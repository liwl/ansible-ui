import os
from ansible.parsing.dataloader import DataLoader
from ansible.inventory.manager import InventoryManager
from ansible.vars.manager import VariableManager
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
from ansible import context
from ansible.module_utils.common.collections import ImmutableDict
import tempfile
import json
import subprocess
import threading
import re
import socket
import posixpath
from crypto_utils import CryptoUtils

# ansible-core 不支持把 Windows 当作控制节点：它依赖 fork 起 worker 进程，
# Windows 只能 spawn，任务对象里有不可序列化的模块引用，会抛
# "TypeError: cannot pickle 'module' object"。因此在 Windows 上改用 paramiko
# 直连实现巡检 / 命令执行 / 文件分发（终端与 SFTP 页面本来就是 paramiko）。
IS_WINDOWS = os.name == 'nt'
PARAMIKO_FALLBACK = IS_WINDOWS

# 远端命令执行超时（秒）：避免远端不返回时把请求线程挂死
EXEC_TIMEOUT = int(os.getenv('SSH_EXEC_TIMEOUT', '120'))

class ResultCallback(CallbackBase):
    """自定义回调类来处理任务结果"""
    def __init__(self):
        super().__init__()
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_ok(self, result):
        self.host_ok[result._host.get_name()] = result

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.host_failed[result._host.get_name()] = result

    def v2_runner_on_unreachable(self, result):
        self.host_unreachable[result._host.get_name()] = result

class AnsibleManager:
    def __init__(self, db):
        self.db = db
        self.crypto = CryptoUtils()
        context.CLIARGS = ImmutableDict(
            connection='smart',
            module_path=None,
            forks=30,
            become=None,
            become_method=None,
            become_user=None,
            check=False,
            diff=False,
            verbosity=0
        )

    def generate_inventory(self, hosts):
        """生成临时 inventory 文件"""
        inventory_content = ["[managed_hosts]"]
        for host in hosts:
            line = f"{host['address']} ansible_user={host['username']} ansible_port={host['port']} "
            
            if host['auth_method'] == 'key':
                key_path = (
                    (host.get('private_key_path') or '').strip()
                    or os.getenv('SSH_PRIVATE_KEY', '').strip()
                    or '/root/.ssh/id_ed25519'
                )
                line += f"ansible_ssh_private_key_file={key_path} "
            elif host['auth_method'] == 'password':
                password = host.get('password')
                if password:
                    line += f"ansible_ssh_pass={password} "

            line += "ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
            inventory_content.append(line)

        fd, inventory_path = tempfile.mkstemp(prefix='ansible_inventory_')
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(inventory_content))
        
        return inventory_path

    def execute_command(self, command, target_hosts=None):
        """执行命令：Windows 控制节点走 paramiko，其它平台走 ansible"""
        if target_hosts is None:
            target_hosts = self.db.get_hosts()
        if PARAMIKO_FALLBACK:
            return self._execute_command_paramiko(command, target_hosts)
        return self._execute_command_ansible(command, target_hosts)

    def _execute_command_ansible(self, command, target_hosts=None):
        if target_hosts is None:
            target_hosts = self.db.get_hosts()

        inventory_path = self.generate_inventory(target_hosts)
        
        try:
            loader = DataLoader()
            inventory = InventoryManager(loader=loader, sources=inventory_path)
            variable_manager = VariableManager(loader=loader, inventory=inventory)
            
            play_source = dict(
                name="Ansible Ad-Hoc",
                hosts='managed_hosts',
                gather_facts='no',
                tasks=[dict(action=dict(module='shell', args=command))]
            )

            play = Play().load(play_source, variable_manager=variable_manager, loader=loader)
            results_callback = ResultCallback()

            tqm = None
            try:
                tqm = TaskQueueManager(
                    inventory=inventory,
                    variable_manager=variable_manager,
                    loader=loader,
                    passwords=dict(),
                    stdout_callback=results_callback
                )
                tqm.run(play)
            finally:
                if tqm is not None:
                    tqm.cleanup()

            results = {
                'success': {},
                'failed': {},
                'unreachable': {}
            }

            for host, result in results_callback.host_ok.items():
                results['success'][host] = {
                    'stdout': result._result.get('stdout', ''),
                    'stderr': result._result.get('stderr', ''),
                    'rc': result._result.get('rc', 0)
                }
                host_id = next((h['id'] for h in target_hosts if h['address'] == host), None)
                if host_id:
                    self.db.log_command(
                        host_id,
                        command,
                        json.dumps(results['success'][host]),
                        'success'
                    )

            for host, result in results_callback.host_failed.items():
                results['failed'][host] = {
                    'msg': result._result.get('msg', ''),
                    'rc': result._result.get('rc', 1)
                }
                host_id = next((h['id'] for h in target_hosts if h['address'] == host), None)
                if host_id:
                    self.db.log_command(
                        host_id,
                        command,
                        json.dumps(results['failed'][host]),
                        'failed'
                    )

            for host, result in results_callback.host_unreachable.items():
                results['unreachable'][host] = {
                    'msg': result._result.get('msg', '')
                }
                host_id = next((h['id'] for h in target_hosts if h['address'] == host), None)
                if host_id:
                    self.db.log_command(
                        host_id,
                        command,
                        json.dumps(results['unreachable'][host]),
                        'unreachable'
                    )

            return results

        finally:
            os.remove(inventory_path)

    def execute_ping(self, target_hosts):
        """连通性巡检：Windows 控制节点走 paramiko，其它平台走 ansible ping 模块"""
        if PARAMIKO_FALLBACK:
            return self._execute_ping_paramiko(target_hosts)
        return self._execute_ping_ansible(target_hosts)

    def _execute_ping_ansible(self, target_hosts):
        inventory_path = self.generate_inventory(target_hosts)
        
        try:
            loader = DataLoader()
            inventory = InventoryManager(loader=loader, sources=inventory_path)
            variable_manager = VariableManager(loader=loader, inventory=inventory)
            
            play_source = dict(
                name="Ansible Ping",
                hosts='managed_hosts',
                gather_facts='no',
                tasks=[dict(action=dict(module='ping'))]
            )

            play = Play().load(play_source, variable_manager=variable_manager, loader=loader)
            results_callback = ResultCallback()

            tqm = None
            try:
                tqm = TaskQueueManager(
                    inventory=inventory,
                    variable_manager=variable_manager,
                    loader=loader,
                    passwords=dict(),
                    stdout_callback=results_callback
                )
                tqm.run(play)
            finally:
                if tqm is not None:
                    tqm.cleanup()

            results = {
                'success': {},
                'failed': {},
                'unreachable': {}
            }

            for host, result in results_callback.host_ok.items():
                results['success'][host] = result._result
                host_id = next((h['id'] for h in target_hosts if h['address'] == host), None)
                if host_id:
                    self.db.log_command(
                        host_id,
                        'ping',
                        json.dumps(result._result),
                        'success'
                    )

            for host, result in results_callback.host_failed.items():
                results['failed'][host] = result._result
                host_id = next((h['id'] for h in target_hosts if h['address'] == host), None)
                if host_id:
                    self.db.log_command(
                        host_id,
                        'ping',
                        json.dumps(result._result),
                        'failed'
                    )

            for host, result in results_callback.host_unreachable.items():
                results['unreachable'][host] = result._result
                host_id = next((h['id'] for h in target_hosts if h['address'] == host), None)
                if host_id:
                    self.db.log_command(
                        host_id,
                        'ping',
                        json.dumps(result._result),
                        'unreachable'
                    )

            return results

        finally:
            os.remove(inventory_path)

    def get_host_facts(self, host_id):
        """获取主机详细信息"""
        host = self.db.get_host(host_id)
        if not host:
            return None

        results = self.execute_command('ansible_facts', [host])
        if host['address'] in results['success']:
            return results['success'][host['address']]
        return None

    def run_playbook(self, play, target_hosts=None):
        """运行 playbook"""
        try:
            loader = DataLoader()
            
            if target_hosts:
                inventory_path = self.generate_inventory(target_hosts)
            else:
                inventory_path = self.generate_inventory(self.db.get_hosts())

            inventory = InventoryManager(loader=loader, sources=inventory_path)
            variable_manager = VariableManager(loader=loader, inventory=inventory)
            
            results_callback = ResultCallback()

            tqm = None
            try:
                tqm = TaskQueueManager(
                    inventory=inventory,
                    variable_manager=variable_manager,
                    loader=loader,
                    passwords=dict(),
                    stdout_callback=results_callback
                )
                for play_item in play:
                    play_obj = Play().load(play_item, variable_manager=variable_manager, loader=loader)
                    tqm.run(play_obj)
            finally:
                if tqm is not None:
                    tqm.cleanup()

            return {
                'success': results_callback.host_ok,
                'failed': results_callback.host_failed,
                'unreachable': results_callback.host_unreachable
            }
        except Exception as e:
            raise Exception(f"执行 playbook 失败: {str(e)}")

    def copy_file_to_hosts(self, src, dest, hosts):
        """复制文件到指定主机，返回详细的成功/失败结果"""
        if not isinstance(hosts, list):
            hosts = [hosts]

        selected_hosts_data = []
        all_hosts = self.db.get_hosts()
        for host in all_hosts:
            host_id_str = str(host['id'])
            if host_id_str in [str(h) for h in hosts]:
                selected_hosts_data.append(host)

        if not selected_hosts_data:
            raise Exception("没有找到选中的主机")

        if PARAMIKO_FALLBACK:
            return self._copy_file_paramiko(src, dest, selected_hosts_data)

        return self._copy_file_to_hosts_ansible(src, dest, selected_hosts_data)

    def _copy_file_to_hosts_ansible(self, src, dest, selected_hosts_data):
        hosts_str = ','.join([h['address'] for h in selected_hosts_data])
        
        play = [{
            'name': 'Copy file to selected hosts',
            'hosts': hosts_str,
            'gather_facts': 'no',
            'tasks': [{
                'name': 'Ensure destination directory exists',
                'file': {
                    'path': os.path.dirname(dest),
                    'state': 'directory',
                    'mode': '0755'
                }
            }, {
                'name': 'Copy file to remote hosts',
                'copy': {
                    'src': src,
                    'dest': dest,
                    'mode': '0644'
                }
            }]
        }]
        
        try:
            result = self.run_playbook(play, target_hosts=selected_hosts_data)
            return result
        except Exception as e:
            raise Exception(f"复制文件失败: {str(e)}")

    def copy_file_to_all(self, src, dest):
        """复制文件到所有主机，返回详细的成功/失败结果"""
        all_hosts = self.db.get_hosts()
        if PARAMIKO_FALLBACK:
            return self._copy_file_paramiko(src, dest, all_hosts)

        return self._copy_file_to_all_ansible(src, dest, all_hosts)

    def _copy_file_to_all_ansible(self, src, dest, all_hosts):
        play = [{
            'name': 'Copy file to all hosts',
            'hosts': 'all',
            'gather_facts': 'no',
            'tasks': [{
                'name': 'Ensure destination directory exists',
                'file': {
                    'path': os.path.dirname(dest),
                    'state': 'directory',
                    'mode': '0755'
                }
            }, {
                'name': 'Copy file to remote hosts',
                'copy': {
                    'src': src,
                    'dest': dest,
                    'mode': '0644'
                }
            }]
        }]
        
        try:
            result = self.run_playbook(play, target_hosts=all_hosts)
            return result
        except Exception as e:
            raise Exception(f"复制文件失败: {str(e)}")

    # ------------------------------------------------------------------
    # paramiko 直连实现（Windows 控制节点，或 ansible 不可用时）
    # 返回结构与 ansible 版本保持一致：{success/failed/unreachable: {address: {...}}}
    # ------------------------------------------------------------------

    def _paramiko_connect(self, host, timeout=8):
        """按主机配置建立 SSH 连接（密码或密钥）"""
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_args = {
            'hostname': host['address'],
            'port': int(host.get('port') or 22),
            'username': host['username'],
            'timeout': timeout,
            'banner_timeout': timeout,
            'auth_timeout': timeout,
        }

        if (host.get('auth_method') or 'password') == 'password':
            connect_args['password'] = host.get('password') or ''
            connect_args['look_for_keys'] = False
            connect_args['allow_agent'] = False
        else:
            key_path = (host.get('private_key_path') or '').strip() or os.getenv('SSH_PRIVATE_KEY')
            if key_path and os.path.exists(key_path):
                connect_args['key_filename'] = key_path
                connect_args['look_for_keys'] = False
                connect_args['allow_agent'] = False

        client.connect(**connect_args)
        return client

    @staticmethod
    def _is_unreachable_error(exc):
        """区分「连不上」和「连上了但认证/执行失败」"""
        import paramiko
        from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError

        if isinstance(exc, AuthenticationException):
            return False
        return isinstance(exc, (
            NoValidConnectionsError,
            paramiko.SSHException,
            socket.timeout,
            TimeoutError,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError,
        ))

    @staticmethod
    def _ensure_remote_dir(sftp, remote_dir):
        """逐级创建远端目录，已存在则跳过"""
        path = (remote_dir or '').replace('\\', '/')
        if path in ('', '.', '/'):
            return
        if not path.startswith('/'):
            path = '/' + path
        current = ''
        for part in [p for p in path.split('/') if p and p != '.']:
            current += '/' + part
            try:
                sftp.stat(current)
            except IOError:
                try:
                    sftp.mkdir(current)
                except IOError:
                    pass

    def _execute_ping_paramiko(self, target_hosts):
        """用 SSH 连接 + echo 探活代替 ansible ping 模块"""
        results = {'success': {}, 'failed': {}, 'unreachable': {}}

        for host in target_hosts:
            address = host['address']
            host_id = host.get('id')
            client = None
            try:
                client = self._paramiko_connect(host)
                _stdin, stdout, stderr = client.exec_command('echo pong', timeout=10)
                output = stdout.read().decode('utf-8', 'replace').strip()
                rc = stdout.channel.recv_exit_status()
                if rc == 0 and output:
                    payload = {'ping': 'pong', 'stdout': output, 'rc': rc}
                    results['success'][address] = payload
                    status = 'success'
                else:
                    payload = {
                        'msg': stderr.read().decode('utf-8', 'replace').strip() or f'rc={rc}',
                        'rc': rc,
                    }
                    results['failed'][address] = payload
                    status = 'failed'
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                payload = {'msg': message, 'ping': 'failed'}
                if self._is_unreachable_error(exc):
                    results['unreachable'][address] = payload
                    status = 'unreachable'
                else:
                    results['failed'][address] = payload
                    status = 'failed'
            finally:
                if client is not None:
                    client.close()

            if host_id:
                self.db.log_command(
                    host_id, 'ping', json.dumps(payload, ensure_ascii=False), status
                )

        return results

    def _execute_command_paramiko(self, command, target_hosts):
        """用 SSH exec_command 执行 shell 命令"""
        results = {'success': {}, 'failed': {}, 'unreachable': {}}

        for host in target_hosts:
            address = host['address']
            host_id = host.get('id')
            client = None
            try:
                client = self._paramiko_connect(host)
                _stdin, stdout, stderr = client.exec_command(command, timeout=EXEC_TIMEOUT)
                out = stdout.read().decode('utf-8', 'replace')
                err = stderr.read().decode('utf-8', 'replace')
                rc = stdout.channel.recv_exit_status()
                payload = {'stdout': out, 'stderr': err, 'rc': rc}
                if rc == 0:
                    results['success'][address] = payload
                    status = 'success'
                else:
                    payload['msg'] = err.strip() or f'命令返回码 {rc}'
                    results['failed'][address] = payload
                    status = 'failed'
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                payload = {'msg': message, 'rc': 1}
                if self._is_unreachable_error(exc):
                    results['unreachable'][address] = {'msg': message}
                    status = 'unreachable'
                else:
                    results['failed'][address] = payload
                    status = 'failed'
            finally:
                if client is not None:
                    client.close()

            if host_id:
                self.db.log_command(
                    host_id, command, json.dumps(payload, ensure_ascii=False), status
                )

        return results

    def _copy_file_paramiko(self, src, dest, hosts):
        """用 SFTP 上传文件，替代 ansible copy 模块"""
        results = {'success': {}, 'failed': {}, 'unreachable': {}}
        remote_dir = posixpath.dirname(dest.replace('\\', '/')) or '/'

        for host in hosts:
            address = host['address']
            host_id = host.get('id')
            client = None
            try:
                client = self._paramiko_connect(host)
                sftp = client.open_sftp()
                try:
                    self._ensure_remote_dir(sftp, remote_dir)
                    sftp.put(src, dest)
                    try:
                        sftp.chmod(dest, 0o644)
                    except IOError:
                        pass
                finally:
                    sftp.close()
                payload = {'msg': 'ok', 'dest': dest, 'size': os.path.getsize(src)}
                results['success'][address] = payload
                status = 'success'
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                payload = {'msg': message}
                if self._is_unreachable_error(exc):
                    results['unreachable'][address] = payload
                    status = 'unreachable'
                else:
                    results['failed'][address] = payload
                    status = 'failed'
            finally:
                if client is not None:
                    client.close()

            if host_id:
                self.db.log_command(
                    host_id,
                    f'upload {os.path.basename(src)} -> {dest}',
                    json.dumps(payload, ensure_ascii=False),
                    status
                )

        return results

    def execute_custom_playbook(self, playbook_content, target_hosts=None, extra_vars=None):
        """执行自定义Playbook，extra_vars 会作为 ansible-playbook -e 变量传入"""
        if IS_WINDOWS:
            raise Exception(
                '当前控制节点是 Windows，ansible-core 官方不支持在 Windows 上执行 playbook'
                '（依赖 fork，Windows 只有 spawn）。请在 Docker 或 Linux 主机上运行本服务后再执行 Playbook；'
                '巡检、命令执行、文件上传已改用 paramiko 直连，不受此限制。'
            )
        fd, playbook_path = tempfile.mkstemp(prefix='ansible_playbook_', suffix='.yml')
        with os.fdopen(fd, 'w') as f:
            f.write(playbook_content)
        
        try:
            inventory_option = []
            if target_hosts:
                inventory_path = self.generate_inventory(target_hosts)
                inventory_option = ['-i', inventory_path]
            
            cmd = ['ansible-playbook', playbook_path] + inventory_option + ['-v']
            if extra_vars:
                cmd += ['-e', json.dumps(extra_vars)]
            logs = []
            log_lock = threading.Lock()
            
            def process_output(process):
                for line in iter(process.stdout.readline, b''):
                    decoded_line = line.decode('utf-8').rstrip()
                    with log_lock:
                        logs.append(decoded_line)
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=False
            )
            
            output_thread = threading.Thread(target=process_output, args=(process,))
            output_thread.daemon = True
            output_thread.start()
            
            process.wait()
            output_thread.join()
            result = {
                'success': process.returncode == 0,
                'return_code': process.returncode,
                'logs': logs,
                'summary': self._parse_playbook_result(logs)
            }
            
            return result
        
        finally:
            os.remove(playbook_path)
            if target_hosts:
                os.remove(inventory_path)
    
    def _parse_playbook_result(self, logs):
        """解析Playbook执行结果，生成主机成功/失败统计"""
        summary = {
            'success': [],
            'failed': [],
            'unreachable': []
        }
        
        success_pattern = re.compile(r'([\w\.-]+)\s+:\s+ok=\d+')
        failed_pattern = re.compile(r'([\w\.-]+)\s+:\s+.*failed=([1-9]\d*)')
        unreachable_pattern = re.compile(r'([\w\.-]+)\s+:\s+.*unreachable=([1-9]\d*)')
        
        for line in logs:
            success_match = success_pattern.search(line)
            if success_match and not failed_pattern.search(line) and not unreachable_pattern.search(line):
                host = success_match.group(1)
                if host not in summary['success']:
                    summary['success'].append(host)
            
            failed_match = failed_pattern.search(line)
            if failed_match:
                host = failed_match.group(1)
                if host not in summary['failed']:
                    summary['failed'].append(host)
            
            unreachable_match = unreachable_pattern.search(line)
            if unreachable_match:
                host = unreachable_match.group(1)
                if host not in summary['unreachable']:
                    summary['unreachable'].append(host)
        
        return summary

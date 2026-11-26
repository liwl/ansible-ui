"""文件管理：SFTP 浏览与编辑、批量上传到主机。"""
import json
import os
import stat
import tempfile
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request
from werkzeug.utils import secure_filename

from ..errors import describe_ssh_error, handle_error
from ..extensions import ansible, app, db
from ..security import auth_required
from ..services.ssh import sftp_client_for_host
from ..utils import allowed_file
from ..config import UPLOAD_FOLDER
bp = Blueprint('files', __name__)


@bp.route('/api/sftp/<int:host_id>/list')
@handle_error
@auth_required
def sftp_list(host_id):
    """获取 SFTP 文件列表"""
    path = request.args.get('path', '/')
    host = db.get_host(host_id)

    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        with sftp_client_for_host(host) as sftp:
            file_list = []
            for entry in sftp.listdir_attr(path):
                file_list.append({
                    'name': entry.filename,
                    'type': 'directory' if stat.S_ISDIR(entry.st_mode) else 'file',
                    'size': entry.st_size,
                    'mtime': entry.st_mtime
                })
            return jsonify(file_list)
    
    except Exception as e:
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/mkdir', methods=['POST'])
@handle_error
@auth_required
def sftp_mkdir(host_id):
    """创建文件夹"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        data = request.json
        path = data.get('path')
        if not path:
            return jsonify({'error': 'Path is required'}), 400

        with sftp_client_for_host(host) as sftp:
            try:
                sftp.stat(path)
                return jsonify({'error': 'Directory already exists'}), 400
            except IOError:
                sftp.mkdir(path)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"SFTP mkdir error: {str(e)}")
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/upload', methods=['POST'])
@handle_error
@auth_required
def sftp_upload(host_id):
    """处理文件上传"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        path = request.form.get('path', '/')
        if not request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files[]')
        
        with sftp_client_for_host(host) as sftp:
            for file in files:
                if file.filename:
                    filename = secure_filename(file.filename)
                    remote_path = os.path.join(path, filename).replace('\\', '/')

                    # 独立临时文件：固定的 /tmp/<文件名> 会让并发上传互相覆盖，
                    # 极端情况下把 A 的文件传到 B 的主机上
                    fd, temp_path = tempfile.mkstemp(prefix='ansible_upload_')
                    os.close(fd)
                    file.save(temp_path)

                    try:
                        sftp.put(temp_path, remote_path)
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"SFTP upload error: {str(e)}")
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/rename', methods=['POST'])
@handle_error
@auth_required
def sftp_rename(host_id):
    """重命名文件或文件夹"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        data = request.json
        old_path = data.get('old_path')
        new_path = data.get('new_path')
        
        if not old_path or not new_path:
            return jsonify({'error': 'Both old_path and new_path are required'}), 400

        with sftp_client_for_host(host) as sftp:
            try:
                sftp.stat(new_path)
                return jsonify({'error': 'Destination already exists'}), 400
            except IOError:
                sftp.rename(old_path, new_path)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"SFTP rename error: {str(e)}")
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/touch', methods=['POST'])
@handle_error
@auth_required
def sftp_touch(host_id):
    """创建空文件"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        data = request.json
        path = data.get('path')
        
        if not path:
            return jsonify({'error': 'Path is required'}), 400

        with sftp_client_for_host(host) as sftp:
            try:
                sftp.stat(path)
                return jsonify({'error': 'File already exists'}), 400
            except IOError:
                with sftp.file(path, 'w') as f:
                    f.write('')

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"SFTP touch error: {str(e)}")
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/read')
@handle_error
@auth_required
def sftp_read(host_id):
    """读取文件内容"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    path = request.args.get('path')

    try:
        with sftp_client_for_host(host) as sftp:
            with sftp.file(path, 'r') as f:
                content = f.read().decode('utf-8', errors='replace')
            return jsonify({'content': content})
    
    except Exception as e:
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/write', methods=['POST'])
@handle_error
@auth_required
def sftp_write(host_id):
    """写入文件内容"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        data = request.json
        path = data.get('path')
        content = data.get('content', '')
        
        if not path:
            return jsonify({'error': 'Path is required'}), 400

        with sftp_client_for_host(host) as sftp:
            with sftp.file(path, 'w') as f:
                f.write(content)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/delete', methods=['POST'])
@handle_error
@auth_required
def sftp_delete(host_id):
    """删除文件或文件夹"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    try:
        data = request.json
        path = data.get('path')
        is_directory = data.get('is_directory', False)
        
        if not path:
            return jsonify({'error': 'Path is required'}), 400

        with sftp_client_for_host(host) as sftp:
            if is_directory:
                if sftp.listdir(path):
                    return jsonify({'error': 'Directory is not empty'}), 400
                sftp.rmdir(path)
            else:
                sftp.remove(path)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/sftp/<int:host_id>/download')
@handle_error
@auth_required
def sftp_download(host_id):
    """下载文件"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404

    path = request.args.get('path')
    if not path:
        return jsonify({'error': 'Path is required'}), 400

    try:
        filename = os.path.basename(path)
        with sftp_client_for_host(host) as sftp:
            file_attr = sftp.stat(path)
            if stat.S_ISDIR(file_attr.st_mode):
                return jsonify({'error': 'Cannot download a directory'}), 400

            # 独立临时文件：避免并发下载同名文件时读到别人的内容（横向泄露）
            fd, temp_path = tempfile.mkstemp(prefix='ansible_download_')
            os.close(fd)
            sftp.get(path, temp_path)

            try:
                with open(temp_path, 'rb') as f:
                    content = f.read()

                response = Response(content)
                response.headers['Content-Type'] = 'application/octet-stream'
                # 用 RFC 5987 的 filename* 传文件名：中文可用，也不会因为
                # 文件名里的引号/换行把响应头截断（头注入）
                response.headers['Content-Disposition'] = (
                    f"attachment; filename*=UTF-8''{quote(filename)}"
                )
                return response
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
    
    except Exception as e:
        app.logger.error(f"SFTP download error: {str(e)}")
        return jsonify({'error': describe_ssh_error(e)}), 500


@bp.route('/api/upload', methods=['POST'])
@handle_error
@auth_required
def api_upload():
    """API版本的文件上传处理，适配前端发送的格式，支持部分成功场景"""
    if 'file' not in request.files:
        return jsonify({'error': '没有文件被上传'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        remote_path = request.form.get('remote_path', '/tmp/')
        hosts_json = request.form.get('hosts', 'all')
        
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        try:
            remote_file_path = os.path.join(remote_path, filename).replace('\\', '/')
            
            if hosts_json != 'all':
                try:
                    hosts = json.loads(hosts_json)
                    if not hosts:
                        return jsonify({'error': '未选择主机'}), 400
                except json.JSONDecodeError:
                    return jsonify({'error': '无效的主机列表格式'}), 400
                
                host_ids = [str(h) for h in hosts]
                all_hosts = db.get_hosts()
                host_map = {str(h['id']): h for h in all_hosts}
                result = ansible.copy_file_to_hosts(file_path, remote_file_path, hosts)
            else:
                all_hosts = db.get_hosts()
                host_map = {str(h['id']): h for h in all_hosts}
                host_ids = list(host_map.keys())
                result = ansible.copy_file_to_all(file_path, remote_file_path)
            
            if os.path.exists(file_path):
                os.remove(file_path)
            
            successful_hosts = []
            failed_hosts = {}
            
            for host, res in result.get('success', {}).items():
                host_id = next((id for id, h in host_map.items() if h['address'] == host), None)
                if host_id:
                    successful_hosts.append(host_id)
            
            for host, res in result.get('failed', {}).items():
                host_id = next((id for id, h in host_map.items() if h['address'] == host), None)
                if host_id:
                    failed_hosts[host_id] = res.get('msg', '未知错误')
            
            for host, res in result.get('unreachable', {}).items():
                host_id = next((id for id, h in host_map.items() if h['address'] == host), None)
                if host_id:
                    failed_hosts[host_id] = '主机不可达'
            
            total = len(host_ids)
            succeeded = len(successful_hosts)
            
            if succeeded == total:  # 全部成功
                return jsonify({
                    'success': True,
                    'message': '文件上传成功',
                    'details': {
                        'succeeded': successful_hosts,
                        'failed': {}
                    }
                })
            elif succeeded > 0:  # 部分成功
                return jsonify({
                    'success': True,
                    'message': f'文件部分上传成功 ({succeeded}/{total})',
                    'details': {
                        'succeeded': successful_hosts,
                        'failed': failed_hosts
                    }
                }), 207  # 207 Multi-Status
            else:  # 全部失败
                return jsonify({
                    'success': False,
                    'message': '文件上传失败',
                    'details': {
                        'succeeded': [],
                        'failed': failed_hosts
                    }
                }), 500
                
        except Exception as e:
            app.logger.error(f"文件上传失败: {str(e)}")
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({
                'success': False,
                'message': str(e),
                'details': {
                    'succeeded': [],
                    'failed': {'all': str(e)}
                }
            }), 500
    
    return jsonify({'error': '不支持的文件类型'}), 400

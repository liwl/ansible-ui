from contextlib import contextmanager
from flask import Flask, request, jsonify, send_from_directory, Response
from database import Database
from ansible_manager import AnsibleManager
import json
import os
from functools import wraps
import secrets
from flask_sock import Sock
import paramiko
import threading
import stat
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import time
import hmac
import hashlib
import jwt
import datetime
import logging
from logging.handlers import RotatingFileHandler
from crypto_utils import CryptoUtils, set_crypto_keys, derive_key_from_credentials

def get_client_ip():
    """获取客户端真实IP地址
    优先从代理转发的头信息中获取真实IP，如不存在则返回直连IP
    """
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr

def _load_or_create_secret_key():
    """获取 Flask 密钥。

    优先级：环境变量 SECRET_KEY > 数据目录下的持久化文件 > 新生成并落盘。
    不这样做的话，未设置 SECRET_KEY 时每次重启都会换密钥，
    已签发的 JWT 全部失效（容器 restart 一下所有用户就被踢下线）。
    """
    env_key = os.getenv('SECRET_KEY')
    if env_key:
        return env_key

    key_file = os.getenv('SECRET_KEY_FILE', os.path.join('data', '.secret_key'))
    try:
        if os.path.exists(key_file):
            with open(key_file, 'r', encoding='utf-8') as fp:
                saved = fp.read().strip()
            if saved:
                return saved

        new_key = secrets.token_hex(32)
        os.makedirs(os.path.dirname(key_file) or '.', exist_ok=True)
        with open(key_file, 'w', encoding='utf-8') as fp:
            fp.write(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        # 此处 app 尚未创建，只能用标准 logging
        logging.getLogger(__name__).warning(
            "未设置 SECRET_KEY，已生成随机密钥并保存到 %s（重启后复用）。"
            "多副本部署请显式设置 SECRET_KEY。", key_file
        )
        return new_key
    except OSError:
        # 只读文件系统等异常场景：退回进程内随机密钥，保证能启动
        return secrets.token_hex(32)


app = Flask(__name__, static_folder='public', static_url_path='')
app.secret_key = _load_or_create_secret_key()
JWT_EXPIRATION = int(os.getenv('JWT_EXPIRATION_HOURS', '5')) * 60 * 60
JWT_SECRET = app.secret_key
db = Database()
ansible = AnsibleManager(db)
crypto = CryptoUtils()

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    app.logger.warning("未设置管理员凭证环境变量(ADMIN_USERNAME/ADMIN_PASSWORD)，请设置这些环境变量以确保系统安全")

sock = Sock(app)
sock.init_app(app)

UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', '/tmp/ansible_uploads')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """检查文件是否允许上传，当前策略是允许所有文件"""
    return True

def handle_error(f):
    """错误处理装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            app.logger.error(f"Error in {f.__name__}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return decorated_function

def get_request_token():
    """从请求中提取JWT令牌"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1]

    return request.cookies.get('token') or request.args.get('token')

def ensure_crypto_key():
    """确保运行期加密密钥已初始化"""
    from crypto_utils import CRYPTO_KEY

    if isinstance(CRYPTO_KEY, bytes) and len(CRYPTO_KEY) == 32:
        return True

    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        app.logger.error("缺少管理员凭证，无法派生加密密钥")
        return False

    app.logger.info("检测到加密密钥未初始化，尝试从管理员凭证派生")
    try:
        key, salt = derive_key_from_credentials(ADMIN_USERNAME, ADMIN_PASSWORD)
        set_crypto_keys(key, salt)
        app.logger.info("密钥派生成功，长度为: %d 字节", len(key))
        return True
    except Exception as e:
        app.logger.error(f"密钥派生失败: {str(e)}")
        return False

@contextmanager
def ssh_client_for_host(host, timeout=10):
    """为指定主机创建并管理SSH连接"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_args = {
        'hostname': host['address'],
        'port': host['port'],
        'username': host['username'],
        'timeout': timeout
    }
    if host['auth_method'] == 'password':
        connect_args['password'] = host['password']

    ssh.connect(**connect_args)
    try:
        yield ssh
    finally:
        ssh.close()

@contextmanager
def sftp_client_for_host(host, timeout=10):
    """为指定主机创建并管理SFTP连接"""
    with ssh_client_for_host(host, timeout=timeout) as ssh:
        with ssh.open_sftp() as sftp:
            yield sftp

def load_user_from_token(token):
    """解析令牌并以数据库为准刷新用户名/角色

    角色不信任令牌里的快照：用户被降级、删除后应立刻失效，
    否则旧令牌还能继续用满整个有效期。
    """
    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get('user_id')
    if isinstance(user_id, int) or str(user_id).isdigit():
        account = db.get_user(int(user_id))
        if not account:
            return None  # 账号已删除，令牌立即失效
        payload['username'] = account['username']
        payload['role'] = account.get('role') or 'viewer'
        return payload

    # 兼容早期版本签发的令牌（user_id 为固定字符串）
    payload.setdefault('username', ADMIN_USERNAME)
    payload.setdefault('role', 'admin')
    return payload

def auth_required(f):
    """JWT认证要求装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_request_token()
        if not token:
            return jsonify({'error': 'Unauthorized'}), 401

        user = load_user_from_token(token)
        if not user:
            return jsonify({'error': 'Invalid or expired token'}), 401

        if not ensure_crypto_key():
            return jsonify({'error': '系统加密配置错误，请联系管理员'}), 500

        request.user = user
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """要求管理员角色（需配合 auth_required 或自行解析令牌）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = getattr(request, 'user', None)
        if not user:
            token = get_request_token()
            user = load_user_from_token(token) if token else None
            if not user:
                return jsonify({'error': 'Unauthorized'}), 401
            request.user = user
        if user.get('role') != 'admin':
            return jsonify({'error': '权限不足，该操作仅管理员可执行'}), 403
        return f(*args, **kwargs)
    return decorated_function

WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')
READONLY_WHITELIST = ('/api/login',)


@app.before_request
def before_request():
    app.logger.info(f"处理请求: {request.path}")

    if request.method == 'OPTIONS':
        return None

    # 只读角色：拦截所有写操作（登录与刷新自身令牌除外）
    if (request.path.startswith('/api/')
            and request.method in WRITE_METHODS
            and request.path not in READONLY_WHITELIST):
        token = get_request_token()
        user = load_user_from_token(token) if token else None
        if user:
            request.user = user
            if user.get('role') != 'admin':
                app.logger.warning(
                    f"只读用户 {user.get('username')} 尝试执行写操作被拒绝: {request.method} {request.path}"
                )
                return jsonify({'error': '权限不足：当前账号为只读角色'}), 403

@app.after_request
def after_request(response):
    
    if request.path.startswith("/api/"):
        status = 'success' if response.status_code < 400 else 'failed'
        user = getattr(request, 'user', None) or {}
        db.add_access_log(
            get_client_ip(),
            request.path, 
            status,
            response.status_code,
            username=user.get('username'),
            method=request.method
        )
    return response


def ensure_primary_admin():
    """确保主管理员账号存在：首次启动时用环境变量凭证初始化 users 表"""
    if db.count_users() == 0:
        if ADMIN_USERNAME and ADMIN_PASSWORD:
            db.create_user(
                ADMIN_USERNAME,
                generate_password_hash(ADMIN_PASSWORD),
                role='admin',
                is_primary=True
            )
            app.logger.info(f"已初始化主管理员账号: {ADMIN_USERNAME}")
        else:
            app.logger.warning("缺少管理员凭证环境变量，users 表为空，无法初始化账号")
            return
    elif db.get_primary_admin_username() is None and ADMIN_USERNAME:
        # 已有用户但没标记主管理员（例如旧库），补标记
        existing = db.get_user_by_username(ADMIN_USERNAME)
        if existing:
            db.update_user(existing['id'], role='admin', is_primary=True)
            app.logger.info(f"已将 {ADMIN_USERNAME} 补标记为主管理员")


@app.route('/api/login', methods=['POST'])
def login():
    """用户登录：优先查 users 表，兼容环境变量里的管理员凭证"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    ensure_primary_admin()

    account = db.get_user_by_username(username)
    verified = False
    is_primary = False

    if account and account.get('password_hash'):
        verified = check_password_hash(account['password_hash'], password)
        is_primary = bool(account.get('is_primary'))

    # 环境变量凭证兜底（例如 users 表被清空、或临时应急登录）
    if not verified and ADMIN_USERNAME and ADMIN_PASSWORD:
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            verified = True
            is_primary = True
            if not account:
                db.create_user(
                    ADMIN_USERNAME,
                    generate_password_hash(ADMIN_PASSWORD),
                    role='admin',
                    is_primary=True
                )
                account = db.get_user_by_username(ADMIN_USERNAME)
            else:
                # 环境变量是主管理员密码的唯一来源，登录成功即同步哈希，
                # 避免旧哈希残留导致历史密码仍可登录
                db.update_user(
                    account['id'],
                    password_hash=generate_password_hash(ADMIN_PASSWORD),
                    role='admin'
                )
                account = db.get_user_by_username(ADMIN_USERNAME)

    if not verified or not account:
        app.logger.warning(f"登录失败，用户名或密码不正确: {username}")
        return jsonify({'success': False, 'message': '用户名或密码不正确'}), 401

    try:
        # 主管理员的凭证参与主机密码加密密钥的派生，必须保持原行为
        if is_primary and ADMIN_USERNAME and ADMIN_PASSWORD:
            key, salt = derive_key_from_credentials(ADMIN_USERNAME, ADMIN_PASSWORD)
            set_crypto_keys(key, salt)
            app.logger.info(f"已从主管理员凭证派生加密密钥，长度为: {len(key)} 字节")
        else:
            ensure_crypto_key()

        db.touch_user_login(account['id'])
        role = account.get('role') or 'admin'
        token = generate_token(account['id'], username=account['username'], role=role)
        response_data = {
            'success': True,
            'message': '登录成功',
            'token': token,
            'username': account['username'],
            'role': role,
        }
        response = jsonify(response_data)
        response.set_cookie(
            'token',
            token,
            max_age=JWT_EXPIRATION,
            httponly=True,
            samesite='Lax'
        )
        return response
    except Exception as e:
        app.logger.error(f"登录处理失败: {str(e)}")
        return jsonify({'success': False, 'message': '登录失败，系统加密配置错误'}), 500


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react_app(path):
    """处理前端路由 - 所有路由都交给React处理，除非是静态文件"""
    app.logger.info(f"serve_react_app 处理 路径: '{path}'")
    
    if path.startswith('terminal'):
        app.logger.info(f"明确处理终端路径: {path}")
        return send_from_directory(app.static_folder, 'index.html')
    
    if path.startswith('api/') or path.startswith('ws/'):
        app.logger.info(f"API或WebSocket路径，返回404: {path}")
        return jsonify({'error': 'Not found'}), 404
    
    static_file_path = os.path.join(app.static_folder, path)
    app.logger.info(f"尝试查找静态文件: {static_file_path}")
    if path != "" and os.path.exists(static_file_path) and not os.path.isdir(static_file_path):
        app.logger.info(f"找到静态文件，返回: {static_file_path}")
        return send_from_directory(app.static_folder, path)
    else:
        app.logger.info(f"未找到静态文件，返回index.html用于前端路由: {path}")
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/hosts', methods=['GET'])
@handle_error
@auth_required
def get_hosts():
    """获取所有主机列表"""
    hosts = db.get_hosts()
    for host in hosts:
        if host['auth_method'] == 'password':
            host['is_password_encrypted'] = crypto.is_encrypted(host['encrypted_password'])
        else:
            host['is_password_encrypted'] = False
        host['password'] = '********'
        if 'encrypted_password' in host:
            del host['encrypted_password']
    return jsonify(hosts)

@app.route('/api/hosts/<int:host_id>', methods=['GET'])
@handle_error
@auth_required
def get_host(host_id):
    """获取单个主机信息"""
    host = db.get_host(host_id)
    if host:
        if host['auth_method'] == 'password':
            host['is_password_encrypted'] = crypto.is_encrypted(host['encrypted_password'])
        else:
            host['is_password_encrypted'] = False
        host['password'] = '********'
        if 'encrypted_password' in host:
            del host['encrypted_password']
        return jsonify(host)
    return jsonify({'error': 'Host not found'}), 404

@app.route('/api/hosts', methods=['POST'])
@handle_error
@auth_required
def add_host():
    """添加单个主机"""
    host_data = request.json
    auth_method = host_data.get('auth_method', 'password') # 默认为密码认证

    required_fields = ['comment', 'address', 'username', 'port']
    if auth_method == 'password':
        required_fields.append('password')
    
    if not all(field in host_data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    host_id = db.add_host(host_data)
    return jsonify({
        'message': 'Host added successfully',
        'host_id': host_id
    }), 201

@app.route('/api/hosts/batch', methods=['POST'])
@handle_error
@auth_required
def add_hosts_batch():
    """批量添加主机"""
    hosts_data = request.json
    if not isinstance(hosts_data, list):
        return jsonify({'error': 'Invalid data format'}), 400

    for host in hosts_data:
        auth_method = host.get('auth_method', 'password')
        required_fields = ['comment', 'address', 'username', 'port']
        if auth_method == 'password':
            required_fields.append('password')
        
        if not all(field in host for field in required_fields):
            return jsonify({'error': f'Missing required fields in host data: {host}'}), 400

    count = db.add_hosts_batch(hosts_data)
    return jsonify({
        'message': f'Successfully added {count} hosts',
        'count': count
    })

@app.route('/api/hosts/<int:host_id>', methods=['PUT'])
@handle_error
@auth_required
def update_host(host_id):
    """更新主机信息"""
    host_data = request.json

    required_fields = ['comment', 'address', 'username', 'port']
    if not all(field in host_data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if not db.get_host(host_id):
        return jsonify({'error': 'Host not found'}), 404
        
    db.update_host(host_id, host_data)
    return jsonify({'message': 'Host updated successfully'})

@app.route('/api/hosts/batch', methods=['DELETE'])
@handle_error
@auth_required
def delete_hosts_batch():
    """批量删除主机"""
    data = request.json or {}
    host_ids = data.get('ids', [])
    if not isinstance(host_ids, list) or not all(isinstance(i, int) for i in host_ids):
        return jsonify({'error': 'ids 必须是一个整数数组'}), 400
    deleted = db.delete_hosts_batch(host_ids)
    return jsonify({'deleted': deleted, 'message': f'成功删除 {deleted} 台主机'})


@app.route('/api/hosts/<int:host_id>', methods=['DELETE'])
@handle_error
@auth_required
def delete_host(host_id):
    """删除主机"""
    if not db.get_host(host_id):
        return jsonify({'error': 'Host not found'}), 404
        
    db.delete_host(host_id)
    return jsonify({'message': 'Host deleted successfully'})

@app.route('/api/execute', methods=['POST'])
@handle_error
@auth_required
def execute_command():
    """执行命令"""
    data = request.json
    command = data.get('command')
    host_ids = data.get('hosts')

    if not command:
        return jsonify({'error': 'Command is required'}), 400

    if host_ids == 'all':
        target_hosts = db.get_hosts()
    else:
        if not isinstance(host_ids, list):
            return jsonify({'error': 'Invalid hosts format'}), 400
        target_hosts = []
        for host_id in host_ids:
            host = db.get_host(host_id)
            if host:
                target_hosts.append(host)
            else:
                return jsonify({'error': f'Host not found: {host_id}'}), 404

    if not target_hosts:
        return jsonify({'error': 'No valid target hosts'}), 400

    results = ansible.execute_command(command, target_hosts)
    return jsonify(results)

@app.route('/api/logs', methods=['GET'])
@handle_error
@auth_required
def get_logs():
    """获取命令执行日志（支持按主机/状态/时间/关键词筛选与分页）"""
    limit = min(max(request.args.get('limit', default=50, type=int), 1), 500)
    offset = max(request.args.get('offset', default=0, type=int), 0)
    logs = db.get_command_logs(
        limit=limit,
        offset=offset,
        host_id=request.args.get('host_id', default=None, type=int),
        status=request.args.get('status', default=None, type=str),
        date_from=request.args.get('date_from', default=None, type=str),
        date_to=request.args.get('date_to', default=None, type=str),
        keyword=request.args.get('keyword', default=None, type=str),
        sort=request.args.get('sort', default=None, type=str),
        order=request.args.get('order', default='desc', type=str),
    )
    return jsonify(logs)

@app.route('/api/hosts/<int:host_id>/facts', methods=['GET'])
@handle_error
@auth_required
def get_host_facts(host_id):
    """获取主机详细信息"""
    facts = ansible.get_host_facts(host_id)
    if facts:
        return jsonify(facts)
    return jsonify({'error': 'Failed to get host facts'}), 404

@app.route('/api/hosts/<int:host_id>/ping', methods=['GET'])
@handle_error
@auth_required
def ping_host(host_id):
    """检查主机连通性"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404
    
    results = ansible.execute_ping([host])
    host_address = host['address']
    if host_address in results['success']:
        status = 'success'
    elif host_address in results['unreachable']:
        status = 'unreachable'
    else:
        status = 'failed'
    db.update_hosts_status({host_id: status})
    messages = {'success': '连接正常', 'unreachable': '无法连接', 'failed': '失败'}
    return jsonify({'status': status, 'message': messages[status]})


def run_patrol():
    """执行一次全主机巡检，把结果写回 hosts 表并返回汇总。"""
    hosts = db.get_hosts()
    if not hosts:
        return {'checked': 0, 'online': 0, 'offline': 0, 'failed': 0, 'statuses': {}}

    results = None
    try:
        results = ansible.execute_ping(hosts)
    except Exception as e:
        # Windows 等非 Linux 控制节点上 ansible 可能不可用，不能让巡检线程崩掉
        app.logger.error(f"巡检执行失败: {e}")

    status_map = {}
    for host in hosts:
        address = host['address']
        if results is None:
            status_map[host['id']] = 'failed'
        elif address in results['success']:
            status_map[host['id']] = 'success'
        elif address in results['unreachable']:
            status_map[host['id']] = 'unreachable'
        else:
            status_map[host['id']] = 'failed'

    db.update_hosts_status(status_map)

    online = sum(1 for s in status_map.values() if s == 'success')
    offline = sum(1 for s in status_map.values() if s == 'unreachable')
    failed = sum(1 for s in status_map.values() if s == 'failed')
    app.logger.info(f"巡检完成: 共 {len(hosts)} 台, 在线 {online}, 离线 {offline}, 异常 {failed}")
    return {
        'checked': len(hosts),
        'online': online,
        'offline': offline,
        'failed': failed,
        'statuses': status_map,
    }


@app.route('/api/hosts/check-now', methods=['POST'])
@handle_error
@auth_required
def check_hosts_now():
    """手动触发一次全主机巡检"""
    return jsonify(run_patrol())


_patrol_started = False


def start_patrol_scheduler():
    """启动定时巡检守护线程（进程内只启动一次）。"""
    global _patrol_started
    if _patrol_started:
        return
    if os.getenv('PING_ENABLED', 'true').lower() not in ('1', 'true', 'yes'):
        app.logger.info("定时巡检已禁用 (PING_ENABLED=false)")
        return
    try:
        interval = int(os.getenv('PING_INTERVAL', '300'))
    except ValueError:
        interval = 300
    if interval < 30:
        interval = 30

    def loop():
        while True:
            # 启动后先等一个周期再首次巡检，避免服务刚起来就阻塞
            time.sleep(interval)
            try:
                run_patrol()
            except Exception as e:
                app.logger.error(f"定时巡检线程异常: {e}")

    threading.Thread(target=loop, daemon=True, name='patrol-scheduler').start()
    _patrol_started = True
    app.logger.info(f"定时巡检已启动, 间隔 {interval} 秒")


@sock.route('/ws/terminal/<int:host_id>')
def terminal_ws(ws, host_id):
    """处理终端 WebSocket 连接"""
    app.logger.info(f"处理WebSocket连接请求: host_id={host_id}")
    
    token = request.args.get('token')
    if not token:
        app.logger.error("终端WebSocket错误: 未提供令牌")
        ws.send(json.dumps({"error": "Authorization required"}))
        return
    
    try:
        # token 格式: host_id:timestamp:signature
        parts = token.split(':')
        if len(parts) != 3 or parts[0] != str(host_id):
            raise ValueError("Invalid token format")
            
        token_timestamp = int(parts[1])
        current_time = int(time.time())
        if current_time - token_timestamp > 300:  # 5分钟有效期
            raise ValueError("Token expired")
            
        message = f"{host_id}:{token_timestamp}"
        expected_signature = hmac.new(
            app.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if parts[2] != expected_signature:
            raise ValueError("Invalid token signature")
            
    except Exception:
        app.logger.error("终端WebSocket令牌验证失败")
        ws.send(json.dumps({"error": "Invalid or expired token"}))
        return
    
    host = db.get_host(host_id)
    if not host:
        app.logger.error("终端WebSocket错误: 主机ID不存在")
        ws.send(json.dumps({"error": "Host not found"}))
        return
    
    app.logger.info(f"找到主机信息: id={host_id}")
    
    try:
        with ssh_client_for_host(host, timeout=10) as ssh:
            term_width = 100
            term_height = 30

            app.logger.info("SSH连接成功，创建终端会话")
            channel = ssh.invoke_shell(term='xterm-256color', width=term_width, height=term_height)

            def send_data():
                while True:
                    try:
                        if channel.recv_ready():
                            data = channel.recv(1024).decode('utf-8', errors='ignore')
                            if data:
                                ws.send(data)
                        else:
                            time.sleep(0.1)
                    except Exception:
                        app.logger.error("数据发送错误")
                        break

            thread = threading.Thread(target=send_data)
            thread.daemon = True
            thread.start()

            app.logger.info("WebSocket连接已建立，后台线程已启动")

            welcome_msg = "\r\n\x1b[1;32m*** 已连接到主机 ***\x1b[0m\r\n"
            ws.send(welcome_msg)

            while True:
                try:
                    message = ws.receive()
                    if message is None:
                        app.logger.info("WebSocket连接已关闭")
                        break

                    data = json.loads(message)
                    if data['type'] == 'input':
                        channel.send(data['data'])
                    elif data['type'] == 'resize':
                        new_size = data['data']
                        channel.resize_pty(
                            width=new_size['cols'],
                            height=new_size['rows']
                        )
                except json.JSONDecodeError:
                    app.logger.error("JSON解析错误")
                    continue
                except Exception:
                    app.logger.error("WebSocket接收错误")
                    break
    
    except paramiko.AuthenticationException:
        app.logger.error("SSH认证失败")
        ws.send('\r\n\x1b[1;31m*** SSH认证失败 ***\x1b[0m\r\n')
    except paramiko.SSHException:
        app.logger.error("SSH连接错误")
        ws.send('\r\n\x1b[1;31m*** SSH连接错误 ***\x1b[0m\r\n')
    except Exception:
        app.logger.error("终端连接错误")
        ws.send('\r\n\x1b[1;31m*** 连接错误 ***\x1b[0m\r\n')
    finally:
        app.logger.info("关闭终端连接")
        if 'channel' in locals():
            channel.close()

@app.route('/api/sftp/<int:host_id>/list')
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/mkdir', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/upload', methods=['POST'])
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

                    temp_path = os.path.join('/tmp', filename)
                    file.save(temp_path)

                    try:
                        sftp.put(temp_path, remote_path)
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"SFTP upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/rename', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/touch', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/read')
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/write', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/delete', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/sftp/<int:host_id>/download')
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

            # 仅使用文件名，避免目录遍历。
            temp_path = os.path.join('/tmp', secure_filename(filename))
            sftp.get(path, temp_path)

            try:
                with open(temp_path, 'rb') as f:
                    content = f.read()

                response = Response(content)
                response.headers['Content-Type'] = 'application/octet-stream'
                response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
    
    except Exception as e:
        app.logger.error(f"SFTP download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found_error(error):
    """处理404错误"""
    app.logger.error(f"404错误: 路径={request.path}, IP={request.remote_addr}, 方法={request.method}")
    
    if request.path.startswith('/api/') or request.path.startswith('/ws/'):
        return jsonify({'error': 'Not found'}), 404
    
    return send_from_directory(app.static_folder, 'index.html')

@app.errorhandler(500)
def internal_error(error):
    """处理500错误"""
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/access-logs', methods=['GET'])
@handle_error
@auth_required
def get_access_logs():
    """获取访问日志（支持按 IP / 路径 / 操作人筛选）"""
    limit = request.args.get('limit', default=100, type=int)
    ip_filter = request.args.get('ip', '').strip()
    path_filter = request.args.get('path', '').strip()
    user_filter = request.args.get('username', '').strip()
    logs = db.get_access_logs(
        limit=limit, ip_filter=ip_filter, path_filter=path_filter, user_filter=user_filter
    )
    return jsonify(logs)

@app.route('/api/access-logs/users', methods=['GET'])
@handle_error
@auth_required
@admin_required
def get_access_log_users():
    """审计日志中出现过的操作人（用于筛选下拉）"""
    return jsonify(db.get_access_log_users())

@app.route('/api/me', methods=['GET'])
@handle_error
@auth_required
def get_me():
    """当前登录用户信息"""
    user = request.user
    account = db.get_user(user.get('user_id')) if str(user.get('user_id', '')).isdigit() else None
    return jsonify({
        'username': user.get('username') or (account or {}).get('username'),
        'role': user.get('role', 'admin'),
        'last_login': (account or {}).get('last_login'),
    })

@app.route('/api/users', methods=['GET'])
@handle_error
@auth_required
@admin_required
def list_users():
    """用户列表（仅管理员）"""
    return jsonify(db.get_users())

@app.route('/api/users', methods=['POST'])
@handle_error
@auth_required
@admin_required
def create_user():
    """新建用户（仅管理员）"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = data.get('role') or 'viewer'

    if not username or len(username) < 2:
        return jsonify({'error': '用户名至少 2 个字符'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码至少 6 位'}), 400
    if role not in ('admin', 'viewer'):
        return jsonify({'error': '角色只能是 admin 或 viewer'}), 400
    if db.get_user_by_username(username):
        return jsonify({'error': '用户名已存在'}), 400

    try:
        user_id = db.create_user(username, generate_password_hash(password), role=role)
    except Exception as e:
        return jsonify({'error': f'创建失败: {str(e)}'}), 400

    app.logger.info(f"管理员 {request.user.get('username')} 创建了用户 {username}({role})")
    return jsonify({'user_id': user_id, 'message': '用户创建成功'}), 201

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@handle_error
@auth_required
@admin_required
def update_user(user_id):
    """修改用户角色或重置密码（仅管理员）"""
    account = db.get_user(user_id)
    if not account:
        return jsonify({'error': '用户不存在'}), 404

    data = request.json or {}
    role = data.get('role')
    password = data.get('password')

    if role is not None and role not in ('admin', 'viewer'):
        return jsonify({'error': '角色只能是 admin 或 viewer'}), 400

    if account.get('is_primary'):
        if role is not None and role != 'admin':
            return jsonify({'error': '主管理员不能被降级'}), 400
        if password:
            return jsonify({'error': '主管理员密码由环境变量 ADMIN_PASSWORD 决定，请在部署配置中修改'}), 400

    password_hash = None
    if password:
        if len(password) < 6:
            return jsonify({'error': '密码至少 6 位'}), 400
        password_hash = generate_password_hash(password)

    db.update_user(user_id, password_hash=password_hash, role=role)
    app.logger.info(
        f"管理员 {request.user.get('username')} 更新了用户 {account['username']}"
        f"（角色={role or account['role']}，改密={bool(password)}）"
    )
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@handle_error
@auth_required
@admin_required
def delete_user(user_id):
    """删除用户（仅管理员）"""
    account = db.get_user(user_id)
    if not account:
        return jsonify({'error': '用户不存在'}), 404
    if account.get('is_primary'):
        return jsonify({'error': '主管理员不能被删除'}), 400
    if str(request.user.get('user_id')) == str(user_id):
        return jsonify({'error': '不能删除当前登录账号'}), 400

    db.delete_user(user_id)
    app.logger.info(f"管理员 {request.user.get('username')} 删除了用户 {account['username']}")
    return jsonify({'success': True})

@app.route('/api/access-logs/cleanup', methods=['POST'])
@handle_error
@auth_required
def cleanup_logs():
    """清理旧日志"""
    db.cleanup_old_logs()
    return jsonify({'message': '已清理3天前的访问日志和命令日志'})

def create_required_directories():
    """创建必要的目录"""
    directories = ['logs', 'data']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

@app.route('/api/upload', methods=['POST'])
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

def generate_token(user_id, username=None, role='admin'):
    """生成JWT令牌"""
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=JWT_EXPIRATION),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def decode_token(token):
    """解码并验证JWT令牌"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def generate_ws_token(host_id):
    """生成用于WebSocket连接的令牌"""
    timestamp = int(time.time())
    message = f"{host_id}:{timestamp}"
    
    signature = hmac.new(
        app.secret_key.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return f"{host_id}:{timestamp}:{signature}"

@app.route('/api/ws-token/<int:host_id>', methods=['GET'])
@auth_required
@admin_required
def get_ws_token(host_id):
    """获取WebSocket连接令牌（终端属于变更型能力，仅管理员可用）"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404
        
    return jsonify({'token': generate_ws_token(host_id)})

@app.route('/api/playbooks', methods=['GET'])
@handle_error
@auth_required
def get_playbooks():
    """获取所有已保存的 Playbook"""
    return jsonify(db.get_playbooks())


@app.route('/api/playbooks', methods=['POST'])
@handle_error
@auth_required
def create_playbook():
    """新增 Playbook"""
    data = request.json or {}
    name = (data.get('name') or '').strip()
    content = data.get('content') or ''
    if not name:
        return jsonify({'error': '请输入 Playbook 名称'}), 400
    if not content.strip():
        return jsonify({'error': '请输入 Playbook 内容'}), 400
    playbook_id = db.add_playbook({
        'name': name,
        'description': (data.get('description') or '').strip(),
        'content': content,
    })
    return jsonify({'id': playbook_id, 'message': 'Playbook 已保存'}), 201


@app.route('/api/playbooks/<int:playbook_id>', methods=['GET'])
@handle_error
@auth_required
def get_playbook(playbook_id):
    """获取单个 Playbook"""
    playbook = db.get_playbook(playbook_id)
    if not playbook:
        return jsonify({'error': 'Playbook not found'}), 404
    return jsonify(playbook)


@app.route('/api/playbooks/<int:playbook_id>', methods=['PUT'])
@handle_error
@auth_required
def update_playbook(playbook_id):
    """更新 Playbook"""
    if not db.get_playbook(playbook_id):
        return jsonify({'error': 'Playbook not found'}), 404
    data = request.json or {}
    name = (data.get('name') or '').strip()
    content = data.get('content') or ''
    if not name:
        return jsonify({'error': '请输入 Playbook 名称'}), 400
    if not content.strip():
        return jsonify({'error': '请输入 Playbook 内容'}), 400
    db.update_playbook(playbook_id, {
        'name': name,
        'description': (data.get('description') or '').strip(),
        'content': content,
    })
    return jsonify({'message': 'Playbook 已更新'})


@app.route('/api/playbooks/<int:playbook_id>', methods=['DELETE'])
@handle_error
@auth_required
def delete_playbook(playbook_id):
    """删除 Playbook"""
    if not db.delete_playbook(playbook_id):
        return jsonify({'error': 'Playbook not found'}), 404
    return jsonify({'message': 'Playbook 已删除'})


@app.route('/api/playbook/execute', methods=['POST'])
@handle_error
@auth_required
def execute_playbook():
    """执行用户自定义的Ansible Playbook，可按 ID 选择已保存的 Playbook"""
    data = request.json
    playbook_content = data.get('playbook')
    playbook_id = data.get('playbook_id')
    host_ids = data.get('host_ids', [])
    extra_vars = data.get('extra_vars')
    if extra_vars is not None and not isinstance(extra_vars, dict):
        return jsonify({'error': 'extra_vars 必须是对象'}), 400

    if playbook_id:
        saved = db.get_playbook(playbook_id)
        if not saved:
            return jsonify({'error': 'Playbook not found'}), 404
        playbook_content = saved['content']

    if not playbook_content:
        return jsonify({'error': '未提供Playbook内容'}), 400
    
    target_hosts = None
    if host_ids:
        target_hosts = [db.get_host(host_id) for host_id in host_ids]
        target_hosts = [host for host in target_hosts if host]
    
    try:
        result = ansible.execute_custom_playbook(playbook_content, target_hosts, extra_vars)
        log_output = json.dumps({'playbook_logs': result['logs'], 'extra_vars': extra_vars or {}})

        if target_hosts:
            for host in target_hosts:
                host_status = 'success'
                if host['address'] in result['summary']['failed']:
                    host_status = 'failed'
                elif host['address'] in result['summary']['unreachable']:
                    host_status = 'unreachable'

                db.log_command(
                    host['id'],
                    'Custom Playbook Execution',
                    log_output,
                    host_status,
                    playbook_id
                )
        else:
            db.log_command(
                None,
                'Custom Playbook Execution',
                log_output,
                'success' if result['success'] else 'failed',
                playbook_id
            )
        
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Playbook执行错误: {str(e)}")
        return jsonify({'error': f'Playbook执行失败: {str(e)}'}), 500

if __name__ == '__main__':
    create_required_directories()

    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', 'logs/app.log')
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_048_576,
        backupCount=3,
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)

    # debug 模式下 reloader 会起两个进程，只在真正的工作进程里启动巡检线程
    if (os.getenv('FLASK_DEBUG', 'false').lower() not in ('1', 'true', 'yes')
            or os.getenv('WERKZEUG_RUN_MAIN') == 'true'):
        ensure_primary_admin()
        # 启动即完成密钥派生：否则首个请求到来前 crypto 单例拿的是随机占位密钥，
        # 用它加密的主机密码在重启后无法解密
        ensure_crypto_key()
        start_patrol_scheduler()

    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', '5000')),
        debug=os.getenv('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes'),
    )

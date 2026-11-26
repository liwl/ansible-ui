"""认证、授权与令牌。

对外提供：
- 鉴权装饰器 auth_required / admin_required
- JWT 签发与校验、WebSocket 一次性签名令牌
- 登录失败限流（进程内，键为 IP + 用户名）
- 客户端 IP 识别（含反向代理信任边界）
- 主管理员初始化、运行期加密密钥派生
"""
import datetime
import hashlib
import hmac
import threading
import time
from functools import wraps

import jwt
from flask import jsonify, request
from werkzeug.security import generate_password_hash

from .extensions import app, db
from .services.crypto_utils import derive_key_from_credentials, set_crypto_keys
from .config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    JWT_EXPIRATION,
    JWT_SECRET,
    LOGIN_LOCK_SECONDS,
    LOGIN_MAX_FAILURES,
    TRUST_PROXY,
)


def get_client_ip():
    """获取客户端 IP。

    只有显式开启 TRUST_PROXY 时才采信代理头，否则一律用 TCP 直连地址。

    采信顺序有讲究：
    1. X-Real-IP —— nginx 用 `$remote_addr` 直接覆盖写入，客户端伪造不了；
    2. X-Forwarded-For 的**最后一跳** —— 这是真正连到反代的地址。
       不能取第一个：`$proxy_add_x_forwarded_for` 会保留客户端自己塞进来的值，
       把它追加在真实 IP 前面，取最左等于直接采信伪造值。
    """
    if TRUST_PROXY:
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[-1].strip()
    return request.remote_addr or '-'


def clean_for_log(value, limit=64):
    """把用户可控内容压成单行，避免 \\r\\n 伪造日志行（日志注入）"""
    if value is None:
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    return text[:limit]


def get_request_token():
    """从请求中提取 JWT 令牌

    Authorization 头优先，其次 cookie（兼容旧前端）。
    query 参数只在 /ws/ 下放行：浏览器的 WebSocket 无法携带自定义头，
    而普通 API 用 ?token= 会把令牌写进代理日志和浏览器历史。
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1]

    cookie_token = request.cookies.get('token')
    if cookie_token:
        return cookie_token

    if request.path.startswith('/ws/'):
        return request.args.get('token')
    return None


def ensure_crypto_key():
    """确保运行期加密密钥已初始化"""
    from .services.crypto_utils import CRYPTO_KEY

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


# ---------- 登录失败限流 ----------
# 进程内计数，单容器部署够用。多副本需要换成 Redis，或者交给网关限流。
# 键是「IP + 用户名」，避免同一出口 IP 下的其他账号被连坐。
_login_failures = {}
_login_lock = threading.Lock()


def _login_throttle_key(username):
    return f"{get_client_ip()}|{clean_for_log(username)}"


def login_lock_remaining(key):
    """剩余锁定秒数，0 表示未锁定"""
    now = time.time()
    with _login_lock:
        record = _login_failures.get(key)
        if not record:
            return 0
        failures, last = record
        if failures < LOGIN_MAX_FAILURES:
            return 0
        remain = int(LOGIN_LOCK_SECONDS - (now - last))
        if remain <= 0:
            _login_failures.pop(key, None)
            return 0
        return remain


def login_note_failure(key):
    now = time.time()
    with _login_lock:
        failures, _ = _login_failures.get(key, (0, now))
        _login_failures[key] = (failures + 1, now)
        # 顺手清理过期记录，避免被大量随机用户名撑爆内存
        if len(_login_failures) > 2000:
            cutoff = now - LOGIN_LOCK_SECONDS
            for stale in [k for k, (_, ts) in _login_failures.items() if ts < cutoff]:
                _login_failures.pop(stale, None)


def login_reset(key):
    with _login_lock:
        _login_failures.pop(key, None)


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

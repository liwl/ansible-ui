"""登录与当前用户。"""
from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

from ..errors import handle_error
from ..extensions import app, db
from ..security import (
    _login_throttle_key,
    auth_required,
    clean_for_log,
    get_client_ip,
    ensure_crypto_key,
    ensure_primary_admin,
    generate_token,
    login_lock_remaining,
    login_note_failure,
    login_reset,
)
from ..services.crypto_utils import derive_key_from_credentials, set_crypto_keys
from ..config import ADMIN_PASSWORD, ADMIN_USERNAME, JWT_EXPIRATION
bp = Blueprint('auth', __name__)


@bp.route('/api/login', methods=['POST'])
def login():
    """用户登录：优先查 users 表，兼容环境变量里的管理员凭证"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    # 暴力破解防护：同一 IP + 用户名连续失败到阈值后锁定一段时间
    throttle_key = _login_throttle_key(username)
    remaining = login_lock_remaining(throttle_key)
    if remaining:
        app.logger.warning(
            "登录被限流: ip=%s user=%s 剩余=%ss",
            get_client_ip(), clean_for_log(username), remaining
        )
        return jsonify({
            'success': False,
            'message': f'失败次数过多，请 {remaining} 秒后再试',
        }), 429

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
        login_note_failure(throttle_key)
        app.logger.warning("登录失败，用户名或密码不正确: %s", clean_for_log(username))
        return jsonify({'success': False, 'message': '用户名或密码不正确'}), 401

    login_reset(throttle_key)

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
            samesite='Lax',
            # HTTPS 下标记 Secure，防止令牌被明文链路带出去
            secure=request.is_secure,
        )
        return response
    except Exception as e:
        app.logger.error(f"登录处理失败: {str(e)}")
        return jsonify({'success': False, 'message': '登录失败，系统加密配置错误'}), 500


@bp.route('/api/me', methods=['GET'])
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

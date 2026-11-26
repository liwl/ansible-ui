"""用户管理（仅管理员）。"""
from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from ..errors import handle_error
from ..extensions import app, db
from ..security import admin_required, auth_required, clean_for_log
bp = Blueprint('users', __name__)


@bp.route('/api/users', methods=['GET'])
@handle_error
@auth_required
@admin_required
def list_users():
    """用户列表（仅管理员）"""
    return jsonify(db.get_users())


@bp.route('/api/users', methods=['POST'])
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
    if len(password) < 8:
        return jsonify({'error': '密码至少 8 位'}), 400
    if password.lower() == username.lower():
        return jsonify({'error': '密码不能与用户名相同'}), 400
    if role not in ('admin', 'viewer'):
        return jsonify({'error': '角色只能是 admin 或 viewer'}), 400
    if db.get_user_by_username(username):
        return jsonify({'error': '用户名已存在'}), 400

    try:
        user_id = db.create_user(username, generate_password_hash(password), role=role)
    except Exception:
        app.logger.exception(f"创建用户失败: {clean_for_log(username)}")
        return jsonify({'error': '创建失败，请查看服务端日志'}), 400

    app.logger.info(f"管理员 {request.user.get('username')} 创建了用户 {username}({role})")
    return jsonify({'user_id': user_id, 'message': '用户创建成功'}), 201


@bp.route('/api/users/<int:user_id>', methods=['PUT'])
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
        if len(password) < 8:
            return jsonify({'error': '密码至少 8 位'}), 400
        if password.lower() == (account.get('username') or '').lower():
            return jsonify({'error': '密码不能与用户名相同'}), 400
        password_hash = generate_password_hash(password)

    db.update_user(user_id, password_hash=password_hash, role=role)
    app.logger.info(
        f"管理员 {request.user.get('username')} 更新了用户 {account['username']}"
        f"（角色={role or account['role']}，改密={bool(password)}）"
    )
    return jsonify({'success': True})


@bp.route('/api/users/<int:user_id>', methods=['DELETE'])
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

"""命令执行日志与访问审计日志。"""
from flask import Blueprint, jsonify, request

from ..errors import handle_error
from ..extensions import db
from ..security import admin_required, auth_required
bp = Blueprint('logs', __name__)


@bp.route('/api/logs', methods=['GET'])
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


@bp.route('/api/access-logs', methods=['GET'])
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


@bp.route('/api/access-logs/users', methods=['GET'])
@handle_error
@auth_required
@admin_required
def get_access_log_users():
    """审计日志中出现过的操作人（用于筛选下拉）"""
    return jsonify(db.get_access_log_users())


@bp.route('/api/access-logs/cleanup', methods=['POST'])
@handle_error
@auth_required
def cleanup_logs():
    """清理旧日志"""
    db.cleanup_old_logs()
    return jsonify({'message': '已清理3天前的访问日志和命令日志'})

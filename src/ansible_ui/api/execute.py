"""命令下发。"""
from flask import Blueprint, jsonify, request

from ..errors import handle_error
from ..extensions import ansible, db
from ..security import auth_required
bp = Blueprint('execute', __name__)


@bp.route('/api/execute', methods=['POST'])
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

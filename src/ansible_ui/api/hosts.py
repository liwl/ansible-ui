"""主机管理：CRUD、facts、连通性检查、手动巡检。"""
from flask import Blueprint, jsonify, request

from ..errors import handle_error
from ..extensions import ansible, crypto, db
from ..security import auth_required
from ..services.patrol import run_patrol
bp = Blueprint('hosts', __name__)


@bp.route('/api/hosts', methods=['GET'])
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


@bp.route('/api/hosts/<int:host_id>', methods=['GET'])
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


@bp.route('/api/hosts', methods=['POST'])
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


@bp.route('/api/hosts/batch', methods=['POST'])
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


@bp.route('/api/hosts/<int:host_id>', methods=['PUT'])
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


@bp.route('/api/hosts/batch', methods=['DELETE'])
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


@bp.route('/api/hosts/<int:host_id>', methods=['DELETE'])
@handle_error
@auth_required
def delete_host(host_id):
    """删除主机"""
    if not db.get_host(host_id):
        return jsonify({'error': 'Host not found'}), 404
        
    db.delete_host(host_id)
    return jsonify({'message': 'Host deleted successfully'})


@bp.route('/api/hosts/<int:host_id>/facts', methods=['GET'])
@handle_error
@auth_required
def get_host_facts(host_id):
    """获取主机详细信息"""
    facts = ansible.get_host_facts(host_id)
    if facts:
        return jsonify(facts)
    return jsonify({'error': 'Failed to get host facts'}), 404


@bp.route('/api/hosts/<int:host_id>/ping', methods=['GET'])
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


@bp.route('/api/hosts/check-now', methods=['POST'])
@handle_error
@auth_required
def check_hosts_now():
    """手动触发一次全主机巡检"""
    return jsonify(run_patrol())

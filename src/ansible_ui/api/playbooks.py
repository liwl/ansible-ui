"""Playbook 的保存与执行。"""
import json

from flask import Blueprint, jsonify, request

from ..errors import handle_error
from ..extensions import ansible, app, db
from ..security import auth_required
bp = Blueprint('playbooks', __name__)


@bp.route('/api/playbooks', methods=['GET'])
@handle_error
@auth_required
def get_playbooks():
    """获取所有已保存的 Playbook"""
    return jsonify(db.get_playbooks())


@bp.route('/api/playbooks', methods=['POST'])
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


@bp.route('/api/playbooks/<int:playbook_id>', methods=['GET'])
@handle_error
@auth_required
def get_playbook(playbook_id):
    """获取单个 Playbook"""
    playbook = db.get_playbook(playbook_id)
    if not playbook:
        return jsonify({'error': 'Playbook not found'}), 404
    return jsonify(playbook)


@bp.route('/api/playbooks/<int:playbook_id>', methods=['PUT'])
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


@bp.route('/api/playbooks/<int:playbook_id>', methods=['DELETE'])
@handle_error
@auth_required
def delete_playbook(playbook_id):
    """删除 Playbook"""
    if not db.delete_playbook(playbook_id):
        return jsonify({'error': 'Playbook not found'}), 404
    return jsonify({'message': 'Playbook 已删除'})


@bp.route('/api/playbook/execute', methods=['POST'])
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

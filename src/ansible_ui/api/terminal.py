"""Web 终端（WebSocket）与终端授权令牌。"""
import hashlib
import hmac
import json
import threading
import time

import paramiko
from flask import Blueprint, jsonify, request

from ..extensions import app, db, sock
from ..security import admin_required, auth_required, generate_ws_token
from ..services.ssh import ssh_client_for_host
bp = Blueprint('terminal', __name__)


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
        
        # 定长比较，避免逐字节比较泄露签名前缀
        if not hmac.compare_digest(parts[2], expected_signature):
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


@bp.route('/api/ws-token/<int:host_id>', methods=['GET'])
@auth_required
@admin_required
def get_ws_token(host_id):
    """获取WebSocket连接令牌（终端属于变更型能力，仅管理员可用）"""
    host = db.get_host(host_id)
    if not host:
        return jsonify({'error': 'Host not found'}), 404
        
    return jsonify({'token': generate_ws_token(host_id)})

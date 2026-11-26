"""SPA 静态资源托管：非 API 路径一律回 index.html 交给前端路由。"""
import os

from flask import Blueprint, jsonify, send_from_directory

from ..extensions import app
bp = Blueprint('frontend', __name__)


@bp.route('/', defaults={'path': ''})
@bp.route('/<path:path>')
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

"""统一错误处理。

原则：异常细节只写服务端日志，回给客户端的永远是归类后的通用文案，
避免把 SQL 片段、绝对路径、内部主机名泄露出去。
"""
import os
from functools import wraps

from flask import jsonify, request, send_from_directory

from .extensions import app
from .config import MAX_UPLOAD_MB


def handle_error(f):
    """错误处理装饰器

    异常细节只写服务端日志，不回给客户端——异常文本里常带 SQL 片段、
    绝对路径、内部主机名，属于典型的信息泄露。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception:
            app.logger.exception(f"Error in {f.__name__}")
            return jsonify({'error': '服务器内部错误，请查看服务端日志'}), 500
    return decorated_function


def describe_ssh_error(exc):
    """把 SSH/SFTP 异常转成对用户有用、但不泄露内部细节的提示。

    原始异常里常带绝对路径、内部主机名、Python 栈片段，直接回给客户端
    属于信息泄露。这里按特征归类，完整堆栈仍写服务端日志。
    """
    text = (str(exc) or exc.__class__.__name__).lower()
    if 'authentication failed' in text or 'auth fail' in text or 'bad authentication' in text:
        return '认证失败，请检查主机的用户名、密码或密钥配置'
    if 'timed out' in text or 'timeout' in text:
        return '连接超时，请检查网络连通性与目标端口'
    if 'connection refused' in text:
        return '连接被拒绝，请确认目标主机 SSH 服务已启动'
    if 'no such file' in text:
        return '文件或目录不存在'
    if 'permission denied' in text:
        return '权限不足，目标账号无法操作该路径'
    if 'no space left' in text:
        return '目标主机磁盘空间不足'
    return '远程操作失败，详情请查看服务端日志'


@app.errorhandler(413)
def payload_too_large(error):
    """请求体超过 MAX_CONTENT_LENGTH（默认 512MB，可用环境变量调整）"""
    if request.path.startswith('/api/'):
        return jsonify({'error': f'请求体过大，单次上限 {MAX_UPLOAD_MB} MB'}), 413
    return 'Request Entity Too Large', 413


@app.errorhandler(404)
def not_found_error(error):
    """处理404错误"""
    app.logger.warning(f"404错误: 路径={request.path}, IP={request.remote_addr}, 方法={request.method}")

    if request.path.startswith('/api/') or request.path.startswith('/ws/'):
        return jsonify({'error': 'Not found'}), 404

    # 前端产物缺失时不能再 send_from_directory：那会在错误处理器里二次抛 NotFound，
    # Flask 随即把 404 升级成 500，最终只看到一句 "Internal server error"，
    # 完全看不出是"没打包前端"。这里显式报 503，指向真正的问题。
    if not os.path.isfile(os.path.join(app.static_folder or '', 'index.html')):
        app.logger.error(
            "前端产物缺失：%s/index.html 不存在，页面无法渲染。"
            "请确认部署包里有 dist/index.html（构建前端后重新打包）。",
            app.static_folder,
        )
        return jsonify({
            'error': '前端产物缺失',
            'detail': f'{app.static_folder}/index.html 不存在，请重新构建前端产物',
        }), 503

    return send_from_directory(app.static_folder, 'index.html')


@app.errorhandler(500)
def internal_error(error):
    """处理未捕获异常。

    必须在这里记堆栈：handle_error 只覆盖被它装饰的视图函数，
    而 before_request / after_request / 静态路由 / 蓝图注册阶段的异常
    会直接落到这里。原来这里只返回 JSON 不打日志，
    线上表现就是「页面 500，但日志里什么都没有」。
    """
    original = getattr(error, 'original_exception', None)
    if original is not None:
        app.logger.exception(
            "未捕获异常: %s %s", request.method, request.path, exc_info=original
        )
    else:
        app.logger.error(
            "500 错误: %s %s (%s)", request.method, request.path, error
        )
    return jsonify({'error': 'Internal server error'}), 500

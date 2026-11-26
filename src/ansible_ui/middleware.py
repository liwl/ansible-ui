"""请求钩子：只读角色拦截、安全响应头、访问日志。

这些逻辑只依赖 request/response，因此统一挂在 app 上，
而不是散落到各个蓝图。
"""
from flask import jsonify, request

from . import config
from .extensions import app, db
from .security import get_client_ip, get_request_token, load_user_from_token

WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')
READONLY_WHITELIST = ('/api/login',)


@app.before_request
def before_request():
    app.logger.info(f"处理请求: {request.path}")

    if request.method == 'OPTIONS':
        return None

    # 只读角色：拦截所有写操作（登录与刷新自身令牌除外）
    if (request.path.startswith('/api/')
            and request.method in WRITE_METHODS
            and request.path not in READONLY_WHITELIST):
        token = get_request_token()
        user = load_user_from_token(token) if token else None
        if user:
            request.user = user
            if user.get('role') != 'admin':
                app.logger.warning(
                    f"只读用户 {user.get('username')} 尝试执行写操作被拒绝: {request.method} {request.path}"
                )
                return jsonify({'error': '权限不足：当前账号为只读角色'}), 403


@app.after_request
def after_request(response):
    # ---------- 安全响应头 ----------
    # 防 MIME 嗅探：避免上传的 .txt 被当 html 执行
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    # 防点击劫持
    response.headers.setdefault('X-Frame-Options', 'DENY')
    # 不让外部站点拿到来源路径（路径里可能有主机 id 之类的信息）
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    response.headers.setdefault(
        'Permissions-Policy', 'geolocation=(), microphone=(), camera=(), payment=()'
    )
    response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')

    # CSP：令牌存在 localStorage，一旦被 XSS 拿到等同账号沦陷。
    # 前端是 Vite 打包的 SPA，主题脚本内联在 index.html，Radix/Tailwind 依赖行内样式，
    # 所以这里保留 'unsafe-inline'；它拦不住内联脚本，但能挡掉外链脚本、
    # 内联事件属性之外的注入面，以及 object/iframe 类加载。
    if not app.debug:
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )

    # HSTS 只在确认走 HTTPS 时下发（明文端口下发会让浏览器以后强制 https 而打不开）
    if request.is_secure or config.ENABLE_HSTS:
        response.headers.setdefault(
            'Strict-Transport-Security', 'max-age=15552000; includeSubDomains'
        )

    if request.path.startswith("/api/"):
        status = 'success' if response.status_code < 400 else 'failed'
        user = getattr(request, 'user', None) or {}
        db.add_access_log(
            get_client_ip(),
            request.path, 
            status,
            response.status_code,
            username=user.get('username'),
            method=request.method
        )
    return response

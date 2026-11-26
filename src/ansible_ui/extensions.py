"""应用单例：Flask app 与跨模块共享的对象都在这里创建一次。

之所以保留模块级单例而不是用 create_app() 工厂：
- 全项目有 56 处 ``app.logger``、5 处 ``app.static_folder`` 等调用，
  工厂模式需要把它们全部改成 current_app，改动面远大于收益；
- 本服务是单实例部署，没有多 app 并存（测试、多租户）的需求。

需要测试时改工厂属于后续工作，接口已经通过本模块收敛，不会影响业务代码。
"""

from flask import Flask
from flask_sock import Sock
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config
from .services.ansible_manager import AnsibleManager
from .services.crypto_utils import CryptoUtils
from .services.database import Database

app = Flask(
    'ansible_ui',
    static_folder=str(config.STATIC_DIR),
    static_url_path='',
)
app.secret_key = config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = config.MAX_UPLOAD_MB * 1024 * 1024

# 开了 TRUST_PROXY 才装 ProxyFix，让 X-Forwarded-Proto 生效。
# 不装的话 request.is_secure 恒为 False——反代终止了 TLS，但 Flask 只看到
# 明文 HTTP，结果会话 Cookie 不带 Secure、HSTS 也不下发。
# x_for=1 表示只取 X-Forwarded-For 的最后一跳（与 security.get_client_ip 一致），
# 左边那些客户端自己塞的值一律不认。x_host=0：Nginx 已用 $host 覆盖 Host 头。
if config.TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)

# WebSocket 支持（终端实时会话）
sock = Sock(app)

# 跨模块共享的服务对象
db = Database(config.DB_PATH)
ansible = AnsibleManager(db)
crypto = CryptoUtils()

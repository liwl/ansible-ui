"""进程入口：python -m ansible_ui

负责三件只有"启动进程"才需要管的事：
1. 日志落在文件（容器里由 volume 持久化）
2. 首次启动的初始化（主管理员、加密密钥、定时巡检线程）
3. TLS 装载与 app.run
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import config
from .extensions import app


def setup_logging():
    """日志写文件 + 控制台，级别由 LOG_LEVEL 决定。"""
    os.makedirs(os.path.dirname(config.LOG_FILE) or '.', exist_ok=True)
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=1_048_576,
        backupCount=3,
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)


def build_ssl_context():
    """按环境变量组装 ssl_context。

    配了证书却读不到时宁可启动失败，也不能静默退回明文端口——
    否则"以为开了 HTTPS"的面板会一直以明文对外。
    """
    cert = config.SSL_CERT_FILE
    key = config.SSL_KEY_FILE

    if not cert and not key:
        print("[INFO] 未配置证书，以 HTTP 启动", flush=True)
        return None

    if not cert or not key:
        msg = "SSL_CERT_FILE 与 SSL_KEY_FILE 必须同时设置"
        app.logger.error(msg)
        print(f"[FATAL] {msg}", file=sys.stderr, flush=True)
        raise SystemExit(1)

    missing = [p for p in (cert, key) if not os.path.exists(p)]
    if missing:
        msg = f"证书文件不存在，拒绝以明文启动：{', '.join(missing)}"
        app.logger.error(msg)
        print(f"[FATAL] {msg}", file=sys.stderr, flush=True)
        raise SystemExit(1)

    app.logger.info('已启用 HTTPS，证书：%s', cert)
    print(f"[INFO] 已启用 HTTPS，证书：{cert}", flush=True)
    return (cert, key)


def bootstrap():
    """每个工作进程启动时执行一次的业务初始化。"""
    from .security import ensure_crypto_key, ensure_primary_admin
    from .services.patrol import start_patrol_scheduler
    from .utils import create_required_directories

    create_required_directories()
    ensure_primary_admin()
    # 启动即完成密钥派生：否则首个请求到来前 crypto 单例拿的是随机占位密钥，
    # 用它加密的主机密码在重启后无法解密
    ensure_crypto_key()
    start_patrol_scheduler()


def main():
    setup_logging()

    # debug 模式下 reloader 会起两个进程，只在真正的工作进程里做初始化
    if not config.FLASK_DEBUG or os.getenv('WERKZEUG_RUN_MAIN') == 'true':
        bootstrap()

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.FLASK_DEBUG,
        ssl_context=build_ssl_context(),
        threaded=True,
    )


if __name__ == '__main__':
    main()

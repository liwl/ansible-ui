"""集中配置：所有环境变量只在这里读取一次。

其他模块一律 from ..config import XXX，不再各自 os.getenv——
散落的 os.getenv 是配置漂移的根源（改了 .env 却有一处没生效）。
"""

import logging
import os
import secrets
from pathlib import Path

# ---------- 路径 ----------
PACKAGE_DIR = Path(__file__).resolve().parent


def resolve_static_dir(package_dir=None):
    """定位前端产物目录（index.html 所在处）。

    不能用固定层数推导，因为两种布局的深度不同：
      源码：  <项目根>/src/ansible_ui   → 包的上两级才是项目根
      镜像：  /app/ansible_ui           → 上一级就是 /app（Dockerfile 里 COPY src/ ./）
    所以从包目录逐级向上找第一个真正含 public/index.html 的目录，两种布局都能命中。
    也支持用 STATIC_DIR 环境变量显式覆盖。

    package_dir 参数只为测试注入，正常调用无需传。
    """
    override = os.getenv('STATIC_DIR')
    if override:
        return Path(override)

    pkg = Path(package_dir).resolve() if package_dir else PACKAGE_DIR

    # 首选含 index.html 的目录；退而求其次返回"存在但为空"的 public，
    # 这样前端产物缺失时，报错信息里的路径也是准的（便于直接去补文件）。
    found_but_empty = None
    for base in (pkg, *pkg.parents):
        candidate = base / 'public'
        if (candidate / 'index.html').is_file():
            return candidate
        if found_but_empty is None and candidate.is_dir():
            found_but_empty = candidate

    return found_but_empty or pkg.parent.parent / 'public'


STATIC_DIR = resolve_static_dir()


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name, default, minimum=None):
    try:
        value = int(os.getenv(name, ''))
    except (TypeError, ValueError):
        value = default
    if minimum is not None and value < minimum:
        value = minimum
    return value


# ---------- 运行模式 ----------
FLASK_DEBUG = _env_bool('FLASK_DEBUG')
HOST = os.getenv('HOST', '0.0.0.0')
PORT = _env_int('PORT', 5000)

# 是否信任反向代理传来的 X-Forwarded-For / X-Real-IP。
# 默认不信任：没有反代时这两个头任何人都能伪造，会污染审计日志，
# 也会让基于 IP 的登录限流形同虚设。前面套了 Nginx/Caddy 再打开。
TRUST_PROXY = _env_bool('TRUST_PROXY')

# 强制下发 HSTS。仅在确认全链路 HTTPS 时打开，否则浏览器以后会强制跳 https。
ENABLE_HSTS = _env_bool('ENABLE_HSTS')

# ---------- HTTPS ----------
SSL_CERT_FILE = os.getenv('SSL_CERT_FILE')
SSL_KEY_FILE = os.getenv('SSL_KEY_FILE')

# ---------- 账号 ----------
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

JWT_EXPIRATION = _env_int('JWT_EXPIRATION_HOURS', 5) * 60 * 60

# 单个请求体上限（MB）。上传大安装包需要放宽，但绝不能无限——否则一个请求就能写满磁盘。
MAX_UPLOAD_MB = _env_int('MAX_UPLOAD_MB', 512, minimum=1)

# ---------- 登录限流 ----------
LOGIN_MAX_FAILURES = _env_int('LOGIN_MAX_FAILURES', 8, minimum=1)
LOGIN_LOCK_SECONDS = _env_int('LOGIN_LOCK_SECONDS', 900, minimum=1)

# ---------- 存储 ----------
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', '/tmp/ansible_uploads')
DB_PATH = os.getenv('DB_PATH', 'db/ansible.db')

# ---------- 日志 ----------
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_FILE = os.getenv('LOG_FILE', 'logs/app.log')

# ---------- 巡检 ----------
PING_ENABLED = _env_bool('PING_ENABLED', default=True)
PING_INTERVAL = _env_int('PING_INTERVAL', 300, minimum=30)


def load_or_create_secret_key():
    """获取 Flask 密钥。

    优先级：环境变量 SECRET_KEY > 数据目录下的持久化文件 > 新生成并落盘。
    不这样做的话，未设置 SECRET_KEY 时每次重启都会换密钥，
    已签发的 JWT 全部失效（容器 restart 一下所有用户就被踢下线）。
    """
    env_key = os.getenv('SECRET_KEY')
    if env_key:
        return env_key

    key_file = os.getenv('SECRET_KEY_FILE', os.path.join('data', '.secret_key'))
    try:
        if os.path.exists(key_file):
            with open(key_file, 'r', encoding='utf-8') as fp:
                saved = fp.read().strip()
            if saved:
                return saved

        new_key = secrets.token_hex(32)
        os.makedirs(os.path.dirname(key_file) or '.', exist_ok=True)
        with open(key_file, 'w', encoding='utf-8') as fp:
            fp.write(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        # 此处 app 尚未创建，只能用标准 logging
        logging.getLogger(__name__).warning(
            "未设置 SECRET_KEY，已生成随机密钥并保存到 %s（重启后复用）。"
            "多副本部署请显式设置 SECRET_KEY。", key_file
        )
        return new_key
    except OSError:
        # 只读文件系统等异常场景：退回进程内随机密钥，保证能启动
        return secrets.token_hex(32)


SECRET_KEY = load_or_create_secret_key()
JWT_SECRET = SECRET_KEY

"""蓝图注册表。

每个业务模块一个蓝图，URL 路径仍写完整前缀（/api/hosts 等），
因为前端接口地址是硬编码的，改动会直接破坏兼容性。

新增模块：写好 xxx.py 里的 bp，在这里 import 并加入 BLUEPRINTS。
"""

from . import (
    auth,
    execute,
    files,
    hosts,
    logs,
    playbooks,
    terminal,
    users,
)

# frontend 是 catch-all 路由（/<path:path>），放最后注册
from . import frontend

BLUEPRINTS = (
    auth.bp,
    hosts.bp,
    execute.bp,
    files.bp,
    terminal.bp,
    logs.bp,
    users.bp,
    playbooks.bp,
    frontend.bp,
)


def register_blueprints(app):
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

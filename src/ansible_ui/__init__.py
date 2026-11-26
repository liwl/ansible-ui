"""Ansible Web 管理面板 —— 后端包入口。

导入本包即得到一个配置完毕的 Flask 应用：请求钩子、错误处理器、蓝图全部注册好。

    启动：python -m ansible_ui
"""

from . import errors as _errors  # noqa: F401  导入即注册 413/404/500 处理器
from . import middleware as _middleware  # noqa: F401  导入即注册请求钩子
from .api import register_blueprints
from .extensions import app

register_blueprints(app)

__all__ = ['app']

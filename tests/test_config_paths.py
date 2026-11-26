"""静态目录定位的回归测试。

这个点踩过一次：源码布局是 <根>/src/ansible_ui，镜像里是 /app/ansible_ui，
两者深度不同。用固定 parent 层数推导时本地通过、容器里算成 /public，
表现是「首页 500 但日志里什么都没有」。所以必须按真实目录结构验证两种布局。

注意：这里按文件路径直接加载 config.py，不走 `import ansible_ui`——
包的 __init__ 会连带导入 ansible，而本测试要保持零依赖（标准库即可运行）。
"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / 'src' / 'ansible_ui' / 'config.py'

# config 模块级会读取环境变量，给个最小可运行环境
os.environ.setdefault('SECRET_KEY', 'test-only-key-not-used-in-production')

_spec = importlib.util.spec_from_file_location('ansible_ui_config_under_test', CONFIG_PATH)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)
resolve_static_dir = config.resolve_static_dir


class StaticDirTest(unittest.TestCase):
    def setUp(self):
        # 确保不受外部 STATIC_DIR 覆盖影响
        self._env_backup = os.environ.pop('STATIC_DIR', None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        if self._env_backup is not None:
            os.environ['STATIC_DIR'] = self._env_backup

    def _make(self, package_rel, with_index=True):
        """按给定相对路径造包目录，并在项目根放 public/index.html。"""
        pkg = self.root / package_rel
        pkg.mkdir(parents=True)
        public = self.root / 'public'
        public.mkdir(exist_ok=True)
        if with_index:
            (public / 'index.html').write_text('<html></html>', encoding='utf-8')
        return pkg

    def test_source_layout(self):
        """源码布局：<根>/src/ansible_ui → 应命中 <根>/public（上两级）"""
        pkg = self._make('src/ansible_ui')
        self.assertEqual(resolve_static_dir(pkg), self.root / 'public')

    def test_container_layout(self):
        """容器布局：/app/ansible_ui → 应命中 /app/public（上一级）

        Dockerfile 里 COPY src/ ./ 把包直接放进 /app，
        这里用 <根>/app/ansible_ui 模拟同样的深度关系。
        """
        pkg = self._make('app/ansible_ui')
        self.assertEqual(resolve_static_dir(pkg), self.root / 'public')

    def test_env_override_wins(self):
        pkg = self._make('app/ansible_ui')
        os.environ['STATIC_DIR'] = str(self.root / 'custom')
        try:
            self.assertEqual(resolve_static_dir(pkg), self.root / 'custom')
        finally:
            os.environ.pop('STATIC_DIR', None)

    def test_empty_public_still_points_to_public(self):
        """public 存在但缺 index.html：返回该目录本身，便于报错时指对位置"""
        pkg = self._make('app/ansible_ui', with_index=False)
        resolved = resolve_static_dir(pkg)
        self.assertEqual(resolved, self.root / 'public')
        self.assertFalse((resolved / 'index.html').exists())


if __name__ == '__main__':
    unittest.main()

"""路由表回归测试（零依赖，只用标准库）。

前端接口地址是硬编码的，后端重构最容易犯的错就是悄悄改了某个路径或方法。
本测试把 41 条路由固化成快照，任何增删改都会失败，逼迫改动方确认影响面。

    python -m unittest discover tests
    # 或
    python -m pytest tests

接口有意变更时：更新 tests/routes_snapshot.txt 并同步前端。
"""

import ast
import pathlib
import unittest

PKG = pathlib.Path(__file__).resolve().parents[1] / 'src' / 'ansible_ui'
SNAPSHOT = pathlib.Path(__file__).with_name('routes_snapshot.txt')


def collect_routes():
    """从蓝图模块里静态提取 (路径, 方法, 处理函数, defaults)。"""
    rows = set()
    for py in sorted((PKG / 'api').glob('*.py')):
        for node in ast.parse(py.read_text(encoding='utf-8')).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                if dec.func.attr != 'route' or not dec.args:
                    continue
                if not isinstance(dec.args[0], ast.Constant):
                    continue
                path = dec.args[0].value
                defaults, methods = '', ['GET']
                for kw in dec.keywords:
                    if kw.arg == 'defaults':
                        defaults = ast.unparse(kw.value)
                    if kw.arg == 'methods':
                        methods = sorted(ast.literal_eval(kw.value))
                rows.add((path, ','.join(methods), node.name, defaults))
    return rows


def load_snapshot():
    rows = set()
    for line in SNAPSHOT.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        path, methods, func, defaults = line.split('|')
        rows.add((path, methods, func, defaults))
    return rows


class RouteTableTest(unittest.TestCase):
    def test_routes_match_snapshot(self):
        actual = collect_routes()
        expected = load_snapshot()

        removed = expected - actual
        added = actual - expected

        message = []
        if removed:
            message.append('接口被删除或改名（前端可能已经坏掉）:')
            message.extend(f'  - {r}' for r in sorted(removed))
        if added:
            message.append('新增接口（请同步快照与前端）:')
            message.extend(f'  + {r}' for r in sorted(added))
        self.assertFalse(message, '\n'.join(message))

    def test_no_duplicate_route(self):
        """同一路径 + 方法不能注册两次，否则 Flask 会静默用最后一个。"""
        seen = {}
        for path, methods, func, _ in collect_routes():
            for method in methods.split(','):
                key = (path, method)
                self.assertNotIn(
                    key, seen,
                    f'路由冲突: {method} {path} 同时由 {seen.get(key)} 和 {func} 处理',
                )
                seen[key] = func


if __name__ == '__main__':
    unittest.main()

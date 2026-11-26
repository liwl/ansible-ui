"""主机巡检：一次性执行 + 定时调度。

巡检会调用 ansible ping，属于 IO 密集操作，因此放在独立 daemon 线程里跑，
不能阻塞请求线程。
"""
import threading
import time

from .. import config
from ..extensions import ansible, app, db


def run_patrol():
    """执行一次全主机巡检，把结果写回 hosts 表并返回汇总。"""
    hosts = db.get_hosts()
    if not hosts:
        return {'checked': 0, 'online': 0, 'offline': 0, 'failed': 0, 'statuses': {}}

    results = None
    try:
        results = ansible.execute_ping(hosts)
    except Exception as e:
        # Windows 等非 Linux 控制节点上 ansible 可能不可用，不能让巡检线程崩掉
        app.logger.error(f"巡检执行失败: {e}")

    status_map = {}
    for host in hosts:
        address = host['address']
        if results is None:
            status_map[host['id']] = 'failed'
        elif address in results['success']:
            status_map[host['id']] = 'success'
        elif address in results['unreachable']:
            status_map[host['id']] = 'unreachable'
        else:
            status_map[host['id']] = 'failed'

    db.update_hosts_status(status_map)

    online = sum(1 for s in status_map.values() if s == 'success')
    offline = sum(1 for s in status_map.values() if s == 'unreachable')
    failed = sum(1 for s in status_map.values() if s == 'failed')
    app.logger.info(f"巡检完成: 共 {len(hosts)} 台, 在线 {online}, 离线 {offline}, 异常 {failed}")
    return {
        'checked': len(hosts),
        'online': online,
        'offline': offline,
        'failed': failed,
        'statuses': status_map,
    }


_patrol_started = False


def start_patrol_scheduler():
    """启动定时巡检守护线程（进程内只启动一次）。"""
    global _patrol_started
    if _patrol_started:
        return
    if not config.PING_ENABLED:
        app.logger.info("定时巡检已禁用 (PING_ENABLED=false)")
        return
    # 下限 30 秒的保护已由 config._env_int 完成
    interval = config.PING_INTERVAL

    def loop():
        while True:
            # 启动后先等一个周期再首次巡检，避免服务刚起来就阻塞
            time.sleep(interval)
            try:
                run_patrol()
            except Exception as e:
                app.logger.error(f"定时巡检线程异常: {e}")

    threading.Thread(target=loop, daemon=True, name='patrol-scheduler').start()
    _patrol_started = True
    app.logger.info(f"定时巡检已启动, 间隔 {interval} 秒")

"""SSH / SFTP 连接管理。

终端、文件管理、主机巡检都从这里拿连接，避免各处各写一遍 paramiko 参数。
"""
from contextlib import contextmanager

import paramiko


@contextmanager
def ssh_client_for_host(host, timeout=10):
    """为指定主机创建并管理SSH连接"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_args = {
        'hostname': host['address'],
        'port': host['port'],
        'username': host['username'],
        'timeout': timeout
    }
    if host['auth_method'] == 'password':
        connect_args['password'] = host['password']

    ssh.connect(**connect_args)
    try:
        yield ssh
    finally:
        ssh.close()


@contextmanager
def sftp_client_for_host(host, timeout=10):
    """为指定主机创建并管理SFTP连接"""
    with ssh_client_for_host(host, timeout=timeout) as ssh:
        with ssh.open_sftp() as sftp:
            yield sftp

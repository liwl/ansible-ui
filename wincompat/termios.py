"""Minimal ``termios`` shim for running ansible on Windows.

Why this is needed
------------------
``ansible.executor.task_executor`` does ``import pty``; Python's stdlib ``pty``
imports ``tty``, and ``tty.py`` starts with::

    from termios import *

    def setraw(fd, when=TCSAFLUSH): ...

``TCSAFLUSH`` is evaluated as a *default argument at import time*, so a termios
module that lacks the constant raises ``NameError: name 'TCSAFLUSH' is not
defined`` before any connection is made. That is the error seen when running
巡检 / playbook / 文件上传 on Windows.

This module therefore only needs to make ``from termios import *`` yield the
usual public names, and provide harmless no-op implementations for the calls
ansible reaches at runtime (``tcflush`` during paramiko SSH setup).
"""

# --- 行为常量（取值与 Linux 保持一致，仅用于让 import 与默认参数成立）---
TCSANOW = 0
TCSADRAIN = 1
TCSAFLUSH = 2

# --- 输入/输出模式标志 ---
IGNBRK = 0o0000001
BRKINT = 0o0000002
PARMRK = 0o0000010
ISTRIP = 0o0000040
INLCR = 0o0000100
IGNCR = 0o0000200
ICRNL = 0o0000400
IXON = 0o0002000
IXANY = 0o0004000
IXOFF = 0o0010000

OPOST = 0o0000001
ONLCR = 0o0000004

ISIG = 0o0000001
ICANON = 0o0000002
ECHO = 0o0000010
ECHOE = 0o0000020
ECHOK = 0o0000040
ECHONL = 0o0000100
NOFLSH = 0o0000200
IEXTEN = 0o0100000

CSIZE = 0o0000060
CS8 = 0o0000060
PARENB = 0o0000400
PARODD = 0o0001000

# --- 刷新队列 ---
TCIFLUSH = 0
TCOFLUSH = 1
TCIOFLUSH = 2

# --- 波特率 ---
B0 = 0o0000000
B2400 = 0o0000013
B4800 = 0o0000014
B9600 = 0o0000015
B19200 = 0o0000016
B38400 = 0o0000017

# --- 特殊控制字符下标 ---
VINTR = 0
VQUIT = 1
VERASE = 2
VKILL = 3
VEOF = 4
VTIME = 5
VMIN = 6
VSTART = 8
VSTOP = 9
VSUSP = 10

# --- ioctl ---
TIOCGWINSZ = 0x5413
TIOCSWINSZ = 0x5414


class error(Exception):
    """termios.error，保持与真模块同名。"""


def tcgetattr(fd):
    """返回一个可被 ansible 索引/修改的 7 元组结构。

    ansible 会做 ``new = tcgetattr(fd); new[3] &= ~ICANON``，因此第 4 个元素
    必须是可变整数，第 7 个元素是控制字符数组。
    """
    return [0, 0, 0, 0, B38400, B38400, [b"\x00"] * 32]


def tcsetattr(fd, when, attributes):
    return None


def tcdrain(fd):
    return None


def tcflush(fd, queue):
    return None


def tcflow(fd, action):
    return None


def tcsendbreak(fd, duration):
    return None


def cfgetispeed(attributes):
    return B38400


def cfgetospeed(attributes):
    return B38400


def cfsetispeed(attributes, speed):
    return attributes


def cfsetospeed(attributes, speed):
    return attributes

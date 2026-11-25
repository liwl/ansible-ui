"""Minimal fcntl shim for running ansible imports on Windows (local verification only)."""

F_GETFL = 3
F_SETFL = 4
F_SETLK = 6
F_SETLKW = 7
F_GETLK = 5
F_RDLCK = 0
F_WRLCK = 1
F_UNLCK = 2
LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def fcntl(fd, op, arg=0):
    if op == F_GETFL:
        return 0
    return 0


def flock(fd, operation):
    return None


def lockf(fd, operation, length=0, start=0, whence=0):
    return None


def ioctl(fd, opt, arg=0, mutate_flag=True):
    return None

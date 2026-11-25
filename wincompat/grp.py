"""Minimal grp shim for running ansible imports on Windows (local verification only)."""

from collections import namedtuple

struct_group = namedtuple("struct_group", "gr_name gr_passwd gr_gid gr_mem")


def getgrnam(name):
    if name in ("root", "0", 0):
        return struct_group("root", "x", 0, [])
    return struct_group(str(name), "x", 0, [])


def getgrgid(gid):
    if gid in (0, "0", "root"):
        return struct_group("root", "x", 0, [])
    return struct_group(str(gid), "x", int(gid) if str(gid).isdigit() else 0, [])


def getgrall():
    return [getgrgid(0)]

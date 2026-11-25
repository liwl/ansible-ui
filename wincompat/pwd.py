"""Minimal pwd shim for running ansible imports on Windows (local verification only)."""

from collections import namedtuple

struct_passwd = namedtuple(
    "struct_passwd", "pw_name pw_passwd pw_uid pw_gid pw_gecos pw_dir pw_shell"
)


def getpwnam(name):
    if name in ("root", "0", 0):
        return struct_passwd("root", "x", 0, 0, "root", "/root", "/bin/sh")
    return struct_passwd(str(name), "x", 0, 0, "", "/", "/bin/sh")


def getpwuid(uid):
    if uid in (0, "0", "root"):
        return getpwnam("root")
    return struct_passwd(str(uid), "x", int(uid) if str(uid).isdigit() else 0, 0, "", "/", "/bin/sh")


def getpwall():
    return [getpwnam("root")]

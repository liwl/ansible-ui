"""通用小工具。"""
import os


def allowed_file(filename):
    """检查文件是否允许上传，当前策略是允许所有文件"""
    return True


def create_required_directories():
    """创建必要的目录"""
    directories = ['logs', 'data']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

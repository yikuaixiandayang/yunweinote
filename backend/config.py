#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局配置：路径、app_data 全局状态、user_data 读写。

各 router 模块共享这些配置，避免在 main.py 和 router 之间传递。
"""

import os
import json

# ───────── 路径配置 ─────────
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
NOTES_DIR = os.path.join(PROJECT_ROOT, "notes")
REFERENCES_DIR = os.path.join(PROJECT_ROOT, "references")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
DATA_DIR = os.path.join(APP_DIR, "data")
FRONTEND_DIST = os.path.join(APP_DIR, "frontend", "dist")
USER_DATA_FILE = os.path.join(DATA_DIR, "user_data.json")


# ───────── 应用数据 ─────────
app_data: dict = {"user_data": {}}


def load_user_data() -> None:
    """从磁盘加载用户数据到内存。启动时调用。"""
    global app_data
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, encoding="utf-8") as f:
                app_data["user_data"] = json.load(f)
        except (json.JSONDecodeError, OSError):
            app_data["user_data"] = {}
    else:
        app_data["user_data"] = {}


def save_user_data(data: dict) -> None:
    """原子化持久化用户数据：写临时文件 -> 备份上一版 -> 原子改名替换。"""
    global app_data
    app_data["user_data"] = data
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USER_DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.path.exists(USER_DATA_FILE):
        try:
            os.replace(USER_DATA_FILE, USER_DATA_FILE + ".bak")
        except OSError:
            pass
    os.replace(tmp, USER_DATA_FILE)

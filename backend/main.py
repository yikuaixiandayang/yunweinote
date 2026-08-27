#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastAPI 后端入口：只负责组装（路由注册、静态文件、启动逻辑）。

路由实现拆分在 routers/ 目录：
  - routers/notes.py   笔记索引 / 搜索 / 推荐
  - routers/scripts.py 脚本库
  - routers/folders.py 项目文件夹
  - routers/agent.py   AI Agent（含 SSE 流式对话）

共享配置（路径、user_data）在 config.py；
Agent 记忆持久化（SQLite）在 db.py。
"""

import os
import sys

# 添加 backend 目录到 sys.path，保证以任何工作目录启动都能 import 同级模块
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import config
from config import DATA_DIR, NOTES_DIR, REFERENCES_DIR, FRONTEND_DIST

# 模块加载时即读取用户数据（确保 uvicorn main:app 方式启动也能拿到历史数据）
config.load_user_data()

# 初始化 SQLite 记忆库（data/agent_memory.db）
import db
db.init_db(DATA_DIR)

# Agent 配置注入（触发 routers/agent.py 的启动同步）
from routers import agent, appearance, folders, notes, scripts  # noqa: E402

app = FastAPI(title="运维笔记知识库 API", version="1.1.0")

# 注册 API 路由（统一 /api 前缀）
app.include_router(notes.router, prefix="/api")
app.include_router(scripts.router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(appearance.router, prefix="/api")


# ==================== SPA 页面与静态文件 ====================

def _serve_index() -> HTMLResponse:
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    # index.html 禁止缓存：前端重新构建后资源文件名会变，
    # 若浏览器（尤其 Edge）缓存了旧 index.html，会一直加载旧版 JS，
    # 导致已删除的旧逻辑（如标题闪烁）继续运行。assets/ 下带 hash 的文件可安全长缓存。
    no_cache = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content, headers=no_cache)
    return HTMLResponse("<h1>前端尚未构建</h1><p>请先构建前端：cd frontend && npm run build</p>", headers=no_cache)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _serve_index()


if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")


@app.get("/files/{path:path}")
async def serve_note_files(path: str):
    # 优先在 notes/ 找，找不到再去 references/（PDF 等参考资料）
    for root in (NOTES_DIR, REFERENCES_DIR):
        file_path = os.path.join(root, path)
        real_root = os.path.realpath(root)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(real_root + os.sep) and real_path != real_root:
            continue
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
    return JSONResponse({"error": "文件不存在"}, status_code=404)


# ==================== 入口 ====================

if __name__ == "__main__":
    # reload 默认关闭：开启后 uvicorn 会监听整个目录，notes/ 一有改动就重启，
    # 既产生多余子进程（停服要 taskkill /T），又容易让内存缓存变陈旧。
    # 需要开发热重载时设置环境变量 KB_DEV=1 再启动。
    dev_reload = os.environ.get("KB_DEV") == "1"
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=dev_reload)

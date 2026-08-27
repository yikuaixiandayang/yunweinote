#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目文件夹资源扫描模块：将项目根目录下所有一级文件夹动态纳入展示体系。

设计目标（全自动化）：
  1. 零配置：扫描 PROJECT_ROOT 下所有一级文件夹，新增/删除文件夹自动反映，无需改代码。
  2. 通用化：任何文件夹都自动生成元数据（大小/文件数/类型分布/README 摘要）。
  3. 安全：所有对外路径都经过 realpath 前缀校验，防路径遍历。
  4. 内容变动自动同步：每次请求实时扫描（轻量），不依赖长期缓存。

排除规则：
  - 顶层排除：系统/工具目录（.git/.workbuddy/.trae 等）与超大依赖目录（node_modules*）
  - 内容层跳过：构建产物与缓存（node_modules/_env/dist/__pycache__/.vite 等），避免把垃圾统计进文件夹规模
"""

import os
import datetime
import time
import threading

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)

# 顶层排除：扫描一级文件夹时直接跳过
TOP_LEVEL_SKIP = {
    ".git", ".trae", ".workbuddy", "node_modules", "node_modules_stale_bak",
    "node_modules_old", ".dsh",
}
# 内容层跳过：递归统计/列文件时跳过的子目录（构建产物与缓存）
CONTENT_SKIP = {
    "node_modules", "_env", "venv", ".venv", "__pycache__", "dist", "build",
    ".vite", ".cache", ".git", ".idea", ".vscode", "target", ".next",
    ".workbuddy", "bin", "obj",
}
# 文本预览扩展名
TEXT_EXTS = {
    ".md", ".txt", ".py", ".sh", ".ps1", ".bat", ".cmd", ".js", ".ts", ".vue",
    ".json", ".yml", ".yaml", ".conf", ".cfg", ".ini", ".toml", ".xml", ".html",
    ".css", ".sql", ".log", ".csv", ".env", ".gitignore", ".dockerfile",
}
# 图片扩展名（预览时显示类型图标）
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}

# 类型推断规则：根据内容占比给文件夹打"类型标签"
TYPE_RULES = [
    ("笔记文档", {".md"}, 0.35),
    ("脚本库", {".sh", ".py", ".ps1", ".bat", ".cmd"}, 0.30),
    ("资料库", DOC_EXTS, 0.30),
    ("图片素材", IMAGE_EXTS, 0.40),
    ("配置文件", {".json", ".yml", ".yaml", ".conf", ".ini", ".toml"}, 0.35),
]


def _safe_join(root: str, rel: str) -> str:
    """安全拼接：rel 必须落在 root 内，防路径遍历。"""
    real_root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, rel))
    if target != real_root and not target.startswith(real_root + os.sep):
        raise ValueError("非法路径")
    return target


def _scan_dir_stats(folder: str, max_files: int = 50000) -> dict:
    """递归统计文件夹：总大小、文件数、目录数、扩展名分布、最新修改时间。
    跳过 CONTENT_SKIP 中的子目录；文件数超过 max_files 提前截断。"""
    total_size = 0
    file_count = 0
    dir_count = 0
    latest_ts = 0
    ext_stats = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in CONTENT_SKIP and not d.startswith("."))
        dir_count += len(dirs)
        for f in files:
            fp = os.path.join(root, f)
            try:
                size = os.path.getsize(fp)
                ts = os.path.getmtime(fp)
            except OSError:
                continue
            total_size += size
            file_count += 1
            latest_ts = max(latest_ts, ts)
            ext = os.path.splitext(f)[1].lower() or "(无扩展名)"
            ext_stats[ext] = ext_stats.get(ext, 0) + 1
            if file_count >= max_files:
                break
        if file_count >= max_files:
            break
    return {
        "totalSize": total_size,
        "fileCount": file_count,
        "dirCount": dir_count,
        "latestTs": latest_ts,
        "extStats": dict(sorted(ext_stats.items(), key=lambda x: -x[1])[:12]),
    }


def _read_readme(folder: str) -> dict:
    """读取文件夹 README.md（大小写不敏感），返回 {exists, excerpt}。"""
    for cand in ("README.md", "readme.md", "Readme.md", "README.MD"):
        p = os.path.join(folder, cand)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    text = f.read(2000)
                # 去掉 markdown 标题符号，截取摘要
                lines = [ln.lstrip("# >").strip() for ln in text.splitlines() if ln.strip()]
                excerpt = " ".join(lines[:6])[:300]
                return {"exists": True, "name": cand, "excerpt": excerpt}
            except OSError:
                continue
    return {"exists": False, "name": None, "excerpt": ""}


# README 变体（存在即视为"项目"）
README_VARIANTS = ("README.md", "readme.md", "Readme.md", "README.MD",
                   "DEPLOYMENT.md", "deployment.md", "CHANGELOG.md", "INDEX.md")


def _infer_type(folder: str, stats: dict, readme: dict) -> str:
    """根据内容分布推断文件夹类型标签。
    优先级：README/说明文档 → md 绝对数量 → 占比规则。"""
    if readme["exists"]:
        return "项目"
    # 常见说明文档变体（如 DEPLOYMENT.md / INDEX.md）→ 项目
    for cand in README_VARIANTS:
        if os.path.isfile(os.path.join(folder, cand)):
            return "项目"
    # md 绝对数量优先：notes 含大量图片，占比被稀释，但 md 数量仍说明是笔记库
    if stats["extStats"].get(".md", 0) >= 2:
        return "笔记文档"
    total = stats["fileCount"] or 1
    for label, exts, ratio in TYPE_RULES:
        hit = sum(c for e, c in stats["extStats"].items() if e in exts)
        if hit / total >= ratio and hit >= 3:
            return label
    return "数据/其他"


def _fmt_size(b: int) -> str:
    if b >= 1024 * 1024:
        return f"{b/1024/1024:.1f} MB"
    if b >= 1024:
        return f"{b/1024:.1f} KB"
    return f"{b} B"


# ── scan_folders 结果缓存 ──
# 全量递归扫描 11 个一级文件夹耗时约 1.2s（demos/desk/references 是大头），
# 每次请求都重扫会导致 /folders 列表加载慢 + 30s 定时刷新白白消耗。
# 用内存缓存 + 60s TTL：60 秒内复用上次结果，文件增删最多延迟 60 秒反映。
# "立即刷新"按钮可通过 force=True 绕过缓存强制重扫。
_SCAN_CACHE = {"data": None, "ts": 0.0, "lock": threading.Lock()}
_SCAN_TTL = 60.0  # 秒


def scan_folders(force: bool = False) -> list:
    """扫描项目根所有一级文件夹，返回元数据列表（已按名称排序）。

    Args:
        force: True 时绕过缓存强制重新扫描（供"立即刷新"按钮调用）。
    """
    if not force:
        with _SCAN_CACHE["lock"]:
            cached = _SCAN_CACHE["data"]
            if cached is not None and (time.time() - _SCAN_CACHE["ts"]) < _SCAN_TTL:
                return cached
    result = _scan_folders_impl()
    with _SCAN_CACHE["lock"]:
        _SCAN_CACHE["data"] = result
        _SCAN_CACHE["ts"] = time.time()
    return result


def _scan_folders_impl() -> list:
    """scan_folders 的实际扫描实现（无缓存）。"""
    result = []
    if not os.path.isdir(PROJECT_ROOT):
        return result
    for name in sorted(os.listdir(PROJECT_ROOT)):
        fp = os.path.join(PROJECT_ROOT, name)
        if not os.path.isdir(fp):
            continue
        if name in TOP_LEVEL_SKIP or name.startswith("."):
            continue
        stats = _scan_dir_stats(fp)
        readme = _read_readme(fp)
        mtime = datetime.datetime.fromtimestamp(stats["latestTs"]).strftime("%Y-%m-%d") \
            if stats["latestTs"] else "-"
        result.append({
            "name": name,
            "type": _infer_type(fp, stats, readme),
            "size": _fmt_size(stats["totalSize"]),
            "sizeBytes": stats["totalSize"],
            "fileCount": stats["fileCount"],
            "dirCount": stats["dirCount"],
            "mtime": mtime,
            "extStats": stats["extStats"],
            "readme": readme,
        })
    return result


def folder_tree(name: str, max_depth: int = 3, max_items: int = 200) -> dict:
    """返回某文件夹的内容树（最多 max_depth 层，每层最多 max_items 项）。
    返回 {name, depth, items: [{kind: dir|file, name, rel, ...}]}"""
    folder = _safe_join(PROJECT_ROOT, name)
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"文件夹 '{name}' 不存在")

    def _build(dirpath: str, rel: str, depth: int) -> list:
        if depth > max_depth:
            return [{"kind": "more", "name": "...", "rel": rel}]
        items = []
        try:
            entries = sorted(os.scandir(dirpath), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return items
        for e in entries:
            if len(items) >= max_items:
                items.append({"kind": "more", "name": f"... 还有更多（限制 {max_items} 项）", "rel": rel})
                break
            e_rel = (rel + "/" + e.name) if rel else e.name
            if e.is_dir(follow_symlinks=False):
                if e.name in CONTENT_SKIP or e.name.startswith("."):
                    continue
                items.append({"kind": "dir", "name": e.name, "rel": e_rel,
                              "children": _build(e.path, e_rel, depth + 1)})
            else:
                try:
                    size = os.path.getsize(e.path)
                    ts = os.path.getmtime(e.path)
                except OSError:
                    continue
                ext = os.path.splitext(e.name)[1].lower()
                items.append({
                    "kind": "file", "name": e.name, "rel": e_rel,
                    "size": _fmt_size(size),
                    "ext": ext,
                    "mtime": datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                    "preview": ext in TEXT_EXTS,
                    "image": ext in IMAGE_EXTS,
                })
        return items

    items = _build(folder, "", 1)
    return {"name": name, "items": items}


def folder_file(name: str, path: str, max_bytes: int = 200_000) -> dict:
    """读取文件夹内文本文件内容（预览用，截断到 max_bytes）。"""
    folder = _safe_join(PROJECT_ROOT, name)
    fp = _safe_join(folder, path)
    if not os.path.isfile(fp):
        raise FileNotFoundError("文件不存在")
    ext = os.path.splitext(fp)[1].lower()
    is_text = ext in TEXT_EXTS
    content = ""
    if is_text:
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                content = f.read(max_bytes)
        except OSError:
            content = ""
    return {
        "name": os.path.basename(fp),
        "rel": path,
        "ext": ext,
        "isText": is_text,
        "truncated": len(content) >= max_bytes,
        "content": content,
        "size": _fmt_size(os.path.getsize(fp)),
    }


def folder_asset(name: str, path: str) -> str:
    """Return a safe absolute path for browser-previewable binary assets."""
    folder = _safe_join(PROJECT_ROOT, name)
    fp = _safe_join(folder, path)
    if not os.path.isfile(fp):
        raise FileNotFoundError("文件不存在")
    ext = os.path.splitext(fp)[1].lower()
    if ext not in IMAGE_EXTS and ext not in {".pdf"}:
        raise ValueError("该文件类型不支持在线预览")
    return fp


def folder_download(name: str, path: str) -> str:
    """Return a safe absolute path for downloading (any file type)."""
    folder = _safe_join(PROJECT_ROOT, name)
    fp = _safe_join(folder, path)
    if not os.path.isfile(fp):
        raise FileNotFoundError("文件不存在")
    return fp


def folder_readme(name: str) -> dict:
    """返回文件夹 README 的完整内容。"""
    folder = _safe_join(PROJECT_ROOT, name)
    for cand in ("README.md", "readme.md", "Readme.md", "README.MD"):
        p = os.path.join(folder, cand)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="ignore") as f:
                return {"exists": True, "name": cand, "content": f.read()}
    return {"exists": False, "name": None, "content": ""}

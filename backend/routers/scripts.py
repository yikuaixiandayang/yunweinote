#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脚本库 API 路由。"""

import os
import re
import subprocess
from fastapi import Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi import APIRouter, Body

from config import SCRIPTS_DIR

_SCRIPT_EXTS = {".sh", ".py", ".ps1", ".bat", ".conf", ".yml", ".yaml"}
_META_PATTERNS = {
    "name": re.compile(r"脚本名称：(.+)"),
    "purpose": re.compile(r"用途：(.+)"),
    "source_note": re.compile(r"来源笔记：(.+)"),
    "usage": re.compile(r"用法：\n((?:#\s.+\n)+)", re.MULTILINE),
    "update": re.compile(r"更新：(\d{4}-\d{2}-\d{2})"),
}


def _parse_script_meta(filepath: str, rel_path: str) -> dict:
    meta = {
        "name": os.path.basename(filepath),
        "relPath": rel_path,
        "category": rel_path.split("/")[0] if "/" in rel_path else "misc",
        "purpose": "",
        "sourceNote": "",
        "usage": "",
        "update": "",
        "size": os.path.getsize(filepath),
        "ext": os.path.splitext(filepath)[1].lower(),
    }
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            head = f.read(2000)
    except OSError:
        return meta
    for key, pat in _META_PATTERNS.items():
        m = pat.search(head)
        if m:
            val = m.group(1).strip()
            if key == "usage":
                val = "\n".join(line.lstrip("# ").rstrip() for line in val.strip().split("\n"))
            meta[{"name": "name", "purpose": "purpose", "source_note": "sourceNote",
                  "usage": "usage", "update": "update"}[key]] = val
    return meta


def _scan_scripts() -> list:
    if not os.path.isdir(SCRIPTS_DIR):
        return []
    result = []
    for root, dirs, files in os.walk(SCRIPTS_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in _SCRIPT_EXTS:
                continue
            if f.lower() == "readme.md":
                continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, SCRIPTS_DIR).replace("\\", "/")
            result.append(_parse_script_meta(fp, rel))
    result.sort(key=lambda x: (x["category"], x["name"]))
    return result


router = APIRouter(tags=["scripts"])


@router.get("/scripts")
async def api_scripts():
    scripts = _scan_scripts()
    # 附带用户自定义备注
    try:
        import db as _db
        notes = _db.get_notes_bulk("script:")
        for s in scripts:
            s["note"] = notes.get(f"script:{s['relPath']}", "")
    except Exception:
        for s in scripts:
            s.setdefault("note", "")
    return {"scripts": scripts, "root": "scripts"}


@router.put("/script-note/{path:path}")
async def api_script_note(path: str, payload: dict = Body(default={})):
    """保存/更新脚本自定义备注。body={"note": "..."}。"""
    import db as _db
    note = (payload or {}).get("note", "")
    if not isinstance(note, str) or len(note) > 2000:
        return JSONResponse({"error": "备注内容无效（最长 2000 字）"}, status_code=400)
    _db.set_note(f"script:{path}", note)
    return {"ok": True, "note": note}


@router.delete("/script-note/{path:path}")
async def api_script_note_delete(path: str):
    """清空脚本自定义备注。"""
    import db as _db
    _db.delete_note(f"script:{path}")
    return {"ok": True}


@router.get("/script/{path:path}")
async def api_script_detail(path: str):
    file_path = os.path.join(SCRIPTS_DIR, path)
    real_root = os.path.realpath(SCRIPTS_DIR)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        return JSONResponse({"error": "禁止访问脚本目录外的文件"}, status_code=403)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return JSONResponse({"error": "脚本不存在"}, status_code=404)
    meta = _parse_script_meta(file_path, path)
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            meta["content"] = f.read()
    except OSError as e:
        return JSONResponse({"error": f"读取失败: {e}"}, status_code=500)
    try:
        import db as _db
        meta["note"] = _db.get_note(f"script:{path}")
    except Exception:
        meta.setdefault("note", "")
    return meta


@router.get("/script-locate/{path:path}")
async def api_script_locate(path: str):
    file_path = os.path.join(SCRIPTS_DIR, path)
    real_root = os.path.realpath(SCRIPTS_DIR)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        return JSONResponse({"error": "禁止访问脚本目录外的文件"}, status_code=403)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return JSONResponse({"error": "脚本不存在"}, status_code=404)
    try:
        subprocess.Popen(
            ["explorer", "/select,", os.path.abspath(file_path)],
            shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return JSONResponse({"ok": True, "path": os.path.abspath(file_path)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/script-download/{path:path}")
async def api_script_download(path: str):
    file_path = os.path.join(SCRIPTS_DIR, path)
    real_root = os.path.realpath(SCRIPTS_DIR)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        return JSONResponse({"error": "禁止访问脚本目录外的文件"}, status_code=403)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return JSONResponse({"error": "脚本不存在"}, status_code=404)
    filename = os.path.basename(file_path)
    return FileResponse(
        file_path, filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

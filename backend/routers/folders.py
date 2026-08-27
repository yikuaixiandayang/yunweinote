#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目文件夹资源 API 路由。"""

from fastapi.responses import JSONResponse, FileResponse
from fastapi import APIRouter, Body

from config import PROJECT_ROOT
from folder_scan import (scan_folders, folder_tree, folder_file, folder_asset,
                         folder_readme, folder_download)

router = APIRouter(tags=["folders"])


@router.get("/folders")
async def api_folders(force: bool = False):
    # force=true 绕过 60s 缓存强制重扫（供前端"立即刷新"按钮调用）
    folders = scan_folders(force=force)
    # 附带每个文件夹的 AI 描述缓存（无则 aiDoc=null）
    try:
        import db as _db
        for fm in folders:
            fm["aiDoc"] = _db.get_folder_doc(fm["name"])
            fm["note"] = _db.get_note(f"folder:{fm['name']}")
    except Exception:
        for fm in folders:
            fm.setdefault("aiDoc", None)
            fm.setdefault("note", "")
    return {"folders": folders, "root": PROJECT_ROOT}


@router.put("/folder/{name}/note")
async def api_folder_note(name: str, payload: dict = Body(default={})):
    """保存/更新文件夹自定义备注。body={"note": "..."}。"""
    import db as _db
    note = (payload or {}).get("note", "")
    if not isinstance(note, str) or len(note) > 2000:
        return JSONResponse({"error": "备注内容无效（最长 2000 字）"}, status_code=400)
    _db.set_note(f"folder:{name}", note)
    return {"ok": True, "note": note}


@router.delete("/folder/{name}/note")
async def api_folder_note_delete(name: str):
    """清空文件夹自定义备注。"""
    import db as _db
    _db.delete_note(f"folder:{name}")
    return {"ok": True}


@router.get("/folder/{name}/tree")
async def api_folder_tree(name: str, depth: int = 3, limit: int = 200):
    try:
        data = folder_tree(name, max_depth=min(depth, 6), max_items=min(limit, 500))
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    # 附带每个文件/目录的用户自定义备注
    try:
        import db as _db
        prefix = f"folderfile:{name}/"
        notes = _db.get_notes_bulk(prefix)
        _attach_notes(data["items"], prefix, notes)
    except Exception:
        pass
    return data


def _attach_notes(items, prefix: str, notes: dict) -> None:
    """递归给树节点附加 note 字段。"""
    if not items:
        return
    for it in items:
        if it.get("kind") in ("dir", "file"):
            it["note"] = notes.get(prefix + it["rel"], "")
            if it.get("kind") == "dir" and it.get("children"):
                _attach_notes(it["children"], prefix, notes)


@router.put("/folder-file-note/{name}/{path:path}")
async def api_folder_file_note(name: str, path: str, payload: dict = Body(default={})):
    """保存/更新文件夹内文件（或子目录）的自定义备注。"""
    import db as _db
    note = (payload or {}).get("note", "")
    if not isinstance(note, str) or len(note) > 2000:
        return JSONResponse({"error": "备注内容无效（最长 2000 字）"}, status_code=400)
    # key 形如 folderfile:{name}/{path}
    _db.set_note(f"folderfile:{name}/{path}", note)
    return {"ok": True, "note": note}


@router.delete("/folder-file-note/{name}/{path:path}")
async def api_folder_file_note_delete(name: str, path: str):
    """清空文件夹内文件（或子目录）的自定义备注。"""
    import db as _db
    _db.delete_note(f"folderfile:{name}/{path}")
    return {"ok": True}


@router.get("/folder/{name}/file/{path:path}")
async def api_folder_file(name: str, path: str):
    try:
        return folder_file(name, path)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=403)


@router.get("/folder/{name}/asset/{path:path}")
async def api_folder_asset(name: str, path: str):
    try:
        return FileResponse(folder_asset(name, path))
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=403)


@router.get("/folder/{name}/download/{path:path}")
async def api_folder_download(name: str, path: str):
    """下载文件夹内任意文件（Content-Disposition: attachment 强制下载）。"""
    import os
    try:
        fp = folder_download(name, path)
        return FileResponse(
            fp,
            filename=os.path.basename(fp),
            content_disposition_type="attachment",
        )
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=403)


@router.get("/folder/{name}/readme")
async def api_folder_readme(name: str):
    try:
        return folder_readme(name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=403)

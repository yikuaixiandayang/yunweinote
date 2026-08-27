#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""笔记、搜索、推荐、Typora 修复 API 路由。"""

import os
import re
import json
import datetime
import subprocess
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import APIRouter

from config import (NOTES_DIR, DATA_DIR, FRONTEND_DIST, PROJECT_ROOT,
                    app_data, save_user_data)
from build_core import build_index, search_notes, invalidate_cache, detect_editors


# ============ 图片 URL 重写 ============

_IMG_MD = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
_IMG_TAG = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")')


def _is_abs_url(src: str) -> bool:
    if re.match(r'^[A-Za-z]:[\\/]', src):
        return True
    return src.startswith(("http://", "https://", "//", "data:", "/files", "/"))


def _rewrite_src(src: str, note_dir: str) -> str:
    if _is_abs_url(src):
        return src
    src = src.replace("\\", "/").lstrip("./")
    return f"/files/{note_dir}/{src}" if note_dir else f"/files/{src}"


def rewrite_image_urls(content: str, note_dir: str) -> str:
    def _md(m):
        return f'![{m.group(1)}]({_rewrite_src(m.group(2).strip(), note_dir)})'
    def _tag(m):
        return m.group(1) + _rewrite_src(m.group(2).strip(), note_dir) + m.group(3)
    content = _IMG_MD.sub(_md, content)
    content = _IMG_TAG.sub(_tag, content)
    return content


def strip_text(payload: dict) -> dict:
    """从 payload 中剥离 _text / search_blob 字段，只返回前端渲染需要的字段"""
    result = {}
    notes_stripped = []
    for n in payload.get("notes", []):
        n_copy = {k: v for k, v in n.items() if k not in ("_text", "search_blob")}
        notes_stripped.append(n_copy)
    result.update(payload)
    result["notes"] = notes_stripped
    return result


# ============ 路由 ============

router = APIRouter(tags=["notes"])


@router.get("/data")
async def api_data():
    payload = build_index()
    payload = strip_text(payload)
    payload["user_data"] = app_data.get("user_data", {})
    return JSONResponse(payload)


@router.get("/note")
async def api_note_list():
    payload = build_index()
    notes = payload["notes"]
    result = []
    for n in notes:
        result.append({
            "id": n["id"],
            "name": n["name"],
            "cat": n["cat"],
            "mtime": n["mtime"],
            "tags": n.get("tags", []),
            "size": n.get("size", ""),
            "fileurl": n.get("fileurl", ""),
        })
    return JSONResponse(result)


@router.get("/note/{name:path}")
async def api_note_read(name: str):
    note_path = os.path.join(NOTES_DIR, name)
    if not name.endswith(".md"):
        note_path += ".md"
    real_root = os.path.realpath(NOTES_DIR)
    real_path = os.path.realpath(note_path)
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        return JSONResponse({"error": "禁止访问笔记目录外的文件"}, status_code=403)
    if not os.path.exists(note_path) or not os.path.isfile(note_path):
        return JSONResponse({"error": f"笔记 '{name}' 不存在"}, status_code=404)
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(note_path, encoding=enc) as f:
                content = f.read()
            content = rewrite_image_urls(content, os.path.dirname(name))
            return JSONResponse({"name": name, "content": content})
        except UnicodeDecodeError:
            continue
    return JSONResponse({"error": f"无法解码笔记 '{name}'"}, status_code=500)


@router.post("/rebuild")
async def api_rebuild():
    invalidate_cache()
    payload = build_index()
    payload = strip_text(payload)
    payload["user_data"] = app_data.get("user_data", {})
    return JSONResponse(payload)


@router.get("/typora/status")
async def api_typora_status():
    """返回 Typora 可执行文件与 typora:// 协议的实际可用状态。"""
    return detect_editors().get("typora", {})


@router.post("/typora/open/{name:path}")
async def api_typora_open(name: str):
    """用 subprocess 直接启动 Typora.exe 打开指定笔记。

    根因说明：typora:// 是 Typora 的 Electron 内部资源协议（CVE-2023-2316 披露），
    它不是用来打开外部用户文件的。无论 URL 写成 typora://D:/... 还是 typora://app/D:/...，
    Typora 都无法把外部 .md 文件作为可编辑文档打开，而是新建一个空白文档。
    因此改用后端直接调用 Typora.exe 传入本地路径，这是唯一可靠的方式。
    """
    note_path = os.path.join(NOTES_DIR, name)
    if not name.endswith(".md"):
        note_path += ".md"
    real_root = os.path.realpath(NOTES_DIR)
    real_path = os.path.realpath(note_path)
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        return JSONResponse({"error": "禁止访问笔记目录外的文件"}, status_code=403)
    if not os.path.isfile(note_path):
        return JSONResponse({"error": f"笔记 '{name}' 不存在"}, status_code=404)

    status = detect_editors().get("typora", {})
    typora_exe = status.get("path")
    if not typora_exe or not os.path.isfile(typora_exe):
        return JSONResponse({"ok": False, "error": "Typora 未安装或可执行文件未找到"}, status_code=400)

    try:
        # 用 DETACHED_PROCESS 启动，避免后端进程退出时连带关闭 Typora；
        # 不等待返回，立即返回 ok=True 给前端。
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [typora_exe, os.path.abspath(note_path)],
            creationflags=DETACHED_PROCESS,
            close_fds=True,
        )
    except OSError as e:
        return JSONResponse({"ok": False, "error": f"启动 Typora 失败: {e}"}, status_code=500)

    return {"ok": True, "path": os.path.abspath(note_path), "editor": "typora"}


@router.post("/typora/repair")
async def api_typora_repair():
    """运行受控的当前用户 Typora 协议修复脚本。"""
    script = os.path.join(PROJECT_ROOT, "scripts", "fix_typora_protocol.ps1")
    if not os.path.isfile(script):
        return JSONResponse({"ok": False, "error": "未找到 Typora 修复脚本"}, status_code=404)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return JSONResponse({"ok": False, "error": f"无法运行修复脚本: {e}"}, status_code=500)

    status = detect_editors().get("typora", {})
    if result.returncode != 0 or not status.get("available"):
        message = (result.stderr or result.stdout or "Typora 协议注册失败").strip()
        return JSONResponse({"ok": False, "error": message, "typora": status}, status_code=400)
    invalidate_cache()
    return {"ok": True, "typora": status}


# 服务端独占字段：前端 /data/save 无权覆盖（studyPlan/recommendPath/agentSettings
# 走各自专用端点，避免前端回传时整体替换把它们清空）
_SERVER_ONLY_KEYS = {"studyPlan", "recommendPath", "agentSettings"}


@router.post("/data/save")
async def api_data_save(request: Request):
    try:
        data = await request.json()
        # 黑名单保护：前端只更新它拥有的字段（favs/read/opens/...），服务端字段保留现状
        cur = app_data.get("user_data", {})
        merged = {k: v for k, v in cur.items() if k in _SERVER_ONLY_KEYS}
        merged.update({k: v for k, v in data.items() if k not in _SERVER_ONLY_KEYS})
        save_user_data(merged)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@router.get("/search")
async def api_search(q: str = "", cat: str = "", tag: str = "",
                     sort: str = "relevance", page: int = 1, size: int = 20):
    """全文搜索笔记。"""
    if not q.strip():
        return JSONResponse({"total": 0, "results": [], "page": page, "size": size})
    payload = build_index()
    result = search_notes(payload, q=q, cat=cat or None, tag=tag or None,
                          sort=sort, page=page, size=size)
    return JSONResponse(result)


# ───────── 推荐引擎（统一实现） ─────────
# 下列纯函数抽取自原 /api/recommend、/api/suggest、/api/insights 三份重复逻辑，
# 现由唯一的 /api/insights 端点复用，消除"改一处漏两处"的维护风险。


def _score_notes(notes, favs, read_ids, opens, interest_cats, has_user_data, now):
    """对笔记按兴趣/热度/新鲜度加权打分并排序。"""
    scored = []
    now_ts = now.timestamp()
    for n in notes:
        if n.get("stub"):
            continue
        score = 0.0
        if n["id"] in favs:
            score += 1.0
        if n["id"] in read_ids:
            score += 0.5
        score += min(opens.get(n["id"], 0) * 0.2, 0.8)
        if n["cat"] in interest_cats:
            score += 0.6
        wl_count = len(n.get("wikilinks", []))
        score += min(wl_count * 0.15, 0.6)
        try:
            # 复用笔记已有的 ts 时间戳，避免反复 strptime("%Y-%m-%d")
            ts = n.get("ts") or int(datetime.datetime.strptime(n["mtime"], "%Y-%m-%d").timestamp())
            days_since_update = int((now_ts - ts) // 86400)
            if days_since_update <= 30:
                score += 0.45
            elif days_since_update <= 60:
                score += 0.2
        except (ValueError, KeyError, TypeError):
            pass
        if n["id"] in read_ids and n["id"] not in favs:
            score *= 0.5
        if not has_user_data:
            cat_count = sum(1 for n2 in notes if n2["cat"] == n["cat"])
            score += min(cat_count * 0.05, 0.5)
            score += min(len(n.get("wikilinks", [])) * 0.15, 0.6)
            try:
                ts = n.get("ts") or int(datetime.datetime.strptime(n["mtime"], "%Y-%m-%d").timestamp())
                days = int((now_ts - ts) // 86400)
                if days <= 30:
                    score += 0.4
                elif days <= 90:
                    score += 0.2
            except (ValueError, KeyError, TypeError):
                pass
            lines = n.get("lines", 0)
            if lines > 200:
                score += 0.3
            elif lines > 100:
                score += 0.15
        scored.append({
            "id": n["id"], "name": n["name"], "cat": n["cat"],
            "tags": n.get("tags", []), "mtime": n.get("mtime", ""),
            "score": round(score, 2),
        })
    scored.sort(key=lambda x: -x["score"])

    if not has_user_data:
        seen_cats = set()
        boosted = []
        for s in scored:
            if s["cat"] not in seen_cats:
                s["score"] = max(s["score"], 0.5)
                seen_cats.add(s["cat"])
            boosted.append(s)
        boosted.sort(key=lambda x: (-x["score"], x["cat"]))
        scored = boosted
    return scored


def _review_list(notes, read_ids, now, threshold=45):
    """已读但久未更新的笔记，提示复习。"""
    review = []
    now_ts = now.timestamp()
    for n in notes:
        if n["id"] not in read_ids:
            continue
        try:
            ts = n.get("ts") or int(datetime.datetime.strptime(n["mtime"], "%Y-%m-%d").timestamp())
            days = int((now_ts - ts) // 86400)
            if days > threshold:
                review.append({"id": n["id"], "name": n["name"], "cat": n["cat"],
                               "days": days, "mtime": n["mtime"]})
        except (ValueError, KeyError, TypeError):
            pass
    review.sort(key=lambda x: -x["days"])
    return review


def _uncovered(notes, search_hist, match_names=True, match_tags=True):
    """搜索过但未在笔记标题/标签中出现的主题，提示知识缺口。"""
    all_names_tags = set()
    for n in notes:
        if match_names:
            all_names_tags.add(n["name"].replace(".md", "").lower())
        if match_tags:
            for t in n.get("tags", []):
                all_names_tags.add(t.lower())
    seen_kw = set()
    uncovered = []
    for kw in search_hist:
        kwl = kw.lower()
        if not any(kwl in nt for nt in all_names_tags) and kwl not in seen_kw:
            seen_kw.add(kwl)
            uncovered.append(kw)
    return uncovered[:10]


def _coverage(notes, read_ids, favs):
    """分类维度的覆盖度（总量/已读/收藏）。"""
    cat_coverage = {}
    for n in notes:
        c = n["cat"]
        if c not in cat_coverage:
            cat_coverage[c] = {"total": 0, "read": 0, "fav": 0}
        cat_coverage[c]["total"] += 1
        if n["id"] in read_ids:
            cat_coverage[c]["read"] += 1
        if n["id"] in favs:
            cat_coverage[c]["fav"] += 1
    return cat_coverage


def _stale(notes, now, threshold=30):
    """长期未更新的笔记。"""
    stale = []
    now_ts = now.timestamp()
    for n in notes:
        try:
            ts = n.get("ts") or int(datetime.datetime.strptime(n["mtime"], "%Y-%m-%d").timestamp())
            days = int((now_ts - ts) // 86400)
            if days > threshold:
                stale.append({"id": n["id"], "name": n["name"], "cat": n["cat"],
                              "days": days, "mtime": n["mtime"]})
        except (ValueError, KeyError, TypeError):
            pass
    stale.sort(key=lambda x: -x["days"])
    return stale


def _hubs(notes, top=10):
    """被引用最多的笔记（知识枢纽）。"""
    ref_count = {}
    for n in notes:
        for w in n.get("wikilinks", []):
            ref_count[w] = ref_count.get(w, 0) + 1
    return sorted(ref_count.items(), key=lambda x: -x[1])[:top]


def _hot_tags(notes, top=15):
    """出现频率最高的标签。"""
    tag_freq = {}
    for n in notes:
        for t in n.get("tags", []):
            tag_freq[t] = tag_freq.get(t, 0) + 1
    return sorted(tag_freq.items(), key=lambda x: -x[1])[:top]


def _recommended(notes, favs, readrecent, interest_cats):
    """基于兴趣分类与共享标签，推荐未读笔记。"""
    interest_ids = set(favs) | set(readrecent)
    interest_tags = set()
    for n in notes:
        if n["id"] in interest_ids:
            for t in n.get("tags", []):
                interest_tags.add(t)
    recommended = []
    for n in notes:
        if n["id"] in interest_ids:
            continue
        if n["cat"] in interest_cats:
            shared_tags = len(interest_tags & set(n.get("tags", [])))
            if shared_tags > 0:
                recommended.append({
                    "id": n["id"], "name": n["name"], "cat": n["cat"],
                    "reason": f"同分类「{n['cat']}」+ 共享 {shared_tags} 个标签",
                    "score": shared_tags,
                })
    recommended.sort(key=lambda x: -x["score"])
    return recommended


@router.get("/insights")
async def api_insights():
    """统一洞察端点：评分/复习/缺口/覆盖度/陈旧/枢纽/热门标签/推荐一站式返回。"""
    payload = build_index()
    notes = payload["notes"]
    now = datetime.datetime.now()
    ud = app_data.get("user_data", {})

    favs = set(ud.get("favs", []))
    read_ids = set(ud.get("read", []))
    opens = ud.get("opens", {})
    search_hist = ud.get("searchHist", [])
    has_user_data = bool(favs or read_ids or opens)

    interest_cats = {n["cat"] for n in notes if n["id"] in favs or n["id"] in read_ids}

    scored = _score_notes(notes, favs, read_ids, opens, interest_cats, has_user_data, now)
    review = _review_list(notes, read_ids, now)
    uncovered = _uncovered(notes, search_hist)
    cat_coverage = _coverage(notes, read_ids, favs)
    stale = _stale(notes, now)
    hubs = _hubs(notes)
    hot_tags = _hot_tags(notes)
    readrecent = ud.get("read", [])[-5:] if ud.get("read") else []
    recommended = _recommended(notes, favs, readrecent, interest_cats)

    return JSONResponse({
        "next": [x for x in scored[:10] if x["id"] not in read_ids or x["id"] in favs][:8],
        "review": review[:8],
        "gap": uncovered,
        "coverage": cat_coverage,
        "stale": stale[:10],
        "hubs": [{"id": nid, "name": next((n["name"] for n in notes if n["id"] == nid), "?"), "refs": cnt}
                 for nid, cnt in hubs],
        "hotTags": hot_tags,
        "recommended": recommended[:8],
        "stats": {"total": len(notes), "scored": len(scored),
                  "reviewCount": len(review), "gapCount": len(uncovered),
                  "staleCount": len(stale), "hubsCount": len(hubs)},
    })

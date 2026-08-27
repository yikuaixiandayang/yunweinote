#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI Agent API 路由（含 SSE 流式端点）。"""

import json
import time
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from config import (NOTES_DIR, app_data, save_user_data)
import agent as ai_agent

router = APIRouter(tags=["agent"])


# 默认配置（用户明确不需要脱敏处理；首次启动写入 user_data，前端设置中可修改）
# 双后端：Hermes Agent 优先（自带 tool_call），pcl GLM API 兜底
_DEFAULT_AGENT_CONFIG = {
    "apiBase": "https://llmapi.pcl.ac.cn/v1",
    "apiKey": "sk-n0lnEztd5d7qJArbWzn4Wd6Ray9s1wvLfWlCz8g01S2KPGun",
    "model": "GLM-5.2",
    "hermesUrl": "http://172.22.40.153:8642/v1",
    "hermesKey": "hermes_sk_7f3a9c2e1b8d4a6e5c0f2a9d3e7b1c4f8a6d2e9b",
    "backend": "auto",
}


def _get_agent_config() -> dict:
    ud = app_data.get("user_data", {})
    cfg = ud.get("agentSettings")
    # apiKey 或 hermesKey 任一存在即视为已配置
    if not cfg or not (cfg.get("apiKey") or cfg.get("hermesKey")):
        cfg = dict(_DEFAULT_AGENT_CONFIG)
        ud["agentSettings"] = cfg
        app_data["user_data"] = ud
        save_user_data(ud)
    return cfg


def _sync_agent_config() -> None:
    cfg = _get_agent_config()
    ai_agent.configure(
        api_base=cfg.get("apiBase"), api_key=cfg.get("apiKey"),
        model=cfg.get("model"),
        hermes_url=cfg.get("hermesUrl"), hermes_key=cfg.get("hermesKey"),
        backend=cfg.get("backend", "auto"),
    )


# 启动时同步一次
_sync_agent_config()


# ───────── 配置端点 ─────────

@router.get("/agent/config")
async def api_agent_config_get():
    cfg = _get_agent_config()
    def _mask(k):
        v = cfg.get(k, "")
        return (v[:8] + "***" + v[-4:]) if len(v) > 12 else "***"
    return JSONResponse({
        "apiBase": cfg.get("apiBase", ""),
        "apiKeyMasked": _mask("apiKey"),
        "model": cfg.get("model", ""),
        "hasKey": bool(cfg.get("apiKey")),
        "hermesUrl": cfg.get("hermesUrl", ""),
        "hermesKeyMasked": _mask("hermesKey"),
        "hasHermesKey": bool(cfg.get("hermesKey")),
        "backend": cfg.get("backend", "auto"),
    })


@router.post("/agent/config")
async def api_agent_config_set(request: Request):
    try:
        body = await request.json()
        ud = app_data.get("user_data", {})
        cfg = ud.get("agentSettings", dict(_DEFAULT_AGENT_CONFIG))
        for k_src, k_dst in [("apiBase", "apiBase"), ("apiKey", "apiKey"),
                             ("model", "model"), ("hermesUrl", "hermesUrl"),
                             ("hermesKey", "hermesKey"), ("backend", "backend")]:
            v = body.get(k_src)
            if v:
                cfg[k_dst] = v
        ud["agentSettings"] = cfg
        save_user_data(ud)
        _sync_agent_config()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@router.get("/agent/health")
async def api_agent_health():
    _sync_agent_config()
    return JSONResponse(await run_in_threadpool(ai_agent.health_check))


# ───────── 功能端点（非流式） ─────────

@router.post("/agent/summarize")
async def api_agent_summarize(request: Request):
    try:
        body = await request.json()
        name = body.get("name", "")
        if not name:
            return JSONResponse({"error": "缺少 name 参数"}, status_code=400)
        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        result = await run_in_threadpool(
            ai_agent.summarize_note, name, NOTES_DIR, payload["notes"],
            app_data.get("user_data", {}))
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/agent/organize")
async def api_agent_organize(request: Request):
    try:
        body = await request.json()
        target_cat = body.get("cat", "")
        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        result = await run_in_threadpool(
            ai_agent.organize_notes, payload["notes"],
            app_data.get("user_data", {}), target_cat)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/agent/recommend-path")
async def api_agent_recommend_path(request: Request):
    """生成学习路径 + 持久化规范化副本到 user_data.recommendPath（联动数据源）。

    响应在原 AI 字段（path/milestones/gaps，AgentPage 消费）之外附加 recommendPath
    规范化结构（steps 带 id/order/status/pathVersion），供学习计划联动使用。
    """
    try:
        body = await request.json() if await request.body() else {}
        goal = body.get("goal", "")
        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        result = await run_in_threadpool(
            ai_agent.recommend_path, payload["notes"],
            app_data.get("user_data", {}), goal)
        # 后处理：注入 id/order/status/pathVersion 并落盘（已完成步骤按 noteId/标题迁移）
        if "error" not in result and result.get("path"):
            ud = app_data.get("user_data", {})
            ud["recommendPath"] = ai_agent.normalize_recommend_path(
                result, ud.get("recommendPath"))
            save_user_data(ud)
            result["recommendPath"] = ud["recommendPath"]
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/agent/optimize-algorithm")
async def api_agent_optimize_algorithm(request: Request):
    try:
        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        result = await run_in_threadpool(
            ai_agent.optimize_algorithm, payload["notes"],
            app_data.get("user_data", {}))
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ───────── 动态学习计划端点 ─────────

@router.get("/agent/study-plan")
async def api_get_study_plan():
    """获取当前学习计划（不存在返回空）。"""
    ud = app_data.get("user_data", {})
    plan = ud.get("studyPlan")
    if not plan:
        return JSONResponse({"plan": None, "message": "尚未生成学习计划"})
    return JSONResponse({"plan": plan})


@router.post("/agent/study-plan/generate")
async def api_generate_study_plan(request: Request):
    """生成联动版学习计划：代码选步骤（顺序），AI 只拆解成笔记。

    - 计划任务严格取自路径"下一个未完成步骤"，AI 不可用时规则降级（degraded=true）
    - 无路径 / 路径全部完成 → ok=False + 引导信息（前端显示"生成学习路径"引导卡）
    """
    try:
        body = await request.json() if await request.body() else {}
        goal = body.get("goal", "")
        feedback = body.get("feedback", "")

        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        ud = app_data.get("user_data", {})
        prev_plan = ud.get("studyPlan")

        result = await run_in_threadpool(
            ai_agent.generate_study_plan_linked,
            notes=payload["notes"],
            user_data=ud,
            goal=goal,
            feedback=feedback,
        )

        if result.get("ok"):
            ud["studyPlan"] = result["plan"]
            # 路径状态可能变化（today_step pending → in_progress），一并回写
            ud["recommendPath"] = result["path"]
            save_user_data(ud)
            return JSONResponse({"ok": True, "plan": result["plan"],
                                 "path": result["path"],
                                 "degraded": result.get("degraded", False)})
        # 无路径 / 全部完成 / 异常 → 保持旧计划不变
        return JSONResponse({"ok": False, "plan": prev_plan,
                             "error": result.get("error", "生成失败")})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/agent/study-plan/feedback")
async def api_study_plan_feedback(request: Request):
    """任务反馈 + 回流路径进度（方向 B）。幂等、可撤销。

    action: "done" / "undo" / "skip" / "hard" / "easy" / "feedback"
    - status 只取 pending/done/skipped 三态；hard/easy/feedback 只写 item.feedback 文本
    - done → 对应路径步骤按任务汇总推进（全部解决且至少一个 done → 步骤 done）
    - undo → 步骤回退；重复 done 幂等 noop
    - source="manual" 的任务不推进路径
    """
    try:
        body = await request.json()
        note_id = body.get("noteId", "")
        action = body.get("action", "")
        feedback_text = body.get("feedback", "")

        ud = app_data.get("user_data", {})
        plan = ud.get("studyPlan") or {}
        path = ud.get("recommendPath") or {}
        if not plan:
            return JSONResponse({"ok": False, "error": "尚无学习计划"})

        # 1. 找到所有目标任务项（同 noteId 可能跨时间桶出现——完成应同时生效）
        targets = []
        for period in ("daily", "tomorrow", "weekly"):
            for item in (plan.get(period) or {}).get("items", []) or []:
                if item.get("noteId") == note_id:
                    targets.append(item)
        if not targets:
            return JSONResponse({"ok": False, "error": "任务不存在"})

        # 2. 更新任务状态（幂等：重复 done 且全部已 done 直接 noop 返回）
        if action == "done":
            if all(t.get("status") == "done" for t in targets):
                return JSONResponse({"ok": True, "plan": plan, "path": path, "noop": True})
            now_iso = datetime.now().isoformat(timespec="seconds")
            for t in targets:
                t["status"] = "done"
                t["doneAt"] = now_iso
        elif action == "undo":
            for t in targets:
                t["status"] = "pending"
                t["doneAt"] = None
        elif action == "skip":
            for t in targets:
                t["status"] = "skipped"
        elif action in ("hard", "easy", "feedback"):
            pass  # 只写反馈文本，status 不动（保持三态）
        else:
            return JSONResponse({"ok": False, "error": f"未知 action: {action}"})
        if feedback_text:
            for t in targets:
                t["feedback"] = feedback_text

        # 3. 回流路径（manual 任务隔离；任一关联步骤都要重算）
        synced = set()
        for t in targets:
            step_id = t.get("pathStepId")
            if step_id and t.get("source") != "manual" and step_id not in synced:
                ai_agent._sync_step_status(plan, path, step_id)
                synced.add(step_id)

        save_user_data(ud)
        return JSONResponse({"ok": True, "plan": plan, "path": path})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/agent/study-path")
async def api_get_study_path():
    """读取学习路径（带派生进度）。progress 在 deepcopy 上现算，禁止落库。"""
    import copy
    ud = app_data.get("user_data", {})
    path = copy.deepcopy(ud.get("recommendPath") or {})
    plan = ud.get("studyPlan") or {}
    for s in path.get("steps", []) or []:
        tasks = [it for p in ("daily", "tomorrow", "weekly")
                 for it in ((plan.get(p) or {}).get("items") or [])
                 if it.get("pathStepId") == s.get("id")]
        done = sum(1 for t in tasks if t.get("status") == "done")
        s["progress"] = f"{done}/{len(tasks)}"
    return JSONResponse({"path": path})


@router.post("/agent/study-plan/item")
async def api_study_plan_add_item(request: Request):
    """手动添加任务到今日计划：source="manual"，pathStepId=null，完成不推进路径。"""
    try:
        body = await request.json()
        name = (body.get("name") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "任务名不能为空"})
        note_id = body.get("noteId") or f"manual-{int(time.time())}"
        hours = body.get("estimatedHours", 1)

        ud = app_data.get("user_data", {})
        plan = ud.get("studyPlan") or {}
        if not plan:
            return JSONResponse({"ok": False, "error": "尚无学习计划"})
        plan.setdefault("daily", {"date": datetime.now().strftime("%Y-%m-%d"),
                                  "items": []})
        plan["daily"].setdefault("items", []).append({
            "noteId": note_id,
            "noteName": name,
            "pathStepId": None,
            "source": "manual",
            "reason": "手动添加",
            "estimatedHours": hours,
            "status": "pending",
            "doneAt": None,
        })
        save_user_data(ud)
        return JSONResponse({"ok": True, "plan": plan})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ───────── 对话端点（非流式，兼容旧前端） ─────────

@router.post("/agent/chat")
async def api_agent_chat(request: Request):
    try:
        body = await request.json()
        session_id = body.get("session_id") or "default"
        message = body.get("message", "").strip()
        if not message:
            return JSONResponse({"error": "message 不能为空"}, status_code=400)
        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        result = await run_in_threadpool(
            ai_agent.chat, session_id, message,
            notes=payload["notes"],
            user_data=app_data.get("user_data", {}))
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ───────── 对话端点（SSE 流式） ─────────

@router.post("/agent/chat/stream")
async def api_agent_chat_stream(request: Request):
    """流式对话：SSE 格式返回，每个 token 一个 event。

    请求体：{"session_id": "...", "message": "..."}
    响应流：data: {"content": "一个token"}\\n\\n
             data: [DONE]\\n\\n
    """
    try:
        body = await request.json()
        session_id = body.get("session_id") or "default"
        message = body.get("message", "").strip()
        if not message:
            return JSONResponse({"error": "message 不能为空"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    _sync_agent_config()
    from build_core import build_index
    payload = build_index()

    async def event_generator():
        async for chunk in ai_agent.chat_stream(
            session_id, message,
            notes=payload["notes"],
            user_data=app_data.get("user_data", {}),
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ───────── 文件 AI 解读 ─────────

def _read_describe_target(kind: str, path: str) -> tuple[str, str]:
    """按类型读取待解读文件，返回 (文件名, 内容)。失败抛异常。"""
    import os
    if kind == "script":
        from config import SCRIPTS_DIR
        file_path = os.path.join(SCRIPTS_DIR, path)
        real_root = os.path.realpath(SCRIPTS_DIR)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(real_root + os.sep) and real_path != real_root:
            raise PermissionError("禁止访问脚本目录外的文件")
        if not os.path.isfile(file_path):
            raise FileNotFoundError("脚本不存在")
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            return os.path.basename(file_path), f.read()
    elif kind == "folderfile":
        # path 形如 "文件夹名/相对路径"
        parts = path.split("/", 1)
        if len(parts) != 2:
            raise ValueError("folderfile 路径格式应为 文件夹名/文件路径")
        from folder_scan import folder_file
        r = folder_file(parts[0], parts[1])
        if not r.get("isText"):
            raise ValueError("该文件不是文本文件，暂不支持 AI 解读")
        return parts[1].split("/")[-1], r.get("content", "")
    raise ValueError(f"未知的解读类型: {kind}")


@router.get("/agent/describe")
async def api_agent_describe_get(path: str = "", kind: str = "script"):
    """返回缓存的文件解读（不调用 LLM）。"""
    if not path:
        return JSONResponse({"error": "缺少 path 参数"}, status_code=400)
    doc = ai_agent.get_cached_file_doc(path)
    return JSONResponse({"cached": bool(doc), "doc": doc})


@router.post("/agent/describe")
async def api_agent_describe(request: Request):
    """AI 解读脚本/文件：用途、用法、工作过程、注意事项（结果缓存）。"""
    try:
        body = await request.json()
        path = body.get("path", "")
        kind = body.get("kind", "script")
        force = bool(body.get("force"))
        if not path:
            return JSONResponse({"error": "缺少 path 参数"}, status_code=400)
        name, content = _read_describe_target(kind, path)
    except (PermissionError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    _sync_agent_config()
    result = await run_in_threadpool(
        ai_agent.describe_file, kind, path, name, content, force=force)
    return JSONResponse(result)


# ───────── 文件夹 AI 描述（单个，仅用户点击按钮触发） ─────────

@router.get("/agent/describe-folder")
async def api_agent_describe_folder_get(name: str = ""):
    """返回缓存的文件夹 AI 描述（不调用 LLM）。"""
    if not name:
        return JSONResponse({"error": "缺少 name 参数"}, status_code=400)
    doc = ai_agent.get_cached_folder_doc(name)
    return JSONResponse({"cached": bool(doc), "doc": doc})


@router.post("/agent/describe-folder")
async def api_agent_describe_folder(request: Request):
    """AI 生成/更新单个文件夹的描述（由用户点击按钮触发，结果缓存）。

    body: {"name": "文件夹名", "force": 可选，true 忽略缓存重新生成}
    """
    try:
        body = await request.json()
        name = (body.get("name") or "").strip()
        force = bool(body.get("force"))
    except Exception:
        return JSONResponse({"error": "请求体解析失败"}, status_code=400)
    if not name:
        return JSONResponse({"error": "缺少 name 参数"}, status_code=400)
    try:
        inputs = _build_folder_inputs(only=name)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not inputs:
        return JSONResponse({"error": f"未找到文件夹 '{name}'"}, status_code=404)
    fname, readme_text, tree_summary, rep_files = inputs[0]
    _sync_agent_config()
    result = await run_in_threadpool(
        ai_agent.describe_folder, fname, readme_text, tree_summary,
        rep_files, force=force)
    return JSONResponse(result)


# ───────── 文件夹 README.md 生成（写入磁盘） ─────────

import os as _os_for_readme   # 局部别名，避免与模块顶部命名冲突

_README_FILENAMES = ("README.md", "readme.md", "Readme.md", "README.MD")


def _has_readme(folder: str) -> str | None:
    """若目录已有 README（任意大小写变体），返回其文件名；否则 None。"""
    for cand in _README_FILENAMES:
        if _os_for_readme.path.isfile(_os_for_readme.path.join(folder, cand)):
            return cand
    return None


def _readme_needs_update(folder: str, force: bool) -> tuple[bool, str | None]:
    """判断目录 README 是否需要 LLM 生成/更新。

    返回 (needs_update, existing_readme_name)：
      - 无 README            → (True, None)   需创建
      - force=True 且有 README → (True, <name>) 强制重做
      - 有 README 但目录里有内容文件比 README 新 → (True, <name>) 过时需更新
      - 否则                  → (False, <name>) 跳过（省额度）

    mtime 对比排除 CONTENT_SKIP 目录（node_modules/.git/dist 等），避免依赖变动误判。
    README 自身不计入对比。
    """
    from folder_scan import CONTENT_SKIP
    existing = _has_readme(folder)
    if not existing:
        return True, None
    if force:
        return True, existing
    readme_path = _os_for_readme.path.join(folder, existing)
    try:
        readme_mtime = _os_for_readme.path.getmtime(readme_path)
    except OSError:
        return True, existing
    # 目录里有内容文件比 README 新 → 判定过时
    for root, dirs, files in _os_for_readme.walk(folder):
        dirs[:] = [d for d in dirs if d not in CONTENT_SKIP and not d.startswith(".")]
        for fn in files:
            # 跳过 README 自身（无论在根还是子目录的同名文件都跳过，避免自比较）
            if fn == existing:
                continue
            try:
                if _os_for_readme.path.getmtime(_os_for_readme.path.join(root, fn)) > readme_mtime:
                    return True, existing
            except OSError:
                continue
    return False, existing


def _write_folder_readme(name: str, content: str, force: bool = False) -> dict:
    """把 README Markdown 写入目录根。返回 {ok, path, written, skipped, error}。

    - skip 条件：磁盘已有 README 且 force=False
    - 写入固定为 README.md（统一大写）
    """
    from config import PROJECT_ROOT
    folder = _os_for_readme.path.join(PROJECT_ROOT, name)
    if not _os_for_readme.path.isdir(folder):
        return {"ok": False, "error": f"文件夹 '{name}' 不存在"}
    readme_path = _os_for_readme.path.join(folder, "README.md")
    if _os_for_readme.path.isfile(readme_path) and not force:
        return {"ok": True, "path": readme_path, "written": False, "skipped": True}
    try:
        with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content.rstrip() + "\n")
        return {"ok": True, "path": readme_path, "written": True, "skipped": False}
    except OSError as e:
        return {"ok": False, "error": str(e)}


@router.post("/agent/describe-folder-readme")
async def api_agent_describe_folder_readme(request: Request):
    """为单个目录生成/更新 README.md 并落盘（始终调 LLM：有则更新，无则创建）。

    body: {"name": "目录名", "force": 可选，true 覆盖已有 README（默认也是覆盖，force 仅为语义占位）}
    返回 {ok, written, path, name, error}。
    """
    try:
        body = await request.json()
        name = (body.get("name") or "").strip()
        force = bool(body.get("force"))
    except Exception:
        return JSONResponse({"error": "请求体解析失败"}, status_code=400)
    if not name:
        return JSONResponse({"error": "缺少 name 参数"}, status_code=400)
    from config import PROJECT_ROOT
    folder = _os_for_readme.path.join(PROJECT_ROOT, name)
    if not _os_for_readme.path.isdir(folder):
        return JSONResponse({"error": f"未找到文件夹 '{name}'"}, status_code=404)
    # 单卡片点击 = 用户显式要更新这一个，始终调 LLM 生成并写入（有则覆盖，无则创建）
    try:
        inputs = _build_folder_inputs(only=name)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not inputs:
        return JSONResponse({"error": f"未找到文件夹 '{name}'"}, status_code=404)
    fname, readme_text, tree_summary, rep_files = inputs[0]
    _sync_agent_config()
    r = await run_in_threadpool(
        ai_agent.generate_folder_readme, fname, readme_text, tree_summary, rep_files)
    if "error" in r or not r.get("readme"):
        return JSONResponse({"ok": False, "error": r.get("error", "LLM 返回空内容")},
                            status_code=500)
    w = _write_folder_readme(fname, r["readme"], force=True)  # 单卡片=显式更新，始终写入
    return JSONResponse({
        "ok": w.get("ok", False),
        "written": w.get("written", False),
        "path": w.get("path"),
        "name": fname,
        "error": w.get("error"),
    })


# ───────── 一键全量更新（脚本库描述 + 文件夹描述） ─────────

import threading

# 全局刷新任务状态（同一时刻只允许一个任务在跑）
_refresh_state = {
    "running": False,
    "force": False,
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": "",          # 正在处理的项目名
    "stage": "",            # scripts / folders
    "details": [],          # [{kind,name,ok,error}]
    "started_at": 0,
    "finished_at": 0,
    "error": "",
}
_refresh_lock = threading.Lock()


def _set_current(stage: str, name: str) -> None:
    with _refresh_lock:
        _refresh_state["stage"] = stage
        _refresh_state["current"] = name


def _add_detail(item: dict) -> None:
    with _refresh_lock:
        _refresh_state["details"].append(item)
        _refresh_state["done"] += 1
        if not item.get("ok"):
            _refresh_state["failed"] += 1


def _build_folder_inputs(only: str = "") -> list[tuple[str, str, str, list[str]]]:
    """扫描项目根所有一级文件夹，为每个构造 (name, readme, tree_summary, rep_files)。

    only 非空时只构造指定名称的文件夹（用于单个文件夹的 AI 描述）。
    """
    import os
    from config import PROJECT_ROOT
    from folder_scan import scan_folders, folder_tree, _read_readme, CONTENT_SKIP, TEXT_EXTS
    result = []
    folders_meta = scan_folders()
    for fm in folders_meta:
        name = fm["name"]
        if only and name != only:
            continue
        folder = os.path.join(PROJECT_ROOT, name)
        readme = _read_readme(folder)
        readme_text = ""
        if readme.get("exists"):
            try:
                with open(os.path.join(folder, readme["name"]), encoding="utf-8", errors="ignore") as f:
                    readme_text = f.read()
            except OSError:
                readme_text = ""
        # 类型分布摘要
        ext_stats = fm.get("extStats", {})
        tree_summary = f"文件数 {fm.get('fileCount', 0)}，子目录数 {fm.get('dirCount', 0)}，"
        tree_summary += f"主要类型：{', '.join(f'{e}({c})' for e, c in list(ext_stats.items())[:8])}"
        # 取若干代表性文件名（最多 20 个，优先文本/脚本）
        rep_files = []
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in CONTENT_SKIP and not d.startswith(".")]
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in TEXT_EXTS or ext in {".sh", ".py", ".ps1", ".bat", ".md"}:
                    rel = os.path.relpath(os.path.join(root, fn), folder).replace("\\", "/")
                    rep_files.append(rel)
                    if len(rep_files) >= 20:
                        break
            if len(rep_files) >= 20:
                break
        result.append((name, readme_text, tree_summary, rep_files))
    return result


def _run_refresh(force: bool) -> None:
    """后台线程：分批处理所有脚本 + 所有文件夹 + 所有缺失 README（每批 BATCH_SIZE 个，一次 LLM 调用）。"""
    import time
    try:
        _sync_agent_config()
        # ── 1. 脚本库（分批）──
        import os
        from config import SCRIPTS_DIR, PROJECT_ROOT
        from routers.scripts import _scan_scripts
        scripts = _scan_scripts()
        # 先过滤出需要处理的（命中缓存且非 force 的跳过），并读取内容
        pending = []
        for s in scripts:
            if not _refresh_state["running"]:
                break
            rel = s["relPath"]
            if not force and ai_agent.get_cached_file_doc(rel):
                _add_detail({"kind": "script", "name": rel, "ok": True, "skipped": True})
                continue
            try:
                fp = os.path.join(SCRIPTS_DIR, rel)
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                pending.append({"kind": "script", "path": rel, "name": s["name"], "content": content})
            except Exception as e:
                _add_detail({"kind": "script", "name": rel, "ok": False, "error": str(e)})
        # 分批调 LLM
        batch_size = ai_agent.BATCH_SIZE
        for i in range(0, len(pending), batch_size):
            if not _refresh_state["running"]:
                break
            batch = pending[i:i + batch_size]
            _set_current("scripts", f"批 {i//batch_size + 1}：{len(batch)} 个文件")
            try:
                results = ai_agent.describe_files_batch(batch)
                for ri in results:
                    doc = ri.get("doc", {})
                    _add_detail({"kind": "script", "name": ri["path"],
                                 "ok": isinstance(doc, dict) and "error" not in doc,
                                 "error": doc.get("error", "") if isinstance(doc, dict) else str(doc)})
            except Exception as e:
                for it in batch:
                    _add_detail({"kind": "script", "name": it["path"], "ok": False, "error": str(e)})
        # ── 2. 文件夹描述（分批）──
        folder_inputs = _build_folder_inputs()
        pending_folders = []
        for name, readme_text, tree_summary, rep_files in folder_inputs:
            if not _refresh_state["running"]:
                break
            if not force and ai_agent.get_cached_folder_doc(name):
                _add_detail({"kind": "folder", "name": name, "ok": True, "skipped": True})
                continue
            pending_folders.append({"name": name, "readme_text": readme_text,
                                    "tree_summary": tree_summary, "rep_files": rep_files})
        for i in range(0, len(pending_folders), batch_size):
            if not _refresh_state["running"]:
                break
            batch = pending_folders[i:i + batch_size]
            _set_current("folders", f"批 {i//batch_size + 1}：{len(batch)} 个文件夹")
            try:
                results = ai_agent.describe_folders_batch(batch)
                for ri in results:
                    doc = ri.get("doc", {})
                    _add_detail({"kind": "folder", "name": ri["name"],
                                 "ok": isinstance(doc, dict) and "error" not in doc,
                                 "error": doc.get("error", "") if isinstance(doc, dict) else str(doc)})
            except Exception as e:
                for it in batch:
                    _add_detail({"kind": "folder", "name": it["name"], "ok": False, "error": str(e)})
        # ── 3. README.md（无则创建；有但文件变动则 LLM 更新；有且没变则跳过；force 全重做）──
        # 变动检测：目录里有内容文件比 README 新（mtime 对比，排除依赖/构建目录）→ 过时需更新。
        # _write_folder_readme 传 force=True 确保覆盖过时的已有 README（能进 pending 的都是确定要写的）。
        pending_readmes = []
        for name, readme_text, tree_summary, rep_files in folder_inputs:
            if not _refresh_state["running"]:
                break
            folder = os.path.join(PROJECT_ROOT, name)
            needs, _existing = _readme_needs_update(folder, force)
            if not needs:
                _add_detail({"kind": "readme", "name": name, "ok": True, "skipped": True})
                continue
            pending_readmes.append({"name": name, "readme_text": readme_text,
                                    "tree_summary": tree_summary, "rep_files": rep_files})
        for i in range(0, len(pending_readmes), batch_size):
            if not _refresh_state["running"]:
                break
            batch = pending_readmes[i:i + batch_size]
            _set_current("readmes", f"批 {i//batch_size + 1}：{len(batch)} 个 README")
            try:
                results = ai_agent.generate_folders_readme_batch(batch)
                for ri in results:
                    name = ri["name"]
                    content = ri.get("readme", "")
                    err = ri.get("error")
                    if err or not content:
                        _add_detail({"kind": "readme", "name": name,
                                     "ok": False, "error": err or "LLM 返回空内容"})
                        continue
                    w = _write_folder_readme(name, content, force=True)  # 确定要写，覆盖过时的已有
                    _add_detail({"kind": "readme", "name": name,
                                 "ok": bool(w.get("ok")),
                                 "error": w.get("error", ""),
                                 "skipped": bool(w.get("skipped")),
                                 "written": bool(w.get("written"))})
            except Exception as e:
                for it in batch:
                    _add_detail({"kind": "readme", "name": it["name"], "ok": False, "error": str(e)})
    except Exception as e:
        with _refresh_lock:
            _refresh_state["error"] = str(e)
    finally:
        with _refresh_lock:
            _refresh_state["running"] = False
            _refresh_state["finished_at"] = time.time()
            _refresh_state["stage"] = ""
            _refresh_state["current"] = ""


@router.post("/agent/refresh-all")
async def api_agent_refresh_all(request: Request):
    """一键全量更新：脚本库所有脚本的 AI 解读 + 项目根所有一级文件夹的 AI 描述 + 无 README 目录的 README 生成。

    后台线程串行执行，立即返回 {started, total}。前端轮询 /agent/refresh-all/progress 查进度。
    查询参数 force=1 强制重新生成（脚本/描述忽略缓存；README 覆盖已有）。
    """
    import time
    import os as _os
    from config import PROJECT_ROOT
    force = request.query_params.get("force") == "1"
    with _refresh_lock:
        if _refresh_state["running"]:
            return JSONResponse({"started": False, "error": "已有更新任务在执行中"},
                                status_code=409)
        # 统计三阶段各自待处理数量（与 _run_refresh 的过滤逻辑保持一致）
        from routers.scripts import _scan_scripts
        try:
            scripts_count = sum(
                1 for s in _scan_scripts()
                if force or not ai_agent.get_cached_file_doc(s["relPath"])
            )
        except Exception:
            scripts_count = 0
        try:
            folder_inputs = _build_folder_inputs()
            folders_count = 0
            readme_count = 0
            for name, *_ in folder_inputs:
                if force or not ai_agent.get_cached_folder_doc(name):
                    folders_count += 1
                # README 计数用变动检测：无则需创建；有但文件变动则需更新；有且没变则跳过
                needs, _ = _readme_needs_update(_os.path.join(PROJECT_ROOT, name), force)
                if needs:
                    readme_count += 1
        except Exception:
            folder_inputs, folders_count, readme_count = [], 0, 0
        _refresh_state.update(
            running=True, force=force,
            total=scripts_count + folders_count + readme_count,
            done=0, failed=0,
            stage="", current="",
            details=[],
            started_at=time.time(), finished_at=0, error="",
        )
    t = threading.Thread(target=_run_refresh, args=(force,), daemon=True)
    t.start()
    return JSONResponse({
        "started": True,
        "total": _refresh_state["total"],
        "force": force,
        "breakdown": {"scripts": scripts_count, "folders": folders_count, "readmes": readme_count},
    })


@router.get("/agent/refresh-all/progress")
async def api_agent_refresh_progress():
    """查询一键更新任务进度。"""
    import time
    with _refresh_lock:
        state = dict(_refresh_state)
    state["elapsed"] = round((state.get("finished_at") or time.time()) - state.get("started_at", time.time()), 1)
    # details 可能很长，只返回最近 50 条
    state["recentDetails"] = state.get("details", [])[-50:]
    state.pop("details", None)
    return JSONResponse(state)


# ───────── 会话管理端点 ─────────

@router.get("/agent/sessions")
async def api_agent_sessions():
    return JSONResponse({"sessions": ai_agent.list_sessions()})


@router.get("/agent/session/{sid}")
async def api_agent_session_get(sid: str):
    s = ai_agent.get_session(sid)
    msgs = ai_agent.get_session_messages(sid)
    return JSONResponse({"id": sid, "messages": msgs, "count": len(msgs)})


@router.delete("/agent/session/{sid}")
async def api_agent_session_clear(sid: str):
    ai_agent.clear_session(sid)
    return JSONResponse({"ok": True})

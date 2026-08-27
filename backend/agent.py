#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI Agent 模块：基于 Hermes Agent（优先）+ pcl GLM API（兜底）的学习助手。

功能：
  1. chat              — 多轮对话（Hermes 自带 tool_call 能力，后端只负责收发 + 持久记忆）
  2. summarize_note    — 自动整理单篇笔记（摘要 + 知识点 + 复习要点）
  3. organize_notes    — 批量聚类整理（按主题分组 + 依赖关系建议）
  4. recommend_path   — 基于学习历史 + 目标推荐个性化学习路径
  5. optimize_algorithm — 优化学习算法（间隔重复 / 难度评估 / 推荐打分调优）
  6. chat_stream       — 流式对话（SSE，token 级实时返回）
  7. generate_study_plan_linked — 联动版学习计划（路径是唯一事实来源，方向 A+B 闭环）

记忆持久化：
  - 所有会话消息存入 SQLite（db.py），进程重启不丢失
  - 不再截断为固定条数，发给 LLM 时取最近 N 条（默认 50，可配置）
"""

import os
import json
import time
from typing import Any, AsyncIterator

import httpx

# ───────── 配置 ─────────
# 支持双后端：
#   - "hermes" : 优先使用 Hermes Agent（自带 tool_call + 共享记忆）
#   - "pcl"    : 兜底使用 pcl GLM API
# 运行期由 main.py 注入（来自 user_data.agentSettings）
DEFAULT_API_BASE = os.environ.get("LLM_API_BASE", "https://llmapi.pcl.ac.cn/v1")
DEFAULT_API_KEY = os.environ.get("LLM_API_KEY", "")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "GLM-5.2")

# 单次请求超时（秒）
REQUEST_TIMEOUT = 60

# 发给 LLM 的历史消息条数上限（从 SQLite 取最近 N 条）
_HISTORY_LIMIT = 50

_runtime_cfg = {
    "api_base": DEFAULT_API_BASE,
    "api_key": DEFAULT_API_KEY,
    "model": DEFAULT_MODEL,
    # Hermes Agent 专用配置（优先级高于 api_base/api_key）
    "hermes_url": os.environ.get("HERMES_URL", "http://172.22.40.153:8642/v1"),
    "hermes_key": os.environ.get("HERMES_KEY", ""),
    "backend": "auto",  # "auto" | "hermes" | "pcl"
}

# 导入 db 模块（记忆持久化层）
# 注意：db.init_db() 由 main.py 启动时调用，这里只 import
import db as _db


def init_db(data_dir: str) -> None:
    """供 main.py 启动时调用，初始化 SQLite。"""
    _db.init_db(data_dir)


# ───────── 配置管理 ─────────

def configure(api_base: str | None = None, api_key: str | None = None,
              model: str | None = None, hermes_url: str | None = None,
              hermes_key: str | None = None, backend: str | None = None) -> None:
    """由 main.py 在启动时注入配置。"""
    if api_base:
        _runtime_cfg["api_base"] = api_base
    if api_key:
        _runtime_cfg["api_key"] = api_key
    if model:
        _runtime_cfg["model"] = model
    if hermes_url:
        _runtime_cfg["hermes_url"] = hermes_url
    if hermes_key:
        _runtime_cfg["hermes_key"] = hermes_key
    if backend:
        _runtime_cfg["backend"] = backend


def get_config() -> dict:
    return dict(_runtime_cfg)


# ───────── LLM 调用核心 ─────────

def _select_backend() -> tuple[str, str, str]:
    """根据 backend 配置选择实际使用的后端。
    返回 (backend_name, api_base, api_key)。
    auto 模式：Hermes 配置了 key 且非占位符 → 优先 Hermes，否则 pcl。
    """
    cfg = _runtime_cfg
    mode = cfg.get("backend", "auto")
    hermes_key = cfg.get("hermes_key", "")
    # 非空即视为已配置
    hermes_usable = bool(hermes_key)
    if mode == "hermes":
        if hermes_usable:
            return "hermes", cfg["hermes_url"], hermes_key
        raise RuntimeError("backend=hermes 但 Hermes Key 未配置")
    if mode == "pcl":
        return "pcl", cfg["api_base"], cfg["api_key"]
    # auto：优先 Hermes，不可用则 pcl
    if hermes_usable:
        return "hermes", cfg["hermes_url"], hermes_key
    if cfg["api_key"]:
        return "pcl", cfg["api_base"], cfg["api_key"]
    raise RuntimeError("无可用 LLM 后端：Hermes Key 与 pcl Key 均未配置")


def _extract_content(data: dict) -> str:
    """从 OpenAI 兼容响应中提取 assistant 文本，兼容 None/缺失字段。"""
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM 返回空 choices")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if content is None:
        content = msg.get("reasoning") or ""
    if not isinstance(content, str):
        content = str(content) if content else ""
    return content.strip()


def _chat(messages: list[dict], *, temperature: float = 0.3,
          max_tokens: int = 2048, timeout: float = REQUEST_TIMEOUT,
          session_id: str | None = None) -> str:
    """调用 OpenAI 兼容的 /chat/completions 接口，返回 assistant 文本。

    - 自动选择后端（Hermes 优先，pcl 兜底）
    - session_id 非空时从 SQLite 读历史并持久化本次对话
    - 失败时抛出 RuntimeError，调用方负责兜底处理
    """
    cfg = _runtime_cfg
    backend, api_base, api_key = _select_backend()
    if not api_key:
        raise RuntimeError("LLM API Key 未配置：请在设置中填入 API Key")
    url = api_base.rstrip("/") + "/chat/completions"

    # 从 SQLite 读取会话历史（最近 N 条）
    final_messages = list(messages)
    if session_id:
        hist_rows = _db.get_session_messages(session_id, limit=_HISTORY_LIMIT)
        if hist_rows:
            hist = [{"role": r["role"], "content": r["content"]} for r in hist_rows]
            # 历史在前，本次 messages 在后
            final_messages = hist + messages

    payload = {
        "model": cfg["model"],
        "messages": final_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # 运维笔记客户端身份标识 —— 后端 Hermes Agent 据此区分来源
        "X-Hermes-Session-Id": "ops-notes",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    text = _extract_content(data)

    # 持久化到 SQLite：user 消息 + assistant 回复
    if session_id:
        # 记录本次传入的 user 消息（取最后一条 user）
        for m in reversed(messages):
            if m.get("role") == "user":
                _db.add_message(session_id, "user", m.get("content", ""), backend=backend)
                break
        _db.add_message(session_id, "assistant", text, backend=backend)
    return text


def _chat_with_fallback(messages: list[dict], **kwargs) -> dict:
    """带后端降级的 chat：Hermes 失败时自动切到 pcl。
    返回 {"content": "...", "backend": "..."} 或 {"error": "..."}。
    """
    cfg = _runtime_cfg
    mode = cfg.get("backend", "auto")
    try:
        backend, _, _ = _select_backend()
        text = _chat(messages, **kwargs)
        return {"content": text, "backend": backend}
    except Exception as e:
        err1 = str(e)
        # auto 模式：若首次用 hermes 失败且 pcl 有 key，降级到 pcl
        can_try_pcl = mode == "auto" and bool(cfg.get("api_key"))
        if can_try_pcl:
            try:
                old = cfg["backend"]
                cfg["backend"] = "pcl"
                text = _chat(messages, **kwargs)
                cfg["backend"] = old
                return {"content": text, "backend": "pcl",
                        "fallback": True, "prev_error": err1}
            except Exception as e2:
                cfg["backend"] = mode
                return {"error": f"Hermes 失败：{err1} | pcl 也失败：{e2}"}
        return {"error": err1}


# 强制 LLM 只输出 JSON 的约束后缀（抑制思考过程/多余解释）
_JSON_ONLY_SUFFIX = "\n\n【重要】直接输出 JSON 对象，不要输出思考过程、解释、markdown 标题或任何额外文字。第一个字符必须是 { 。"

# 一键更新描述任务的统一系统提示词。
# 不论切到 Hermes 还是 pcl，所有 describe_* 调用都带上它，让模型明确自己的任务边界，
# 避免把"解读脚本/文件夹"理解成闲聊、改代码、写完整文档等其它任务。
_DESCRIBE_SYSTEM_PROMPT = (
    "你是一位资深运维工程师，正在执行『一键更新描述』任务。"
    "你的唯一职责：为给定的脚本或文件夹生成结构化的中文描述字段"
    "（用途 / 用法 / 工作过程 / 注意事项 / 主要内容等，按当次要求的 JSON Schema 输出）。"
    "禁止做以下事：改写源码、给出修复建议、闲聊、输出与描述无关的内容、输出 markdown 标题或解释性文字。"
    "只输出要求的 JSON 对象，第一个字符必须是 { 。"
)


def _safe_json(text: str) -> Any:
    """从可能包含 markdown 代码块的 LLM 输出中提取 JSON。
    容错：支持对象/数组、去除包裹文本、失败时返回带原文的错误结构。
    """
    if not text:
        raise RuntimeError("LLM 返回空内容")
    s = text.strip()
    # 去除 ```json ... ``` 或 ``` ... ``` 包裹
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.startswith("json"):
                s = s[4:]
        else:
            s = parts[0]
    s = s.strip()
    # 优先尝试直接解析
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 截取第一个 { 到最后一个 } 之间（对象）
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            pass
    # 尝试数组 [ ... ]
    start = s.find("[")
    end = s.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            pass
    # 全部失败：返回带原文的提示
    raise RuntimeError(f"无法解析 LLM 输出为 JSON，原文前 200 字符：{s[:200]}")


def _parse_json_result(content: str, meta: dict) -> dict:
    """统一的 JSON 结果解析：解析 LLM 输出 + 注入 backend/fallback 元信息。"""
    result = _safe_json(content)
    if isinstance(result, list):
        result = {"items": result}
    if not isinstance(result, dict):
        result = {"value": result}
    result["_backend"] = meta.get("backend")
    if meta.get("fallback"):
        result["_fallback"] = True
        result["_prev_error"] = meta.get("prev_error")
    return result


# ───────── 笔记数据准备 ─────────

def _read_note_text(name: str, notes_dir: str) -> str:
    """读取笔记原文（最多 8000 字符，避免超出 LLM 上下文）。"""
    path = os.path.join(notes_dir, name if name.endswith(".md") else name + ".md")
    if not os.path.isfile(path):
        return ""
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()[:8000]
        except UnicodeDecodeError:
            continue
    return ""


def _build_user_context(notes: list[dict], user_data: dict) -> str:
    """构建发送给 LLM 的用户上下文（聚合行为数据，不含敏感原始输入）。"""
    read_ids = set(user_data.get("read", []))
    fav_ids = set(user_data.get("favs", []))
    opens = user_data.get("opens", {})
    search_hist = user_data.get("searchHist", [])[:10]

    lines = ["## 用户学习行为（聚合数据，已脱敏）"]
    lines.append(f"- 已读笔记数：{len(read_ids)}")
    lines.append(f"- 收藏笔记数：{len(fav_ids)}")
    lines.append(f"- 总打开次数：{sum(opens.values())}")
    if search_hist:
        lines.append(f"- 近期搜索关键词：{', '.join(search_hist)}")

    # 已读笔记清单（最多 20 条）
    read_notes = [n for n in notes if n["id"] in read_ids][:20]
    if read_notes:
        lines.append("\n### 已读笔记（近期）：")
        for n in read_notes:
            lines.append(f"- [{n['cat']}] {n['name']} (标签: {', '.join(n.get('tags', [])[:5]) or '无'})")

    # 收藏清单
    fav_notes = [n for n in notes if n["id"] in fav_ids][:10]
    if fav_notes:
        lines.append("\n### 收藏笔记：")
        for n in fav_notes:
            lines.append(f"- [{n['cat']}] {n['name']}")

    return "\n".join(lines)


# ───────── 功能 1：整理单篇笔记 ─────────

def summarize_note(name: str, notes_dir: str, notes: list[dict],
                   user_data: dict) -> dict:
    """整理单篇笔记：摘要 + 知识点 + 复习要点 + 难度评估。"""
    text = _read_note_text(name, notes_dir)
    if not text:
        return {"error": f"无法读取笔记 '{name}'"}

    note_info = next((n for n in notes if n["name"] == name or n["id"] == name), None)
    note_meta = ""
    if note_info:
        note_meta = f"分类：{note_info['cat']}，标签：{', '.join(note_info.get('tags', [])[:8])}"

    same_cat = [n["name"].replace(".md", "") for n in notes
                if note_info and n["cat"] == note_info["cat"]
                and n["name"] != name][:15]

    prompt = f"""你是一位资深运维学习教练。请整理以下运维学习笔记，输出结构化 JSON。

笔记信息：{note_meta}
同分类其他笔记：{', '.join(same_cat) if same_cat else '无'}

请输出严格符合以下 JSON Schema 的结果（不要输出任何额外文字）：
{{
  "summary": "200字以内的笔记摘要，概括核心主题与关键结论",
  "key_points": ["3-6个核心知识点，每个一句话"],
  "review_questions": ["2-4个复习自测题，用于检验掌握程度"],
  "difficulty": "入门 | 进阶 | 专家（三选一）",
  "prerequisites": ["0-3个建议先学的同分类笔记名（来自上方列表）"]
}}

笔记原文：
{text}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=1500,
        )
        if "error" in r:
            return {"error": r["error"], "fallback": True}
        return _parse_json_result(r["content"], r)
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}", "fallback": True}


# ───────── 功能 2：批量整理 / 聚类 ─────────

def organize_notes(notes: list[dict], user_data: dict,
                   target_cat: str = "") -> dict:
    """批量整理笔记：按主题聚类 + 学习顺序建议。"""
    candidates = [n for n in notes if not n.get("stub")]
    if target_cat:
        candidates = [n for n in candidates if n["cat"] == target_cat]
    candidates = candidates[:40]

    note_list = "\n".join(
        f"- id={n['id']} | {n['name'].replace('.md','')} | 分类={n['cat']} | "
        f"标签={', '.join(n.get('tags', [])[:5]) or '无'} | "
        f"wikilinks={len(n.get('wikilinks', []))}"
        for n in candidates
    )

    user_ctx = _build_user_context(notes, user_data)

    prompt = f"""你是一位运维学习路径规划专家。请对以下笔记进行主题聚类，并给出建议学习顺序。

{user_ctx}

## 待整理笔记（共 {len(candidates)} 篇）
{note_list}

请输出严格 JSON（不要额外文字）：
{{
  "clusters": [
    {{"topic": "主题名称", "note_ids": ["id1","id2"], "reason": "为什么把这些归为一组"}}
  ],
  "suggested_order": ["按建议学习顺序排列的 note_id 列表"],
  "tips": ["1-3条学习建议"]
}}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=2000,
        )
        if "error" in r:
            return {"error": r["error"], "fallback": True}
        return _parse_json_result(r["content"], r)
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}", "fallback": True}


# ───────── 功能 3：推荐个性化学习路径 ─────────

def recommend_path(notes: list[dict], user_data: dict,
                   goal: str = "") -> dict:
    """基于学习历史 + 目标推荐个性化学习路径。"""
    user_ctx = _build_user_context(notes, user_data)

    all_notes = "\n".join(
        f"- id={n['id']} | {n['name'].replace('.md','')} | {n['cat']} | "
        f"tags={', '.join(n.get('tags', [])[:4]) or '无'}"
        for n in notes if not n.get("stub")
    )[:6000]

    goal_str = f"用户学习目标：{goal}" if goal else "用户未指定目标，请根据其学习历史推断合理目标。"

    prompt = f"""你是一位个性化运维学习路径规划师。请基于用户的学习历史和目标，推荐一条循序渐进的学习路径。

{user_ctx}

## 目标
{goal_str}

## 可选笔记库
{all_notes}

## 要求
1. 路径长度 6-12 步，从基础到进阶
2. 已读过的笔记不必重复（除非需要复习）
3. 每步说明为什么推荐这篇、预计学习时长
4. 指出知识缺口与阶段性里程碑

请输出严格 JSON：
{{
  "path": [
    {{"step": 1, "note_id": "笔记id", "note_name": "笔记名", "reason": "推荐理由", "estimated_hours": 2}}
  ],
  "milestones": ["完成第3步后能独立部署单节点监控", "..."],
  "gaps": ["用户尚缺的基础知识", "..."]
}}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=2500,
        )
        if "error" in r:
            return {"error": r["error"], "fallback": True}
        return _parse_json_result(r["content"], r)
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}", "fallback": True}


# ───────── 功能 4：优化学习算法 ─────────

def optimize_algorithm(notes: list[dict], user_data: dict,
                       current_params: dict | None = None) -> dict:
    """分析用户学习模式，给出算法调优建议。"""
    user_ctx = _build_user_context(notes, user_data)

    params = current_params or {
        "review_interval_days": 45,
        "stale_days": 30,
        "fav_weight": 1.0,
        "read_weight": 0.5,
        "open_weight_per_time": 0.2,
        "open_cap": 0.8,
        "same_cat_weight": 0.6,
        "fresh_30d_weight": 0.45,
        "fresh_60d_weight": 0.2,
    }

    cat_count = len(set(n["cat"] for n in notes))
    prompt = f"""你是一位学习科学专家，擅长优化间隔重复与个性化推荐算法。请分析用户的学习数据，给出算法调优建议。

{user_ctx}

## 当前推荐算法参数
{json.dumps(params, ensure_ascii=False, indent=2)}

## 笔记库统计
- 总笔记数：{len(notes)}
- 分类数：{cat_count}

请分析用户学习节奏、遗忘曲线特征，并输出算法调优建议（严格 JSON）：
{{
  "analysis": "用户学习模式分析（节奏/专注领域/遗忘风险）",
  "recommendations": [
    {{"param": "参数名", "current": 当前值, "suggested": 建议值, "reason": "调整理由"}}
  ],
  "strategy": "个性化学习策略总结（一段话）"
}}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=1800,
        )
        if "error" in r:
            return {"error": r["error"], "fallback": True}
        return _parse_json_result(r["content"], r)
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}", "fallback": True}


# ───────── 健康检查 ─────────

def health_check() -> dict:
    """快速检测 LLM API 可达性与 Key 有效性（带后端降级）。"""
    cfg = _runtime_cfg
    if not cfg.get("api_key") and not cfg.get("hermes_key"):
        return {"ok": False, "error": "API Key 与 Hermes Key 均未配置"}
    try:
        r = _chat_with_fallback(
            [{"role": "user", "content": "请回复 ok"}],
            temperature=0, max_tokens=10, timeout=15,
        )
        if "error" in r:
            return {"ok": False, "error": r["error"], "model": cfg["model"]}
        return {"ok": True, "reply": r["content"][:50], "model": cfg["model"],
                "backend": r.get("backend"),
                "fallback": r.get("fallback", False)}
    except Exception as e:
        return {"ok": False, "error": str(e), "model": cfg["model"]}


# ───────── 会话对话（SQLite 持久记忆） ─────────

# 系统提示词（注入用户上下文，让 Hermes Agent 了解学习状态）
AGENT_SYSTEM_PROMPT = ""


def _build_system_prompt(notes: list[dict] | None, user_data: dict | None) -> str:
    """构建系统提示。"""
    parts = ["你是一位运维学习助手，能整理笔记、推荐学习路径、优化学习算法。请用中文回答。"]
    if notes and user_data:
        parts.append(_build_user_context(notes, user_data))
    return "\n\n".join(parts)


def chat(session_id: str, user_message: str, *, notes: list[dict] | None = None,
         user_data: dict | None = None) -> dict:
    """多轮对话接口（非流式）。

    返回：
      {"reply": "...", "backend": "hermes" | "pcl", "session_id": "..."}
    """
    system_msg = {"role": "system", "content": _build_system_prompt(notes, user_data)}
    messages = [system_msg, {"role": "user", "content": user_message}]
    r = _chat_with_fallback(messages, temperature=0.5, max_tokens=1500,
                            session_id=session_id)
    if "error" in r:
        return {"error": r["error"]}
    return {"reply": r["content"], "backend": r.get("backend"),
            "session_id": session_id, "fallback": r.get("fallback", False)}


async def chat_stream(
    session_id: str, user_message: str, *,
    notes: list[dict] | None = None,
    user_data: dict | None = None,
) -> AsyncIterator[str]:
    """流式对话接口（SSE）。

    逐 token yield SSE 格式字符串：
      data: {"content": "一个token"}\n\n
      data: [DONE]\n\n

    完成后自动将完整 assistant 回复写入 SQLite。
    """
    cfg = _runtime_cfg
    try:
        backend_name, api_base, api_key = _select_backend()
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return
    if not api_key:
        yield f"data: {json.dumps({'error': 'LLM API Key 未配置'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    url = api_base.rstrip("/") + "/chat/completions"

    # 先把 user 消息写入 SQLite
    _db.add_message(session_id, "user", user_message, backend=backend_name)

    # 从 SQLite 读历史（最近 N 条）
    hist_rows = _db.get_session_messages(session_id, limit=_HISTORY_LIMIT)
    hist = [{"role": r["role"], "content": r["content"]} for r in hist_rows]

    system_msg = {"role": "system", "content": _build_system_prompt(notes, user_data)}
    all_messages = hist + [system_msg, {"role": "user", "content": user_message}]

    full_content = ""

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream(
                "POST", url,
                json={
                    "model": cfg["model"],
                    "messages": all_messages,
                    "temperature": 0.5,
                    "max_tokens": 1500,
                    "stream": True,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    # 运维笔记客户端身份标识 —— 后端 Hermes Agent 据此区分来源
                    "X-Hermes-Session-Id": "ops-notes",
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_content += content
                            yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.HTTPStatusError as e:
        yield f"data: {json.dumps({'error': f'LLM 请求失败：HTTP {e.response.status_code}'}, ensure_ascii=False)}\n\n"
        return
    except Exception as e:
        # httpx 的 Timeout 异常 str 常为空，补上类型名便于排查
        detail = str(e) or type(e).__name__
        yield f"data: {json.dumps({'error': f'LLM 请求异常：{detail}'}, ensure_ascii=False)}\n\n"
        return

    # 流结束后，把完整 assistant 回复写入 SQLite
    if full_content:
        _db.add_message(session_id, "assistant", full_content, backend=backend_name)

    # 末尾事件：带上后端标识，前端用于显示
    yield f"data: {json.dumps({'backend': backend_name}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ───────── 会话管理（委托 db 层） ─────────

def list_sessions() -> list[dict]:
    """列出所有会话摘要。"""
    return _db.list_sessions()


def get_session(session_id: str) -> dict:
    """获取会话元信息。"""
    return _db.get_or_create_session(session_id)


def get_session_messages(session_id: str) -> list[dict]:
    """获取会话完整消息历史。"""
    return _db.get_session_messages(session_id)


def clear_session(session_id: str) -> None:
    """清空指定会话记忆。"""
    _db.clear_session(session_id)


# ───────── 文件 AI 解读（脚本库 / 文件库） ─────────

def get_cached_file_doc(path: str) -> dict | None:
    """读取缓存的文件解读。"""
    return _db.get_file_doc(path)


def describe_file(kind: str, path: str, name: str, content: str,
                  force: bool = False) -> dict:
    """让 LLM 解读一个脚本/文件：用途、用法、工作过程、注意事项。

    结果缓存到 SQLite（file_docs 表），同一文件只调用一次 LLM。
    force=True 时忽略缓存重新生成并覆盖（由用户显式触发）。
    返回 {"purpose","usage","workflow":[...],"notes"} 或 {"error":...}。
    """
    # 命中缓存直接返回
    if not force:
        cached = _db.get_file_doc(path)
        if cached:
            return cached

    # 截断超长内容，避免超出上下文
    text = content[:9000]
    if len(content) > 9000:
        text += "\n…（内容过长，已截断）"

    kind_label = "运维脚本" if kind == "script" else "项目文件"
    prompt = f"""请解读下面这个{kind_label}，输出结构化 JSON。

文件名：{name}

请输出严格符合以下 JSON Schema 的结果（不要输出任何额外文字）：
{{
  "purpose": "这个文件是干什么的（1-2 句话，具体到使用场景）",
  "usage": "怎么用：调用方式/命令示例/参数说明/配置项含义（纯文本，可多行，控制在 300 字以内，避免冗长）",
  "workflow": ["工作过程分步说明：它执行时依次做了什么，3-6 步"],
  "notes": "注意事项：依赖、风险、适用环境（1-2 句，可为空字符串）"
}}

文件内容：
```
{text}
``{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _DESCRIBE_SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            temperature=0.15, max_tokens=2000,
        )
        if "error" in r:
            return {"error": r["error"], "fallback": True}
        result = _parse_json_result(r["content"], r)
        # 过滤元信息字段后写缓存
        if "error" not in result:
            _db.set_file_doc(path, kind, result)
        return result
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}", "fallback": True}


# ───────── 批量解读（分批，减少 LLM 请求数 / 共享上下文） ─────────

# 每批处理的文件/文件夹数量。太大可能超 token 上限或单文件出错拖整批，
# 太小则退化为逐个调用。5 是兼顾值。
BATCH_SIZE = 5


def describe_files_batch(items: list[dict]) -> list[dict]:
    """批量解读多个脚本/文件，一次 LLM 调用返回所有描述。

    入参 items: [{"kind","path","name","content"}, ...]（最多 BATCH_SIZE 个）
    返回: 与入参等长的列表，每项是 {"path","doc":{...}} 或 {"path","error":...}。
    每个成功项单独写 file_docs 缓存。整批 JSON 解析失败时自动降级为逐个调用。
    """
    if not items:
        return []
    # 单个直接走 describe_file
    if len(items) == 1:
        it = items[0]
        r = describe_file(it["kind"], it["path"], it["name"], it["content"])
        return [{"path": it["path"], "doc": r}]

    # 拼批 prompt：每个文件编号 + 文件名 + 内容（截断）
    blocks = []
    for i, it in enumerate(items):
        text = (it.get("content") or "")[:6000]
        if len(it.get("content", "")) > 6000:
            text += "\n…（内容过长，已截断）"
        blocks.append(
            f"【文件{i}】\n文件名：{it['name']}\n```\n{text}\n```"
        )
    files_block = "\n\n".join(blocks)
    n = len(items)
    prompt = f"""请解读下面 {n} 个文件，为每个文件输出结构化描述。
严格输出一个 JSON 数组（不要输出任何额外文字），数组第 i 项对应【文件{i}】，每项格式：
{{
  "purpose": "这个文件是干什么的（1-2 句话，具体到使用场景）",
  "usage": "怎么用：调用方式/命令示例/参数说明（纯文本，可多行，控制在 300 字以内）",
  "workflow": ["工作过程分步说明，3-6 步"],
  "notes": "注意事项（1-2 句，可为空字符串）"
}}

{files_block}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _DESCRIBE_SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            temperature=0.15, max_tokens=4000,
        )
        if "error" in r:
            # 整批失败：降级逐个
            return [{"path": it["path"],
                     "doc": describe_file(it["kind"], it["path"], it["name"], it["content"])}
                    for it in items]
        parsed = _safe_json(r["content"])
        if not isinstance(parsed, list) or len(parsed) != n:
            raise RuntimeError("批量返回不是数组或数量不匹配")
        results = []
        for it, doc in zip(items, parsed):
            if isinstance(doc, dict) and "error" not in doc:
                _db.set_file_doc(it["path"], it["kind"], doc)
            results.append({"path": it["path"], "doc": doc if isinstance(doc, dict)
                            else {"error": "批量返回项格式错误"}})
        return results
    except Exception:
        # 解析失败：降级为逐个调用，保证每个文件都有结果
        return [{"path": it["path"],
                 "doc": describe_file(it["kind"], it["path"], it["name"], it["content"])}
                for it in items]


# ───────── 文件夹 AI 描述 ─────────


def get_cached_folder_doc(name: str) -> dict | None:
    """读取缓存的文件夹描述。"""
    return _db.get_folder_doc(name)


def describe_folder(name: str, readme_text: str, tree_summary: str,
                     rep_files: list[str], force: bool = False) -> dict:
    """让 LLM 为一个文件夹生成整体描述：用途、使用场景、主要内容、注意事项。

    入参：
      name          文件夹名
      readme_text   该文件夹 README.md 内容（可为空）
      tree_summary  文件类型分布 / 子目录结构摘要文本
      rep_files     几个代表性文件名（用于推断用途）
      force         True 时忽略缓存重新生成并覆盖（由用户显式触发）
    结果缓存到 SQLite（folder_docs 表），同一文件夹只调用一次 LLM。
    返回 {"summary","purpose","usage","contents","notes"} 或 {"error":...}。
    """
    if not force:
        cached = _db.get_folder_doc(name)
        if cached:
            return cached

    readme_excerpt = (readme_text or "").strip()[:2500]
    rep_list = "\n".join(f"- {f}" for f in rep_files[:20]) or "（无）"
    prompt = f"""请根据文件夹名称、README、目录结构摘要和代表性文件，为下面这个项目文件夹生成面向用户的结构化说明，输出严格符合以下 JSON Schema 的结果（不要输出任何额外文字）：
{{
  "summary": "一句话总结这个文件夹是干什么的（15-40 字）",
  "purpose": "用途：这个文件夹是做什么的、定位是什么，1-2 句话，具体到使用场景",
  "usage": "使用场景与用法：什么时候会用到、如何使用或运行（1-2 句话，无法判断时输出空字符串）",
  "contents": "主要包含哪些内容（2-4 项，用顿号分隔）",
  "notes": "注意事项：可能存在的风险、依赖或限制（1-2 句，无法判断时输出空字符串）"
}}

文件夹名：{name}

文件夹 README 内容：
```
{readme_excerpt or "（无 README）"}
```

文件夹结构摘要：
{tree_summary or "（无）"}

代表性文件：
{rep_list}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _DESCRIBE_SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            temperature=0.15, max_tokens=900,
        )
        if "error" in r:
            return {"error": r["error"], "fallback": True}
        result = _parse_json_result(r["content"], r)
        if "error" not in result:
            _db.set_folder_doc(name, result)
        return result
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}", "fallback": True}


def describe_folders_batch(items: list[dict]) -> list[dict]:
    """批量描述多个文件夹，一次 LLM 调用返回所有描述。

    入参 items: [{"name","readme_text","tree_summary","rep_files"}, ...]（最多 BATCH_SIZE 个）
    返回: 与入参等长的列表，每项 {"name","doc":{...}} 或 {"name","error":...}。
    整批解析失败时降级为逐个调用。
    """
    if not items:
        return []
    if len(items) == 1:
        it = items[0]
        r = describe_folder(it["name"], it.get("readme_text", ""),
                            it.get("tree_summary", ""), it.get("rep_files", []))
        return [{"name": it["name"], "doc": r}]

    blocks = []
    for i, it in enumerate(items):
        readme_excerpt = (it.get("readme_text") or "").strip()[:1500]
        rep = it.get("rep_files") or []
        rep_list = "\n".join(f"  - {f}" for f in rep[:15]) or "  （无）"
        blocks.append(
            f"【文件夹{i}】\n文件夹名：{it['name']}\nREADME：\n```\n{readme_excerpt or '（无 README）'}\n```\n结构摘要：{it.get('tree_summary','（无）')}\n代表性文件：\n{rep_list}"
        )
    folders_block = "\n\n".join(blocks)
    n = len(items)
    prompt = f"""请根据各文件夹的名称、README、结构摘要和代表性文件，为下面 {n} 个项目文件夹各生成一段面向用户的结构化说明。
严格输出一个 JSON 数组（不要输出任何额外文字），数组第 i 项对应【文件夹{i}】，每项格式：
{{
  "summary": "一句话总结这个文件夹是干什么的（15-40 字）",
  "purpose": "用途：这个文件夹是做什么的，1-2 句话，具体到使用场景",
  "usage": "使用场景与用法：什么时候会用到、如何使用或运行（1-2 句话，无法判断时输出空字符串）",
  "contents": "主要包含哪些内容（2-4 项，用顿号分隔）",
  "notes": "注意事项：可能存在的风险、依赖或限制（1-2 句，无法判断时输出空字符串）"
}}

{folders_block}
{_JSON_ONLY_SUFFIX}
"""
    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _DESCRIBE_SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            temperature=0.15, max_tokens=3000,
        )
        if "error" in r:
            return [{"name": it["name"],
                     "doc": describe_folder(it["name"], it.get("readme_text",""),
                                            it.get("tree_summary",""), it.get("rep_files",[]))}
                    for it in items]
        parsed = _safe_json(r["content"])
        if not isinstance(parsed, list) or len(parsed) != n:
            raise RuntimeError("批量返回不是数组或数量不匹配")
        results = []
        for it, doc in zip(items, parsed):
            if isinstance(doc, dict) and "error" not in doc:
                _db.set_folder_doc(it["name"], doc)
            results.append({"name": it["name"], "doc": doc if isinstance(doc, dict)
                            else {"error": "批量返回项格式错误"}})
        return results
    except Exception:
        return [{"name": it["name"],
                 "doc": describe_folder(it["name"], it.get("readme_text",""),
                                        it.get("tree_summary",""), it.get("rep_files",[]))}
                for it in items]


# ───────── 文件夹 README.md 生成（写入磁盘，不进 DB） ─────────

# README 写作任务的统一系统提示词。
# 区别于 _DESCRIBE_SYSTEM_PROMPT 的"输出 JSON"，这里要求直接输出 Markdown 文本。
_README_SYSTEM_PROMPT = (
    "你是一位资深技术作者，正在为项目中的某个目录撰写 README.md。"
    "你的唯一职责：根据提供的目录信息（名称、现有 README、内容摘要、代表性文件），"
    "产出一份结构清晰、信息密度高、可直接被开发者理解与使用的 README 内容。"
    "输出格式：标准 Markdown，从 H1 标题开始（标题就是目录名），使用 ## 二级小节。"
    "禁止：解释、思考过程、用 ```markdown ``` 包裹整篇 README、写『以下是 README：』之类的前缀、输出任何额外文字。"
)


def generate_folder_readme(name: str, readme_text: str, tree_summary: str,
                            rep_files: list[str]) -> dict:
    """为单个文件夹生成 README.md 内容（不落盘，由调用方决定是否写）。

    入参：
      name          目录名
      readme_text   该目录现有 README 内容（可为空，仅作参考）
      tree_summary  目录结构摘要（文件类型分布 + 子目录数）
      rep_files     代表性文件路径列表
    返回 {"readme": "..."} 或 {"error": "..."}。
    """
    existing = (readme_text or "").strip()[:1500]
    rep_list = "\n".join(f"- {f}" for f in rep_files[:25]) or "（无）"
    existing_block = (
        f"该目录已有 README（仅作参考，不强制沿用结构）：\n```\n{existing}\n```\n"
        if existing else "该目录当前无 README。\n"
    )
    prompt = f"""请为下面的项目目录撰写一份 README.md（中文，面向开发者）。

目录名：{name}

{existing_block}目录结构摘要：
{tree_summary or "（无）"}

代表性文件（最多 25 项）：
{rep_list}

要求：
- 从 H1 标题开始，标题就是「# {name}」
- 包含 3-5 个 ## 二级小节，至少覆盖：项目概述、主要内容/结构、关键文件或子目录说明、使用或集成方式（若有）、注意事项或限制
- 信息密度高，不泛泛而谈；具体到这个目录里实际有什么、做什么用
- 篇幅 600-1200 字
- 全文中文；命令、路径、代码标识符保留英文
- 不要用 ```markdown 包裹；第一个字符必须是 #"""
    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _README_SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=2000,
        )
        if "error" in r:
            return {"error": r["error"]}
        text = (r.get("content") or "").strip()
        if not text:
            return {"error": "LLM 返回空内容"}
        return {"readme": text}
    except Exception as e:
        return {"error": f"LLM 调用失败：{e}"}


def generate_folders_readme_batch(items: list[dict]) -> list[dict]:
    """批量为多个目录生成 README 内容（一次 LLM 调用）。

    入参 items: [{"name","readme_text","tree_summary","rep_files"}, ...]（最多 BATCH_SIZE 个）
    返回：与入参等长的列表，每项 {"name","readme"} 或 {"name","readme":"","error":...}。
    整批解析失败 / 调用异常时降级为逐个调用，确保每个目录都尝试。
    """
    if not items:
        return []
    if len(items) == 1:
        it = items[0]
        r = generate_folder_readme(it["name"], it.get("readme_text", ""),
                                    it.get("tree_summary", ""), it.get("rep_files", []))
        return [{"name": it["name"], "readme": r.get("readme", ""),
                 "error": r.get("error")}]

    blocks = []
    for i, it in enumerate(items):
        existing = (it.get("readme_text") or "").strip()[:1000]
        rep = it.get("rep_files") or []
        rep_list = "\n".join(f"  - {f}" for f in rep[:15]) or "  （无）"
        existing_line = (
            f"已有 README（参考）：\n```\n{existing}\n```" if existing
            else "当前无 README。"
        )
        blocks.append(
            f"【目录{i}】\n目录名：{it['name']}\n{existing_line}\n"
            f"结构摘要：{it.get('tree_summary', '（无）')}\n"
            f"代表性文件：\n{rep_list}"
        )
    items_block = "\n\n".join(blocks)
    n = len(items)
    prompt = f"""请为下面 {n} 个项目目录各生成一份 README.md（中文，面向开发者）。
严格输出一个 JSON 数组（不要输出任何额外文字或 markdown 代码块），数组第 i 项对应【目录{i}】，每项格式：
{{
  "readme": "完整的 README Markdown 文本，从 # 标题开始"
}}

每个 README 要求：
- 从 H1 标题开始，标题就是目录名
- 包含 3-5 个 ## 二级小节
- 信息密度高，不泛泛而谈
- 篇幅 500-1000 字
- 中文；命令、路径、代码标识符保留英文
- 第一个字符必须是 #

{items_block}"""
    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _README_SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=2500 * n,
        )
        if "error" in r:
            raise RuntimeError(r["error"])
        parsed = _safe_json(r["content"])
        if not isinstance(parsed, list) or len(parsed) != n:
            raise RuntimeError("批量返回不是数组或数量不匹配")
        results = []
        for it, doc in zip(items, parsed):
            if isinstance(doc, dict) and doc.get("readme"):
                results.append({"name": it["name"], "readme": doc["readme"]})
            else:
                err = doc.get("error", "批量返回项缺少 readme") if isinstance(doc, dict) else "格式错误"
                results.append({"name": it["name"], "readme": "", "error": err})
        return results
    except Exception as e:
        # 整批失败 → 降级逐个调用，保证每个目录都尝试
        return [{"name": it["name"],
                 "readme": "",
                 "error": f"批量失败({e})，请重试"}
                for it in items]


# ───────── 功能 6：动态学习计划（分时间维度） ─────────

def _study_plan_system_prompt() -> str:
    """学习计划任务的系统提示词。"""
    return (
        "你是一位资深运维学习规划师。你的唯一职责：基于用户的学习进度与反馈，"
        "生成分时间维度（今日/明日/本周/本月）的个性化学习计划。"
        "计划要循序渐进、与已学内容连贯，并参考用户反馈调整难度。"
        "只输出要求的 JSON 对象，第一个字符必须是 { 。"
    )


def _archive_daily_to_history(plan: dict) -> None:
    """generate 前归档上一次的 daily：把完成情况记入 plan["history"]。"""
    old_daily = plan.get("daily")
    if not old_daily or not old_daily.get("date"):
        return
    items = old_daily.get("items", []) or []
    completed = sum(1 for it in items if it.get("status") == "done")
    planned = len(items)
    note_ids = [it.get("noteId") for it in items if it.get("noteId")]
    history = plan.get("history", []) or []
    history.append({
        "date": old_daily.get("date"),
        "completed": completed,
        "planned": planned,
        "notes": note_ids,
    })
    # history 只保留最近 60 条，避免无限增长
    plan["history"] = history[-60:]


def _fill_monthly_current(plan: dict, notes: list[dict], user_data: dict) -> None:
    """后端填充 monthly.items[].currentCount —— AI 不知道用户今天读了什么，不能让它编。
    按 category 统计 read 集合里属于该分类的笔记数，进度条永远准确。
    """
    read_ids = set(user_data.get("read", []))
    cat_to_count = {}
    for n in notes:
        if n["id"] in read_ids and not n.get("stub"):
            cat_to_count[n["cat"]] = cat_to_count.get(n["cat"], 0) + 1
    monthly = plan.get("monthly") or {}
    for item in monthly.get("items", []) or []:
        cat = item.get("category", "")
        item["currentCount"] = cat_to_count.get(cat, 0)


def generate_study_plan(notes: list[dict], user_data: dict,
                        goal: str = "", feedback: str = "",
                        prev_plan: dict | None = None) -> dict:
    """根据笔记进度 + 已读记录 + 用户反馈，生成分时间维度的学习计划。

    返回 {"ok": True, "plan": {...}} 或 {"ok": False, "error": "..."}。
    AI 不可用时返回 ok=False，调用方应保持旧计划不变。
    """
    from collections import Counter
    from datetime import datetime, timedelta

    read_ids = set(user_data.get("read", []))
    total = len([n for n in notes if not n.get("stub")])
    read_count = len([n for n in notes if n["id"] in read_ids and not n.get("stub")])

    cat_total = Counter(n["cat"] for n in notes if not n.get("stub"))
    cat_read = Counter(n["cat"] for n in notes if n["id"] in read_ids and not n.get("stub"))

    unread = [n for n in notes if n["id"] not in read_ids and not n.get("stub")]

    # 已读笔记清单（最近 20 条，供 AI 判断"上次学了什么"做连贯性）
    read_recent = [n for n in notes if n["id"] in read_ids][:20]
    read_recent_str = "\n".join(
        f"- {n['name'].replace('.md', '')} [{n['cat']}]"
        for n in read_recent
    )[:2000] or "暂无已读笔记"

    # 未读候选（最多 50 条，避免 prompt 过长）
    unread_str = "\n".join(
        f"- id={n['id']} | {n['name'].replace('.md', '')} | {n['cat']} | tags={', '.join(n.get('tags', [])[:4]) or '无'}"
        for n in unread[:50]
    )[:3000] or "所有笔记都已读"

    # 上次计划的用户反馈（hard/easy/feedback 文本），让 AI 本次参考
    prev_feedback_str = ""
    if prev_plan:
        fb_items = []
        for period in ("daily", "tomorrow", "weekly"):
            for it in (prev_plan.get(period) or {}).get("items", []) or []:
                if it.get("feedback"):
                    fb_items.append(f"- [{it.get('noteName', '?')}] {it['feedback']}")
        if fb_items:
            prev_feedback_str = "\n## 上次计划的用户反馈（请在本次规划中参考）\n" + "\n".join(fb_items[:15])

    user_ctx = f"""## 当前进度
- 总笔记: {total} 篇，已读: {read_count} 篇，未读: {len(unread)} 篇
- 各分类进度: {', '.join(f'{c}({cat_read[c]}/{cat_total[c]})' for c in cat_total)}

## 已读笔记（最近）
{read_recent_str}

## 未读笔记（候选）
{unread_str}

## 用户本次反馈
{feedback if feedback else '无'}{prev_feedback_str}"""

    goal_str = f"## 学习目标\n{goal}" if goal else "## 学习目标\n用户未指定，请根据已学内容推断合理目标"

    prompt = f"""请基于用户的学习进度，生成一个分时间维度的学习计划。

{user_ctx}

{goal_str}

## 输出要求
1. **今日（1-2篇）**：选最该学的，优先跟上次学的内容连续
2. **明日（1-2篇）**：今日学完后的下一步
3. **本周（3-5篇）**：这一周要覆盖的内容，有主题
4. **本月主题**：这个月的重点方向 + 各分类目标篇数（currentCount 不要输出，后端会算）
5. 如果用户反馈"太难了"，降低难度；反馈"太简单"，提高难度

请输出严格 JSON：
{{
  "goal": "推断或确认的学习目标",
  "daily": {{
    "items": [
      {{"noteId": "笔记id", "noteName": "笔记名", "reason": "为什么今天学这篇", "estimatedHours": 2, "status": "pending"}}
    ]
  }},
  "tomorrow": {{
    "items": [
      {{"noteId": "笔记id", "noteName": "笔记名", "reason": "为什么明天学这篇", "estimatedHours": 2, "status": "pending"}}
    ]
  }},
  "weekly": {{
    "items": [
      {{"noteId": "笔记id", "noteName": "笔记名", "reason": "本周安排理由", "estimatedHours": 2, "status": "pending"}}
    ]
  }},
  "monthly": {{
    "theme": "本月主题",
    "items": [
      {{"category": "分类名", "targetCount": 5, "reason": "为什么这个分类是重点"}}
    ]
  }}
}}{_JSON_ONLY_SUFFIX}"""

    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": _study_plan_system_prompt()},
             {"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=2500,
        )
        if "error" in r:
            return {"ok": False, "error": r["error"]}

        plan_data = _safe_json(r["content"])

        # 归档上一次 daily 到 history（在覆盖前操作）
        if prev_plan:
            _archive_daily_to_history(prev_plan)
            plan_data["history"] = prev_plan.get("history", [])
        else:
            plan_data["history"] = []

        # 补充元数据
        today = datetime.now()
        plan_data["version"] = 1
        plan_data["lastUpdated"] = today.isoformat(timespec="hours")
        plan_data["lastUpdatedBy"] = r.get("backend", "unknown")
        (plan_data.setdefault("daily", {}))["date"] = today.strftime("%Y-%m-%d")
        (plan_data.setdefault("tomorrow", {}))["date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        (plan_data.setdefault("weekly", {}))["weekStart"] = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        (plan_data.setdefault("monthly", {}))["monthStart"] = today.strftime("%Y-%m-01")

        # 后端填 monthly.currentCount（AI 不输出这个字段，避免它瞎报）
        _fill_monthly_current(plan_data, notes, user_data)

        return {"ok": True, "plan": plan_data}
    except Exception as e:
        return {"ok": False, "error": f"生成学习计划失败：{e}"}


# ───────── 功能 7：学习计划 × 学习路径 联动（方向 A + B）─────────

def normalize_recommend_path(ai_result: dict, prev_path: dict | None = None) -> dict:
    """把 recommend_path 的 AI 输出规范化成 user_data.recommendPath 存储结构。

    - 注入 step id / order / status / pathVersion（AI 不输出这些字段）
    - 重新生成路径时：旧路径中已完成（done）的步骤按 noteId 或标题匹配迁移 status
    - AgentPage 消费的原始字段（path/milestones/gaps）留在 AI 返回值里，互不影响
    """
    from datetime import datetime

    prev = prev_path or {}
    prev_done = set()
    for s in prev.get("steps", []) or []:
        if s.get("status") == "done":
            if s.get("noteId"):
                prev_done.add(s["noteId"])
            if s.get("title"):
                prev_done.add(s["title"])

    steps = []
    for i, st in enumerate(ai_result.get("path", []) or [], 1):
        note_id = st.get("note_id", "")
        title = st.get("note_name") or note_id
        steps.append({
            "id": f"step-{i:03d}",
            "noteId": note_id,
            "title": title,
            "order": i,
            "status": "done" if (note_id in prev_done or title in prev_done) else "pending",
            "reason": st.get("reason", ""),
            "estimatedHours": st.get("estimated_hours", 2),
        })

    return {
        "version": 2,
        "pathVersion": datetime.now().strftime("pv-%Y%m%d-%H%M"),
        "steps": steps,
        "milestones": ai_result.get("milestones", []) or [],
        "gaps": ai_result.get("gaps", []) or [],
        "lastUpdated": datetime.now().isoformat(timespec="seconds"),
    }


def _sync_step_status(plan: dict, path: dict, step_id: str) -> None:
    """方向 B：任务状态变化后，派生重算对应路径步骤的状态。

    规则（跳过不阻塞完成，但完成至少需要一个 done）：
    - 步骤任务全部 done/skipped 且至少一个 done → done
    - 有任一 done（但未全部解决）→ in_progress
    - 否则：原本不是 done → pending；原本是 done（被撤销）→ in_progress
    """
    step = next((s for s in path.get("steps", []) or [] if s.get("id") == step_id), None)
    if not step:
        return
    tasks = [it for p in ("daily", "tomorrow", "weekly")
             for it in ((plan.get(p) or {}).get("items") or [])
             if it.get("pathStepId") == step_id]
    if not tasks:
        return
    resolved = [t for t in tasks if t.get("status") in ("done", "skipped")]
    if len(resolved) == len(tasks) and any(t.get("status") == "done" for t in tasks):
        step["status"] = "done"
    elif any(t.get("status") == "done" for t in tasks):
        step["status"] = "in_progress"
    else:
        step["status"] = "pending" if step.get("status") != "done" else "in_progress"


def _build_monthly(notes: list[dict], user_data: dict, week_notes: list[dict]) -> dict:
    """monthly 从本周计划笔记的分类派生（不新增 AI 调用）。

    theme 取前两个分类；targetCount = 该分类未读数截断到 [2,5]；
    currentCount 复用 _fill_monthly_current 按 read 集合统计（不让 AI 编）。
    """
    from collections import Counter
    from datetime import datetime

    read_ids = set(user_data.get("read", []))
    cat_unread = Counter(n["cat"] for n in notes
                         if n["id"] not in read_ids and not n.get("stub"))
    cats = []
    for n in week_notes:
        if n.get("cat") and n["cat"] not in cats:
            cats.append(n["cat"])
    items = [{"category": c,
              "targetCount": min(5, max(2, cat_unread.get(c, 2))),
              "reason": "路径本周聚焦方向"} for c in cats[:4]]
    monthly = {
        "monthStart": datetime.now().strftime("%Y-%m-01"),
        "theme": ("、".join(cats[:2]) + " 专项强化") if cats else "路径推进",
        "items": items,
    }
    _fill_monthly_current({"monthly": monthly}, notes, user_data)
    return monthly


def generate_study_plan_linked(notes: list[dict], user_data: dict,
                               goal: str = "", feedback: str = "") -> dict:
    """联动版学习计划（方向 A）：计划任务严格取自路径"下一个未完成步骤"。

    - 顺序决策归代码（pending 队列切片），AI 只做"步骤→笔记"的拆解
    - AI 不可用 → 规则降级（步骤自身笔记 + 标题关键词），degraded=True
    - pathStepId 由本函数注入，AI 输出里没有这个字段
    返回 {"ok": True, "plan", "path", "degraded"} 或 {"ok": False, "error"}。
    """
    from datetime import datetime, timedelta

    ud = user_data
    path = ud.get("recommendPath") or {}
    steps = sorted(path.get("steps", []) or [], key=lambda s: s.get("order", 0))
    pending = [s for s in steps if s.get("status") != "done"]
    if not pending:
        return {"ok": False, "error": "学习路径不存在或已全部完成，请先生成/重新生成学习路径"}

    today_step = pending[0]
    tomorrow_step = pending[1] if len(pending) > 1 else None
    week_steps = pending[:5]

    read_ids = set(ud.get("read", []))
    unread = [n for n in notes if n["id"] not in read_ids and not n.get("stub")]
    note_name = {n["id"]: n["name"].replace(".md", "") for n in notes}

    # 上次计划的文本反馈（hard/easy/feedback），供 AI 本次拆解时参考
    prev_plan = ud.get("studyPlan") or {}
    fb_lines = []
    for period in ("daily", "tomorrow", "weekly"):
        for it in (prev_plan.get(period) or {}).get("items", []) or []:
            if it.get("feedback"):
                fb_lines.append(f"- [{it.get('noteName', '?')}] {it['feedback']}")
    prev_fb = ("\n## 上次计划的用户反馈（参考）\n" + "\n".join(fb_lines[:15])) if fb_lines else ""

    degraded = False

    def split_step(step: dict) -> list[dict] | None:
        """AI 拆解：单步骤 → 1-3 篇笔记。失败返回 None 走规则降级。"""
        nonlocal degraded
        own = note_name.get(step.get("noteId"), "")
        own_line = f"该步骤对应的笔记是「{own}」(id={step.get('noteId')})，优先考虑它。" if own else ""
        candidates = "\n".join(
            f"- id={n['id']} | {n['name'].replace('.md', '')} | {n['cat']}"
            for n in unread[:50]
        ) or "（无未读笔记）"
        prompt = f"""你是运维学习规划师。学习路径中当前步骤是「{step.get('title', '')}」。
从候选笔记中挑出完成这个步骤最需要的 1-3 篇，按学习顺序排列。
{own_line}
## 候选笔记（未读）
{candidates}
## 用户反馈
{(feedback or '无')}{prev_fb}
只输出严格 JSON：
{{"items": [{{"noteId": "候选列表里的id", "reason": "为什么这篇属于这个步骤", "estimatedHours": 2}}]}}"""
        try:
            r = _chat_with_fallback(
                [{"role": "system", "content": "只输出JSON。"},
                 {"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=800,
            )
        except Exception:
            r = {"error": "LLM 调用异常"}
        if "error" not in r:   # _chat_with_fallback 没有 ok 字段，失败时带 error 键
            data = _safe_json(r.get("content", ""))
            valid_ids = {n["id"] for n in unread}
            items = (data or {}).get("items") or []
            if data and items and all(i.get("noteId") in valid_ids for i in items):
                return items[:3]
        degraded = True
        return None

    def rule_split(step: dict) -> list[dict]:
        """规则降级：步骤自身笔记优先（未读时）+ 标题分词关键词匹配，共 ≤2 篇。"""
        picked = []
        own_id = step.get("noteId")
        if own_id and any(n["id"] == own_id for n in unread):
            picked.append(own_id)
        kws = [w for w in str(step.get("title", "")).split() if w]
        for n in unread:
            if len(picked) >= 2:
                break
            if n["id"] in picked:
                continue
            if any(kw.lower() in n["name"].lower() for kw in kws):
                picked.append(n["id"])
        return [{"noteId": pid,
                 "reason": f"路径步骤「{step.get('title', '')}」的规则匹配",
                 "estimatedHours": 2} for pid in picked]

    _split_cache = {}   # 步骤级缓存：同一步骤在 daily/weekly 只拆解一次（省 AI 调用）

    def build_items(step: dict | None) -> list[dict]:
        if not step:
            return []
        if step["id"] not in _split_cache:
            _split_cache[step["id"]] = split_step(step) or rule_split(step)
        raw = _split_cache[step["id"]]
        out = []
        for i in raw:
            pid = i.get("noteId", "")
            out.append({
                "noteId": pid,
                "noteName": note_name.get(pid, pid),
                "pathStepId": step["id"],          # 服务端注入，AI 永不接触
                "source": "path",
                "reason": i.get("reason", ""),
                "estimatedHours": i.get("estimatedHours", 2),
                "status": "pending",
                "doneAt": None,
            })
        return out

    # 生成前归档旧 daily 到 history（学习轨迹，已拍板实现的功能）
    if prev_plan:
        _archive_daily_to_history(prev_plan)
        history = prev_plan.get("history", []) or []
    else:
        history = []

    today = datetime.now()
    daily_items = build_items(today_step)[:3]
    tomorrow_items = build_items(tomorrow_step)[:3]
    # weekly 去重：已进今日/明日的笔记不再重复排进本周（否则同一任务出现在两个时间桶）
    _scheduled = {it["noteId"] for it in daily_items + tomorrow_items if it.get("noteId")}
    weekly_items = []
    for s in week_steps:
        for it in build_items(s):
            if it["noteId"] not in _scheduled:
                weekly_items.append(it)
                _scheduled.add(it["noteId"])
    weekly_items = weekly_items[:5]                # 本周总量截断 5 篇

    # monthly 从本周计划笔记的分类派生
    week_note_objs = [next((n for n in notes if n["id"] == it["noteId"]), None)
                      for it in daily_items + weekly_items]
    week_note_objs = [n for n in week_note_objs if n]

    plan = {
        "version": 2,
        "goal": goal or prev_plan.get("goal", ""),
        "lastUpdated": today.isoformat(timespec="hours"),
        "lastUpdatedBy": "rule" if degraded else "ai",
        "daily": {"date": today.strftime("%Y-%m-%d"), "items": daily_items},
        "tomorrow": {"date": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
                     "items": tomorrow_items},
        "weekly": {"weekStart": (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d"),
                   "items": weekly_items},
        "monthly": _build_monthly(notes, ud, week_note_objs),
        "history": history,
    }

    # 首个任务调度进今日 → 步骤进入 in_progress（方向 A 的状态机）
    if today_step.get("status") == "pending":
        today_step["status"] = "in_progress"

    return {"ok": True, "plan": plan, "path": path, "degraded": degraded}


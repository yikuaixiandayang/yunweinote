#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 持久记忆层：替代 agent.py 中的内存 _sessions dict。

表结构：
  sessions  — 会话元信息（id, title, 时间戳, 消息计数）
  messages  — 每条消息一行，全量保留，不再截断

特性：
  - WAL 模式，读写不互相阻塞
  - 启动时自动建表，无需手动迁移
  - 进程重启后记忆完整保留
"""

import os
import json
import time
import threading
import sqlite3
from typing import Optional

_db_path: str = ""
_conn: Optional[sqlite3.Connection] = None
# 写锁：agent 端点经 run_in_threadpool 在 worker 线程写库，refresh-all 后台线程也写库，
# 而 chat_stream 在事件循环线程写库。统一用这把锁串行化所有连接写操作，避免多线
# 程共用同一连接导致 "database is locked" 或连接态错乱（check_same_thread=False 只关
# 掉线程检查，并不保证并发安全）。
# 用 RLock：add_message 内部会调用 get_or_create_session，二者都会取锁，同一线程需可重入。
_write_lock = threading.RLock()


def init_db(data_dir: str) -> None:
    """初始化数据库连接并建表。在 main.py 启动时调用一次。"""
    global _db_path, _conn

    os.makedirs(data_dir, exist_ok=True)
    _db_path = os.path.join(data_dir, "agent_memory.db")
    _conn = sqlite3.connect(_db_path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row

    _conn.execute("PRAGMA journal_mode=WAL")
    # 并发写（agent 线程池 / refresh-all 线程 / 事件循环线程）时，让 SQLite 在锁冲突时
    # 等待而非立即报错 "database is locked"。配合下方写锁，基本消除锁竞争导致的失败。
    _conn.execute("PRAGMA busy_timeout=5000")
    _conn.execute("PRAGMA foreign_keys=ON")

    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         TEXT PRIMARY KEY,
            title      TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            last_active REAL NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL DEFAULT '',
            created_at  REAL NOT NULL,
            backend     TEXT NOT NULL DEFAULT '',
            token_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, created_at);

        -- 文件 AI 解读缓存（脚本库/文件库的每个文件一份，避免重复调用 LLM）
        CREATE TABLE IF NOT EXISTS file_docs (
            path       TEXT PRIMARY KEY,
            kind       TEXT NOT NULL DEFAULT '',
            doc        TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );

        -- 文件夹 AI 描述缓存（项目根下每个一级文件夹一份）
        CREATE TABLE IF NOT EXISTS folder_docs (
            name       TEXT PRIMARY KEY,
            doc        TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );

        -- 用户自定义备注（文件夹 / 脚本各一份，key 形如 "folder:xxx" / "script:xxx"）
        CREATE TABLE IF NOT EXISTS user_notes (
            key        TEXT PRIMARY KEY,
            note       TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
    """)
    _conn.commit()


def get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("db.init_db() 尚未调用")
    return _conn


# ───────── 会话操作 ─────────


def get_or_create_session(session_id: str) -> dict:
    """获取或创建会话，返回会话元信息 dict。"""
    with _write_lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row:
            now = time.time()
            conn.execute(
                "UPDATE sessions SET last_active = ? WHERE id = ?", (now, session_id)
            )
            conn.commit()
            return dict(row)
        now = time.time()
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, last_active, message_count) "
            "VALUES (?, '', ?, ?, 0)",
            (session_id, now, now),
        )
        conn.commit()
        return {
            "id": session_id,
            "title": "",
            "created_at": now,
            "last_active": now,
            "message_count": 0,
        }


def add_message(
    session_id: str,
    role: str,
    content: str,
    *,
    backend: str = "",
    token_count: int = 0,
) -> None:
    """向会话追加一条消息，自动更新会话的 last_active 和 message_count。"""
    with _write_lock:
        conn = get_conn()
        now = time.time()

        # 确保会话存在（RLock 可重入，get_or_create_session 内部取锁安全）
        get_or_create_session(session_id)

        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at, backend, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, now, backend, token_count),
        )
        conn.execute(
            "UPDATE sessions SET last_active = ?, message_count = message_count + 1 WHERE id = ?",
            (now, session_id),
        )
        conn.commit()

        # 自动更新会话标题：用用户第一条消息的前 30 字
        if role == "user" and not content.startswith("[system]"):
            title = _auto_title(session_id)
            if title:
                conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
                conn.commit()


def _auto_title(session_id: str) -> str:
    """取该会话第一条用户消息的前 30 字作为标题（仅在 title 为空时调用）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT title FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row and row["title"]:
        return ""

    first = conn.execute(
        "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
        "ORDER BY created_at ASC LIMIT 1",
        (session_id,),
    ).fetchone()
    if first:
        text = first["content"].replace("\n", " ").strip()
        return text[:30] + ("…" if len(text) > 30 else "")
    return ""


def get_session_messages(
    session_id: str, *, limit: Optional[int] = None, offset: int = 0
) -> list[dict]:
    """获取会话消息列表，按时间正序。limit=None 返回全部。"""
    conn = get_conn()
    sql = "SELECT id, role, content, created_at, backend FROM messages WHERE session_id = ? ORDER BY created_at ASC"
    params: tuple = (session_id,)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (session_id, limit, offset)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_sessions() -> list[dict]:
    """返回所有会话摘要（不含消息全文），按最近活跃排序。"""
    conn = get_conn()
    now = time.time()
    rows = conn.execute(
        "SELECT id, title, created_at, last_active, message_count "
        "FROM sessions ORDER BY last_active DESC"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["idle_seconds"] = round(now - d["last_active"], 0)
        result.append(d)
    return result


def clear_session(session_id: str) -> None:
    """删除会话及其所有消息。"""
    with _write_lock:
        conn = get_conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


def search_messages(keyword: str, limit: int = 20) -> list[dict]:
    """全文搜索历史消息（LIKE 匹配），返回匹配的消息。"""
    conn = get_conn()
    pattern = f"%{keyword}%"
    rows = conn.execute(
        "SELECT m.id, m.session_id, m.role, m.content, m.created_at, m.backend "
        "FROM messages m WHERE m.content LIKE ? ORDER BY m.created_at DESC LIMIT ?",
        (pattern, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ───────── 文件 AI 解读缓存 ─────────


def get_file_doc(path: str) -> dict | None:
    """获取缓存的文件解读（返回解析后的 dict），无缓存返回 None。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT doc, kind, created_at FROM file_docs WHERE path = ?", (path,)
    ).fetchone()
    if not row:
        return None
    try:
        doc = json.loads(row["doc"])
    except json.JSONDecodeError:
        return None
    doc["_kind"] = row["kind"]
    doc["_created_at"] = row["created_at"]
    return doc


def set_file_doc(path: str, kind: str, doc: dict) -> None:
    """缓存文件解读（覆盖旧值）。"""
    with _write_lock:
        conn = get_conn()
        doc_copy = {k: v for k, v in doc.items() if not k.startswith("_")}
        conn.execute(
            "INSERT INTO file_docs (path, kind, doc, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET kind=excluded.kind, doc=excluded.doc, "
            "created_at=excluded.created_at",
            (path, kind, json.dumps(doc_copy, ensure_ascii=False), time.time()),
        )
        conn.commit()


# ───────── 文件夹 AI 描述缓存 ─────────


def get_folder_doc(name: str) -> dict | None:
    """获取缓存的文件夹描述（返回解析后的 dict），无缓存返回 None。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT doc, created_at FROM folder_docs WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        return None
    try:
        doc = json.loads(row["doc"])
    except json.JSONDecodeError:
        return None
    doc["_created_at"] = row["created_at"]
    return doc


def set_folder_doc(name: str, doc: dict) -> None:
    """缓存文件夹描述（覆盖旧值）。"""
    with _write_lock:
        conn = get_conn()
        doc_copy = {k: v for k, v in doc.items() if not k.startswith("_")}
        conn.execute(
            "INSERT INTO folder_docs (name, doc, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET doc=excluded.doc, "
            "created_at=excluded.created_at",
            (name, json.dumps(doc_copy, ensure_ascii=False), time.time()),
        )
        conn.commit()


# ───────── 用户自定义备注 ─────────


def get_note(key: str) -> str:
    """获取某条用户备注，无则返回空串。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT note FROM user_notes WHERE key = ?", (key,)
    ).fetchone()
    return row["note"] if row else ""


def set_note(key: str, note: str) -> None:
    """写入/清空用户备注（空串会保留行，便于区分"未设置"与"清空"）。"""
    with _write_lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO user_notes (key, note, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET note=excluded.note, "
            "updated_at=excluded.updated_at",
            (key, note, time.time()),
        )
        conn.commit()


def delete_note(key: str) -> None:
    """彻底删除某条用户备注。"""
    with _write_lock:
        conn = get_conn()
        conn.execute("DELETE FROM user_notes WHERE key = ?", (key,))
        conn.commit()


def get_notes_bulk(prefix: str) -> dict:
    """批量取回以 prefix 开头的所有备注（如 "folder:" / "script:"）。返回 {key: note}。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT key, note FROM user_notes WHERE key LIKE ?",
        (prefix + "%",),
    ).fetchall()
    return {r["key"]: r["note"] for r in rows}

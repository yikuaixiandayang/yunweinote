#!/usr/bin/env python3
"""db.py（SQLite 持久记忆层）单测。

重点验证本次优化引入的并发安全机制：
  - init_db 设置 PRAGMA busy_timeout / WAL
  - 所有写函数经 threading.RLock 串行化；add_message 内部调用 get_or_create_session
    再次取锁，验证 RLock 可重入（若误用普通 Lock 会死锁）
  - 多线程并发写同一会话不抛 "database is locked"、不丢消息
以及常规读写正确性（会话创建/查询/清除、各类缓存 upsert、用户备注）。
"""
import os
import sys
import threading
import time

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """每个测试用独立临时库，避免相互污染。"""
    db.init_db(str(tmp_path))
    yield
    # 测试结束后断开，释放 WAL 文件
    conn = db._conn
    db._conn = None
    if conn is not None:
        conn.close()


# ─────────────── 会话读写基础 ───────────────
def test_get_or_create_session_creates_then_returns_existing():
    s = db.get_or_create_session("sess-1")
    assert s["id"] == "sess-1"
    assert s["message_count"] == 0
    # 第二次调用应返回同一行（不会新建），仅刷新 last_active
    s2 = db.get_or_create_session("sess-1")
    assert s2["id"] == "sess-1"
    assert s2["message_count"] == 0


def test_add_message_autocreates_session_and_increments_count():
    db.add_message("sess-a", "user", "你好，这是第一条消息")
    db.add_message("sess-a", "assistant", "收到")
    msgs = db.get_session_messages("sess-a")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"

    sess = db.get_or_create_session("sess-a")
    assert sess["message_count"] == 2
    # 用户首条消息前 30 字自动成为标题
    assert sess["title"] == "你好，这是第一条消息"


def test_add_message_title_truncates_at_30():
    long_text = "字" * 50
    db.add_message("sess-title", "user", long_text)
    sess = db.get_or_create_session("sess-title")
    assert len(sess["title"]) == 31  # 30 字 + 省略号
    assert sess["title"].endswith("…")


def test_clear_session_removes_messages_and_session():
    db.add_message("sess-del", "user", "临时会话")
    db.clear_session("sess-del")
    assert db.get_session_messages("sess-del") == []
    # get_or_create_session 应能为同 id 重新建表行
    s = db.get_or_create_session("sess-del")
    assert s["message_count"] == 0


def test_list_sessions_sorted_by_recent():
    db.add_message("s-old", "user", "旧会话")
    time.sleep(0.01)
    db.add_message("s-new", "user", "新会话")
    sessions = db.list_sessions()
    ids = [s["id"] for s in sessions]
    assert "s-new" in ids and "s-old" in ids
    # 最近活跃的排最前
    assert sessions[0]["id"] == "s-new"


def test_search_messages_like():
    db.add_message("s1", "user", "如何配置 nginx 反向代理")
    db.add_message("s2", "user", "docker 容器网络")
    hits = db.search_messages("nginx")
    assert len(hits) == 1
    assert "nginx" in hits[0]["content"]


# ─────────────── 文件/文件夹解读缓存 upsert ───────────────
def test_file_doc_upsert_and_strip_underscore_keys():
    db.set_file_doc("scripts/a.sh", "script", {"usage": "启动", "_internal": "secret"})
    doc = db.get_file_doc("scripts/a.sh")
    assert doc is not None
    assert doc["usage"] == "启动"
    assert "_internal" not in doc  # 下划线前缀键被剥离
    assert doc["_kind"] == "script"

    # 覆盖写
    db.set_file_doc("scripts/a.sh", "script", {"usage": "重新生成"})
    doc2 = db.get_file_doc("scripts/a.sh")
    assert doc2["usage"] == "重新生成"


def test_folder_doc_upsert():
    db.set_folder_doc("项目A", {"summary": "概览"})
    doc = db.get_folder_doc("项目A")
    assert doc["summary"] == "概览"
    db.set_folder_doc("项目A", {"summary": "更新概览"})
    assert db.get_folder_doc("项目A")["summary"] == "更新概览"


def test_get_missing_doc_returns_none():
    assert db.get_file_doc("nope") is None
    assert db.get_folder_doc("nope") is None


# ─────────────── 用户备注 ───────────────
def test_user_note_set_get_delete():
    db.set_note("folder:foo", "这是备注")
    assert db.get_note("folder:foo") == "这是备注"
    db.set_note("folder:foo", "")  # 清空保留行
    assert db.get_note("folder:foo") == ""
    db.delete_note("folder:foo")
    assert db.get_note("folder:foo") == ""


def test_get_notes_bulk_by_prefix():
    db.set_note("folder:a", "A")
    db.set_note("folder:b", "B")
    db.set_note("script:c", "C")
    folders = db.get_notes_bulk("folder:")
    assert folders == {"folder:a": "A", "folder:b": "B"}
    assert "script:c" not in folders


# ─────────────── 并发写压力（验证 RLock 可重入 + busy_timeout） ───────────────
def test_concurrent_writes_no_deadlock_no_locked():
    """10 个线程各写 5 条到同一会话，验证：
    1) 不抛 'database is locked'（busy_timeout 生效）
    2) 不死锁（add_message 内部重入 get_or_create_session，RLock 可重入）
    3) 消息总数精确等于 50，无丢失
    """
    sid = "sess-concurrent"
    n_threads = 10
    per_thread = 5
    errors = []

    def worker(tid):
        try:
            for i in range(per_thread):
                db.add_message(sid, "user", f"t{tid}-m{i}")
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    # 给一个较短的 join 超时，若死锁则测试会超时失败
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"并发写出现异常：{errors}"
    # 所有线程必须已结束（否则说明死锁）
    assert all(not t.is_alive() for t in threads), "存在未结束线程，疑似死锁"
    assert len(db.get_session_messages(sid)) == n_threads * per_thread

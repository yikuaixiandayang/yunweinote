#!/usr/bin/env python3
"""build_core 纯函数最小回归测试。

覆盖本次优化涉及的关键逻辑，确保重构（search_blob 预计算、编辑器探测缓存、
日期字段改用 ts 时间戳）不破坏既有行为：
  - categorize       分类规则匹配
  - derive_tags      标签派生（含 ≤3 字符 ASCII 关键词的整词边界）
  - extract_headings 标题抽取（跳过代码块内伪标题）
  - search_notes     全文搜索（子串/子序列、分类与标签过滤、分页）
"""
import os
import sys

# 让测试能直接 import 同级 backend 模块（pytest 工作目录可能不在此）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import build_core as bc


# ───────────────────────── categorize ─────────────────────────
def test_categorize_known_keywords():
    assert bc.categorize("nginx反向代理配置.md") == "Web与中间件"
    assert bc.categorize("Docker容器实战笔记.md") == "容器与编排"
    assert bc.categorize("MySQL主从复制与备份恢复.md") == "数据库与存储"
    assert bc.categorize("Prometheus+Grafana监控告警.md") == "监控与可观测性"


def test_categorize_fallback_to_other():
    # 不含任何分类关键词 → 归为"其他"
    assert bc.categorize("随便写点心得体会.md") == "其他"


# ───────────────────────── derive_tags ─────────────────────────
def test_derive_tags_basic():
    tags = bc.derive_tags("nginx配置.md", [("1", "负载均衡")])
    assert "nginx" in tags
    # 标题命中的关键词也应进标签
    assert "负载" in tags


def test_derive_tags_short_ascii_word_boundary():
    # "ssh" 应命中（整词边界）
    assert "ssh" in bc.derive_tags("ssh免密登录配置.md", [])
    # "sshd" 不应让 "ssh" 误命中（\bssh\b 在 "sshd" 中不成立）
    assert "ssh" not in bc.derive_tags("sshd服务调优.md", [])
    # "redis" 长度 > 3，子串匹配即可
    assert "redis" in bc.derive_tags("redis缓存设计.md", [])


def test_derive_tags_cap():
    # 造一个能命中很多关键词的名字，验证标签上限 12
    many = bc.derive_tags("docker nginx mysql redis kafka git vue ssh linux systemd iptables tomcat ansible zabbix prometheus", [])
    assert len(many) <= 12


# ─────────────────────── extract_headings ───────────────────────
def test_extract_headings_skips_code_block():
    text = (
        "# 一级标题\n"
        "正文\n"
        "## 二级标题\n"
        "```\n"
        "# 这是代码块里的注释，不应被当作标题\n"
        "echo hello\n"
        "```\n"
        "### 三级标题\n"
    )
    heads = bc.extract_headings(text)
    levels_titles = [(lv, t) for lv, t in heads]
    assert ("一级标题",) not in [(t,) for t in [x[1] for x in levels_titles]] or True
    titles = [t for _, t in heads]
    assert "一级标题" in titles
    assert "二级标题" in titles
    assert "三级标题" in titles
    # 代码块内的伪标题不应出现
    assert "这是代码块里的注释，不应被当作标题" not in titles


def test_extract_headings_level_and_cap():
    # 生成 120 个标题，验证 cap=100 截断
    text = "\n".join(f"# 标题{i}" for i in range(120))
    heads = bc.extract_headings(text, cap=100)
    assert len(heads) == 100
    assert heads[0][0] == 1  # 一级


# ───────────────────────── search_notes ─────────────────────────
def _make_payload():
    notes = [
        {
            "id": "n1",
            "name": "nginx反向代理配置.md",
            "rel": "",
            "cat": "Web与中间件",
            "tags": ["nginx", "代理"],
            "mtime": "2026-08-20",
            "ts": 1700000000,
            "_text": "本文介绍 nginx 的反向代理与负载均衡配置方法。",
            "heads": [("1", "反向代理"), ("2", "负载均衡")],
            # 预计算的 search_blob（与 build_index 产出一致）
            "search_blob": "nginx反向代理配置.md 反向代理 负载均衡 本文介绍 nginx 的反向代理与负载均衡配置方法。".lower(),
        },
        {
            "id": "n2",
            "name": "Docker容器实战.md",
            "rel": "",
            "cat": "容器与编排",
            "tags": ["docker"],
            "mtime": "2026-08-21",
            "ts": 1700100000,
            "_text": "docker compose 编排多容器应用。",
            "heads": [("1", "编排")],
            "search_blob": "docker容器实战.md 编排 docker compose 编排多容器应用。".lower(),
        },
    ]
    return {"notes": notes}


def test_search_notes_substr_match():
    payload = _make_payload()
    res = bc.search_notes(payload, "nginx")
    assert res["total"] == 1
    assert res["results"][0]["id"] == "n1"


def test_search_notes_category_filter():
    payload = _make_payload()
    # 分类过滤：查询 docker（命中 n2，分类=容器与编排），应排除 nginx 那条
    res = bc.search_notes(payload, "docker", cat="容器与编排")
    assert res["total"] == 1
    assert res["results"][0]["id"] == "n2"
    # 反向：分类设为 Web与中间件，应只命中 nginx 那条
    res2 = bc.search_notes(payload, "nginx", cat="Web与中间件")
    assert res2["total"] == 1
    assert res2["results"][0]["id"] == "n1"


def test_search_notes_tag_filter():
    payload = _make_payload()
    res = bc.search_notes(payload, "nginx", tag="代理")
    assert res["total"] == 1
    res2 = bc.search_notes(payload, "nginx", tag="不存在的标签")
    assert res2["total"] == 0


def test_search_notes_subsequence_match():
    # "ngx" 不是子串，但是 "nginx" 的子序列 → 应被召回
    payload = _make_payload()
    res = bc.search_notes(payload, "ngx")
    ids = [r["id"] for r in res["results"]]
    assert "n1" in ids


def test_search_notes_empty_query():
    payload = _make_payload()
    res = bc.search_notes(payload, "")
    assert res == {"total": 0, "results": [], "page": 1, "size": 20}


def test_search_notes_pagination():
    # 造 25 条同名命中，验证分页
    notes = []
    for i in range(25):
        notes.append({
            "id": f"x{i}",
            "name": f"nginx笔记{i}.md",
            "cat": "Web与中间件",
            "tags": [],
            "mtime": "2026-08-20",
            "ts": 1700000000 + i,
            "_text": "nginx 相关内容",
            "heads": [],
            "search_blob": f"nginx笔记{i}.md nginx 相关内容".lower(),
        })
    payload = {"notes": notes}
    p1 = bc.search_notes(payload, "nginx", page=1, size=10)
    assert p1["total"] == 25
    assert len(p1["results"]) == 10
    p3 = bc.search_notes(payload, "nginx", page=3, size=10)
    assert len(p3["results"]) == 5

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""笔记索引核心逻辑：扫描、分类、WikiLinks（构建数据层）。

从 build_index.py 中提取，移除模板注入/HTML生成/Flask server/watch mode 等代码。
"""

import os, re, json, hashlib, urllib.parse, datetime, time, subprocess

# winreg 仅 Windows 平台存在；非 Windows（Linux/macOS）导入时降级为 None，
# 使编辑器探测返回"未安装"而非让整个后端在 import 阶段就 ImportError 崩溃。
try:
    import winreg
    HKCR = winreg.HKEY_CLASSES_ROOT
except ImportError:
    winreg = None
    HKCR = None

# 目录定位：backend 位于 app/backend，向上两层到项目根
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))   # E:/运维之路/app/backend
APP_DIR = os.path.dirname(BACKEND_DIR)                     # E:/运维之路/app
SCRIPT_DIR = APP_DIR                                       # 兼容旧名，指向 app/
PROJECT_ROOT = os.path.dirname(APP_DIR)                   # E:/运维之路（项目根）
NOTES_DIR = os.path.join(PROJECT_ROOT, "notes")            # 笔记内容根目录（内容层）
REFERENCES_DIR = os.path.join(PROJECT_ROOT, "references")  # 第三方参考资料（PDF 等）
ROOTS = [
    (NOTES_DIR, "运维笔记"),
    (REFERENCES_DIR, "参考资料"),
]

# 排除目录（扫描时跳过的子目录）
SKIP_DIRS = {".workbuddy", "node_modules", ".git", "CleverPDF", "assets", "images",
             "微服务Demo项目文档", "app", "data", "docs", "archive"}

# 排除文件
SKIP_FILES = {"马哥高级参考索引.md", "SKILL.md", "运维知识笔记索引.md",
              "命名修正与合并总结报告.md", "业务监控集成指南.md", "README.md",
              "_user_data.json"}

# 9 大分类规则
CATEGORY_RULES = [
    ("容器与编排", ["docker", "harbor", "k8s", "kubernetes", "compose", "registry", "镜像"]),
    ("Web与中间件", ["nginx", "tomcat", "nacos", "中间件", "代理", "负载", "注册中心",
                     "kafka", "redis"]),
    ("数据库与存储", ["mysql", "主从", "备份恢复", "lvm", "磁盘", "扩容", "存储",
                      "mount", "nfs", "raid", "rsync", "minio"]),
    ("监控与可观测性", ["prometheus", "zabbix", "elastic", "grafana", "loki", "tempo",
                       "otel", "可观测", "链路追踪", "监控", "logrotate", "日志"]),
    ("网络通信", ["网络", "tcp", "抓包", "tcpdump", "wireshark", "bond", "nmcli", "chrony", "vpn",
                  "netplan"]),
    ("安全防护", ["防火墙", "iptables", "ssh", "fail2ban", "clamav", "漏洞", "tls",
                  "ssl", "证书", "自建ca", "keycloak", "安全"]),
    ("CI/CD与自动化", ["shell", "ansible", "jenkins", "gitlab", "ci", "脚本"]),
    ("编程与构建", ["git", "maven", "vue", "编译", "构建", "正则", "文本处理", "node", "npm"]),
    ("Linux系统基础", ["鸟哥", "rocky", "linux", "ubuntu", "systemd", "sudo",
                       "启动引导", "文件误删", "busybox", "踩坑", "学习日记", "学习笔记",
                       "zsh", "终端", "美化", "yum源", "软件包", "sysctl", "内核", "组件升级",
                       "trash", "回收站", "mount", "挂载", "truncate", "logrotate"]),
]

# 分类图标
CAT_ICONS = {
    "容器与编排": "\U0001f3ed",
    "Web与中间件": "\U0001f310",
    "数据库与存储": "\U0001f5c4\ufe0f",
    "监控与可观测性": "\U0001f4ca",
    "网络通信": "\U0001f4e1",
    "安全防护": "\U0001f512",
    "CI/CD与自动化": "\u2699\ufe0f",
    "编程与构建": "\U0001f528",
    "Linux系统基础": "\U0001f427",
    "其他": "\U0001f4e6",
    "参考资料(PDF)": "\U0001f4c4",
}

TAG_SKIP = {"ci"}


def categorize(name):
    low = name.lower()
    for cat, kws in CATEGORY_RULES:
        if any(k in low for k in kws):
            return cat
    return "其他"


def derive_tags(name, heads):
    """从文件名 + 章节标题中派生标签：命中 CATEGORY_RULES 关键词即记为标签。
    短 ASCII 关键词（<=3 字符）要求整词匹配，避免 ssh 命中 'sshd' 这类情况。"""
    hay = (name + " " + " ".join(t for _, t in heads)).lower()
    tags = []
    for _, kws in CATEGORY_RULES:
        for k in kws:
            kl = k.lower()
            if kl in TAG_SKIP:
                continue
            if len(kl) <= 3 and kl.isascii():
                # 用 re.ASCII：让 \b 只认 ASCII [a-zA-Z0-9_] 为词边界，
                # 这样 "ssh" 紧邻中文（非 ASCII=非词字符）也能识别为词边界而命中，
                # 同时仍排除 "sshd" 这类（h 后是 ASCII 词字符 d，无边界）。
                if not re.search(r"\b" + re.escape(kl) + r"\b", hay, re.ASCII):
                    continue
            elif kl not in hay:
                continue
            if k not in tags:
                tags.append(k)
    return tags[:12]


def derive_name_tags(name):
    """仅从文件名派生标签（不含章节标题）。
    用于分类+标签联动：只有文件名命中的关键词才算"主题相关"，
    章节标题里提到的不算（避免沾边就关联）。"""
    low = name.lower()
    tags = []
    for _, kws in CATEGORY_RULES:
        for k in kws:
            kl = k.lower()
            if kl in TAG_SKIP:
                continue
            if len(kl) <= 3 and kl.isascii():
                # 用 re.ASCII：同 derive_tags，使短 ASCII 关键词在 CJK 边界也能命中
                if not re.search(r"\b" + re.escape(kl) + r"\b", low, re.ASCII):
                    continue
            elif kl not in low:
                continue
            if k not in tags:
                tags.append(k)
    return tags[:12]


def read_text(full):
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(full, encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""


def extract_headings(text, cap=100):
    """抽取一/二/三级标题作为章节大纲（H3 也纳入，便于重点小节被搜索精确定位与大纲展开）。
    cap=100：绝大多数笔记不会超过 100 个一至三级标题，避免截断失真。
    跳过代码块（```/~~~ 包裹）内的内容，避免 YAML/Bash 注释 # 被误识别为标题。
    同时过滤 setext 下划线标题（=====/-----）和纯装饰性文本。"""
    cleaned = re.sub(r'^ {0,3}(```|~~~)[\s\S]*?^\s*\1\s*$',
                     lambda m: '\n' * m.group(0).count('\n'),
                     text, flags=re.MULTILINE)
    heads = []
    for m in re.finditer(r'^(#{1,3})\s+(.+?)\s*$', cleaned, re.MULTILINE):
        level = len(m.group(1))
        title = re.sub(r'[`*_#]', '', m.group(2).strip())
        if not title:
            continue
        if re.match(r'^[=\-*_~`|#\s]+$', title):
            continue
        if re.match(r'^={3,}', title) or re.search(r'={3,}$', title):
            continue
        if len(title) > 80:
            continue
        heads.append((level, title))
        if len(heads) >= cap:
            break
    return heads


def typora_url(full):
    # Typora 的 typora:// 协议实际上是 Electron 内部资源协议（CVE-2023-2316 披露）：
    #   registerFileProtocol('typora', ...) 会取 URL 并做 getRealPath 处理，
    #   其中固定去掉前缀 "typora://app/"（共 13 个字符），然后把剩余部分作为本地文件路径。
    # 因此正确格式必须是 "typora://app/<绝对路径>"，而不是 "typora://D:/...".
    # 若写成 typora://D:/...，Typora 截掉前 13 字符后路径残缺，就会新建一个空白文档。
    abs_path = os.path.abspath(full).replace("\\", "/")
    return "typora://app/" + urllib.parse.quote(abs_path, safe=":/")


def obsidian_url(full):
    """生成 Obsidian 打开链接：obsidian://open?path=<绝对路径>
    Obsidian 原生支持 obsidian:// 协议，path 参数需要 URL 编码的绝对路径。"""
    abs_path = os.path.abspath(full).replace("\\", "/")
    return "obsidian://open?path=" + urllib.parse.quote(abs_path)


def _reg_query(hive, subkey, value_name=None):
    """安全读取注册表值，失败返回 None。非 Windows 平台（winreg=None）直接返回 None。"""
    if winreg is None or hive is None:
        return None
    try:
        key = winreg.OpenKey(hive, subkey)
        val, _ = winreg.QueryValueEx(key, value_name or "")
        winreg.CloseKey(key)
        return val
    except (FileNotFoundError, OSError):
        return None


def detect_editors():
    """检测系统已安装的 Markdown 编辑器（Typora / Obsidian）。
    
    检测策略（双重校验，确保结果可靠）：
      1. 注册表协议注册（HKEY_CLASSES_ROOT\\<protocol>\\shell\\open\\command）
      2. 可执行文件实际存在（os.path.isfile）
    
    返回 dict：
      {
        "typora":   {"installed": bool, "path": "C:\\...\\Typora.exe" or None, "protocol": "typora://"},
        "obsidian": {"installed": bool, "path": "C:\\...\\Obsidian.exe" or None, "protocol": "obsidian://"},
      }
    """
    editors = {}
    
    # ---- Typora ----
    typora_installed = False
    typora_path = None
    # 常见安装路径
    typora_candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Typora", "Typora.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Typora", "Typora.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Typora", "Typora.exe"),
    ]
    for p in typora_candidates:
        if p and os.path.isfile(p):
            typora_path = p
            typora_installed = True
            break
    # 注册表协议校验（双重确认）
    typora_reg = _reg_query(HKCR, r"typora\shell\open\command")
    # HKCR 是 HKLM 与 HKCU\Software\Classes 的合并视图；这里存在且命令包含
    # 有效 exe 才表示浏览器可以实际处理 typora://，仅找到 Typora.exe 不够。
    typora_protocol_registered = bool(typora_reg and re.search(r"\.exe", typora_reg, re.I))
    if typora_reg and not typora_installed:
        # 注册表有但 exe 路径未命中 → 从注册表命令中提取 exe 路径
        m = re.search(r'"([^"]+\.exe)"', typora_reg)
        if m and os.path.isfile(m.group(1)):
            typora_path = m.group(1)
            typora_installed = True
    # 破解/激活工具特征：license-gen.exe / node_inject.exe 出现在 Typora 安装目录
    # 说明 Typora 可能是破解版；这类版本在 license 校验失败时（试用期结束/续期失败）
    # 会静默退出，导致"点了没反应"。标记 cracked 供前端判断，避免误用。
    typora_cracked = False
    if typora_path:
        typora_dir = os.path.dirname(typora_path)
        typora_cracked = (
            os.path.isfile(os.path.join(typora_dir, "license-gen.exe"))
            or os.path.isfile(os.path.join(typora_dir, "node_inject.exe"))
        )
    editors["typora"] = {
        "installed": typora_installed,
        "path": typora_path,
        "protocol": "typora://",
        "protocol_registered": typora_protocol_registered,
        "cracked": typora_cracked,
        "available": typora_installed and typora_protocol_registered,
    }
    
    # ---- Obsidian ----
    obsidian_installed = False
    obsidian_path = None
    obsidian_candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Obsidian", "Obsidian.exe"),
    ]
    for p in obsidian_candidates:
        if p and os.path.isfile(p):
            obsidian_path = p
            obsidian_installed = True
            break
    obsidian_reg = _reg_query(HKCR, r"obsidian\shell\open\command")
    if obsidian_reg and not obsidian_installed:
        m = re.search(r'"([^"]+\.exe)"', obsidian_reg)
        if m and os.path.isfile(m.group(1)):
            obsidian_path = m.group(1)
            obsidian_installed = True
    editors["obsidian"] = {
        "installed": obsidian_installed,
        "path": obsidian_path,
        "protocol": "obsidian://",
    }
    
    return editors


def fmt_size(b):
    return f"{b/1024/1024:.1f} MB" if b >= 1024*1024 else f"{b/1024:.1f} KB"


# 缓存（TTL 60 秒）
_cache = {"payload": None, "ts": 0, "ttl": 60}

# 编辑器探测结果缓存：detect_editors() 读注册表 + 探测 exe 存在性，开销不小，
# 且编辑器基本不变。单独用长 TTL 缓存（1 小时），避免每次冷缓存 build_index 都重跑。
_editors_cache = {"value": None, "ts": 0, "ttl": 3600}


def _get_editors():
    """带长 TTL 缓存的编辑器探测（Typora / Obsidian）。"""
    now = time.time()
    if _editors_cache["value"] is not None and (now - _editors_cache["ts"]) < _editors_cache["ttl"]:
        return _editors_cache["value"]
    ed = detect_editors()
    _editors_cache["value"] = ed
    _editors_cache["ts"] = now
    return ed


def invalidate_cache():
    """强制缓存失效，下次 build_index() 会重新扫描"""
    _cache["ts"] = 0

def build_index() -> dict:
    """执行完整扫描，返回 payload dict（带 60 秒 TTL 缓存）"""
    now = time.time()
    if _cache["payload"] and (now - _cache["ts"]) < _cache["ttl"]:
        return _cache["payload"]

    # ---------------- 扫描收集 ----------------
    notes, pdfs = [], []
    total_bytes = 0
    
    # 检测已安装的编辑器（Typora / Obsidian），用于生成 openurl（结果长 TTL 缓存）
    editors = _get_editors()
    has_typora = editors["typora"].get("available", False)
    has_obsidian = editors["obsidian"]["installed"]
    
    for root, label in ROOTS:
        for dirpath, dirnames, filenames in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            parts = rel.split(os.sep)
            if any(p in SKIP_DIRS for p in parts) or any(p.startswith("_") for p in parts):
                dirnames[:] = []
                continue
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                relpath = os.path.relpath(full, root)
                low = fn.lower()
                if fn in SKIP_FILES:
                    continue
                if fn.startswith("backup_"):
                    continue
                if low.endswith(".md"):
                    text = read_text(full)
                    heads = extract_headings(text)
                    size = os.path.getsize(full)
                    mtime = os.path.getmtime(full)
                    cat = categorize(fn)
                    # openurl：优先 Obsidian，其次 Typora，均未安装则为 null（前端降级到浏览器预览）
                    if has_obsidian:
                        openurl = obsidian_url(full)
                    elif has_typora:
                        openurl = typora_url(full)
                    else:
                        openurl = None
                    notes.append({
                        "id": hashlib.md5(relpath.encode("utf-8")).hexdigest()[:12],
                        "name": fn, "rel": relpath,
                        "fileurl": "./" + urllib.parse.quote(relpath.replace("\\", "/")),
                        "typoraurl": typora_url(full),
                        "obsidianurl": obsidian_url(full),
                        "openurl": openurl,
                        "size": fmt_size(size),
                        "ts": int(mtime),
                        "mtime": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                        "heads": heads, "cat": cat, "tags": derive_tags(fn, heads),
                        "nameTags": derive_name_tags(fn),
                        "lines": text.count("\n") + 1,
                        "stub": size < 200,
                        # 预计算小写化搜索串（name+标题+正文），供 search_notes 直接复用，
                        # 避免每次搜索都对全量笔记重复 .lower() 拼接。仅用于后端搜索，前端不返回。
                        "search_blob": (fn + " " + " ".join(h for _, h in heads) + " " + text).lower(),
                        "_text": text,
                    })
                    total_bytes += size
                elif low.endswith(".pdf"):
                    mtime = os.path.getmtime(full)
                    size = os.path.getsize(full)
                    if has_typora:
                        openurl = typora_url(full)
                    elif has_obsidian:
                        openurl = obsidian_url(full)
                    else:
                        openurl = None
                    pdfs.append({
                        "id": "p" + hashlib.md5(relpath.encode("utf-8")).hexdigest()[:10],
                        "name": fn, "rel": relpath,
                        "fileurl": "./" + urllib.parse.quote(relpath.replace("\\", "/")),
                        "typoraurl": typora_url(full),
                        "obsidianurl": obsidian_url(full),
                        "openurl": openurl,
                        "size": fmt_size(size),
                        "ts": int(mtime),
                        "mtime": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                        "heads": [], "cat": "参考资料(PDF)", "tags": ["PDF"],
                        "lines": 0, "stub": False,
                    })
                    total_bytes += size

    # ==================== WikiLinks 双向引用扫描（联合正则优化）====================
    name_to_id = {}
    for n in notes:
        name_wo = n["name"].replace(".md", "")
        name_to_id[name_wo] = n["id"]
    # 构建一个联合正则：所有笔记名（按长度降序，避免短名先匹配）
    all_names = sorted(name_to_id.keys(), key=len, reverse=True)
    if all_names:
        combined_re = re.compile("|".join(re.escape(nm) for nm in all_names))
    else:
        combined_re = None
    id_by_name = {nm: name_to_id[nm] for nm in all_names}
    for n in notes:
        refs = set()
        if combined_re:
            for m in combined_re.finditer(n.get("_text", "")):
                matched = m.group()
                nid = id_by_name.get(matched)
                if nid and nid != n["id"]:
                    refs.add(nid)
        n["wikilinks"] = list(refs)
    # 保留 _text 用于搜索（截断到 50KB 避免 payload 过大）
    for n in notes:
        txt = n.get("_text", "")
        if len(txt) > 51200:
            txt = txt[:51200]
        n["_text"] = txt

    cat_order = [c for c in ["容器与编排", "Web与中间件", "数据库与存储", "监控与可观测性",
                             "网络通信", "安全防护", "CI/CD与自动化", "编程与构建",
                             "Linux系统基础", "其他"]
                 if any(n["cat"] == c for n in notes)]
    if pdfs:
        cat_order.append("参考资料(PDF)")
    total_size_str = fmt_size(total_bytes)

    payload = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "roots": [lab for _, lab in ROOTS],
        "catOrder": cat_order,
        "catIcons": CAT_ICONS,
        "notes": notes,
        "pdfs": pdfs,
        "stats": {"md": len(notes), "pdf": len(pdfs), "totalSize": total_size_str},
        "refIndex": "马哥高级参考索引.md",
        "editors": editors,
    }
    # 写入缓存
    _cache["payload"] = payload
    _cache["ts"] = now
    return payload


def search_notes(payload: dict, q: str, cat: str = None, tag: str = None,
                 sort: str = "relevance", page: int = 1, size: int = 20) -> dict:
    """全文搜索笔记，返回分页结果。
    
    参数：
        q: 搜索关键词（支持子串/子序列/正则模糊匹配）
        cat: 按分类过滤（可选）
        tag: 按标签过滤（可选）
        sort: 排序方式 - relevance(默认)/mtime/name
        page/size: 分页
        
    返回：
        { total, results: [{id, name, rel, cat, tags, mtime, excerpt, score}, ...] }
    """
    if not q:
        return {"total": 0, "results": [], "page": page, "size": size}
    
    ql = q.lower().strip()
    # 构建查询模式的多种匹配：子串、子序列
    scored = []
    
    all_items = payload.get("notes", [])
    
    for n in all_items:
        name = n.get("name", "")
        text = n.get("_text", "")
        heads = n.get("heads", [])
        tags_list = n.get("tags", [])
        # 复用 build_index 阶段预计算的小写 search_blob，避免每次搜索重复 .lower() 拼接
        search_text = n.get("search_blob", "")
        if not search_text:
            search_text = (name + " " + " ".join(t for _, t in heads) + " " + text).lower()
        
        # 1) 子串匹配
        substr_score = 0
        if ql in search_text:
            # 在不同字段中命中给不同权重
            if ql in name.lower():
                substr_score = 100
            elif any(ql in h[1].lower() for h in heads):
                substr_score = 60
            else:
                substr_score = 30
        
        # 2) 子序列匹配（连续字符按顺序出现）
        seq_score = 0
        if substr_score == 0:
            idx = 0
            for ch in ql:
                found = search_text.find(ch, idx)
                if found == -1:
                    break
                idx = found + 1
            else:
                # 全部字符都找到了
                seq_score = max(1, 20 - idx // 10)
        
        score = max(substr_score, seq_score)
        if score == 0:
            continue
        
        # 分类过滤
        if cat and n.get("cat") != cat:
            continue
        # 标签过滤
        if tag and tag not in tags_list:
            continue
        
        # 提取一段摘要（从命中位置前后截取）
        excerpt = ""
        pos = text.lower().find(ql)
        if pos >= 0:
            start = max(0, pos - 40)
            end = min(len(text), pos + len(ql) + 80)
            excerpt = text[start:end].replace("\n", " ").strip()
            if start > 0:
                excerpt = "…" + excerpt
            if end < len(text):
                excerpt = excerpt + "…"
        
        scored.append({
            "id": n["id"],
            "name": name,
            "rel": n.get("rel", ""),
            "cat": n.get("cat", ""),
            "tags": tags_list,
            "mtime": n.get("mtime", ""),
            "ts": n.get("ts", 0),
            "excerpt": excerpt[:200],
            "score": score,
        })
    
    # 排序
    if sort == "mtime":
        scored.sort(key=lambda x: x["ts"], reverse=True)
    elif sort == "name":
        scored.sort(key=lambda x: x["name"])
    else:
        scored.sort(key=lambda x: (-x["score"], x["name"]))
    
    total = len(scored)
    # 分页（移除 _text 后再返回）
    start = (page - 1) * size
    end = start + size
    results = scored[start:end]
    for r in results:
        r.pop("ts", None)
    
    return {
        "total": total,
        "results": results,
        "page": page,
        "size": size,
    }


if __name__ == "__main__":
    result = build_index()
    print(f"笔记(.md): {len(result['notes'])} 篇, PDF: {len(result['pdfs'])} 个")
    print(f"总体积: {result['stats']['totalSize']}")
    print("分类统计:")
    for c in result['catOrder']:
        n_in = sum(1 for n in result['notes'] + result['pdfs'] if n['cat'] == c)
        print(f"  - {c}: {n_in} 篇")

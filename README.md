# 📚 运维知识库

> 一个运维工程师的完整知识体系：99 篇 Markdown 笔记、PDF 参考资料、全文搜索、智能推荐、关系图谱。
>
> **后端：** FastAPI (Python 3.10+) · **前端：** Vue 3 + Vite · **目录结构：** 内容层（notes/）与 应用层（app/，含后端、前端、运行时数据）分离

---

## 📁 项目结构

```
E:/运维之路/
├── notes/               ← 📄 **内容层** — 所有 .md 笔记文件（75+ 篇）
├── app/                 ← ⚙️ **应用层**（项目全部代码 + 运行时数据）
│   ├── backend/         ← FastAPI 后端
│   │   ├── main.py      ← 入口（启动配置 + 路由注册）
│   │   ├── build_core.py← 核心逻辑（扫描、分类、搜索、推荐）
│   │   ├── requirements.txt
│   │   ├── _env/        ← Python 虚拟环境（自动创建，已 gitignore）
│   │   ├── start.bat    ← Windows 一键启动
│   │   └── start.sh     ← Linux/macOS 一键启动
│   ├── frontend/        ← Vue 3 + Vite 前端
│   │   ├── src/         ← 源码（组件 + stores + 路由）
│   │   └── dist/        ← 构建产物（由后端直接托管）
│   ├── data/            ← 🗃️ **运行时层** — 用户数据（已 gitignore）
│   │   └── user_data.json ← 收藏/已读/搜索历史 持久化
│   └── README.md        ← 项目说明
├── archive/             ← 历史归档（旧版备份）
├── docs/                ← 项目文档
└── references/          ← 第三方参考资料（CleverPDF 等）
```

笔记（`notes/`）与代码（`app/`）完全解耦，内容可独立同步；`app/` 内聚全部应用代码与运行时数据。

---

## 🚀 快速启动

### Windows

```bash
# 双击，或命令行运行：
cd backend
start.bat
```

### Linux / macOS

```bash
cd backend
bash start.sh
```

启动后打开 **http://localhost:8000**

> 一键脚本会自动：检测 Python → 创建 venv → 安装依赖 → 构建前端 → 启动服务。

### 前端开发模式（热更新）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173

---

## ⚙️ 常用参数配置

> 下列"修改位置"均给出**真实行号**（基于当前 `main.py` / `config.py` / `build_core.py`），便于直接定位。

| 参数 | 默认值 | 修改位置 | 说明 |
|------|--------|---------|------|
| **服务端口** | `8000` | `backend/main.py` 第 96 行：`port=8000` | 修改为任意端口 |
| **绑定 IP** | `127.0.0.1` | 同上：`host="127.0.0.1"` | `127.0.0.1` = 仅本机可访问；如需局域网访问改为 `0.0.0.0`（注意暴露风险） |
| **热重载** | 关闭（默认） | 同上：`reload=dev_reload`，由环境变量 `KB_DEV=1` 开启 | 开发时自动检测文件变更重启；生产保持默认关闭，避免 notes/ 改动触发多余子进程 |
| **笔记根目录** | `notes/` | `backend/build_core.py` 第 24 行 `NOTES_DIR` / 第 26~29 行 `ROOTS` | 笔记文件放这里即可被自动扫描 |
| **缓存有效期** | 60 秒 | `backend/build_core.py` 第 286 行 `"ttl": 60` | API 请求间隔 < TTL 时不重新扫描磁盘 |
| **排除目录** | `.workbuddy` / `node_modules` / `.git` / `CleverPDF` / `assets` 等 | `backend/build_core.py` 第 32~38 行 `SKIP_DIRS` / `SKIP_FILES` | 不想被扫描到的目录/文件加进来 |
| **分类规则** | 9 大类（容器/Web/数据库/监控/网络/安全/CI/编程/Linux） | `backend/build_core.py` 第 41~59 行 `CATEGORY_RULES` | 新增分类或调整关键词匹配规则 |
| **用户数据文件** | `app/data/user_data.json` | `backend/config.py` 第 20 行 `USER_DATA_FILE` | 用户收藏/已读/搜索历史持久化位置 |
| **前端构建产物** | `app/frontend/dist/` | `backend/config.py` 第 19 行 `FRONTEND_DIST` | 前端 build 后的静态文件目录 |

---

## 🌐 API 接口一览

> 所有 `/api/*` 路由在 `main.py` 中统一以 `/api` 前缀挂载；以下列表省略前缀，写全路径即为实际 URL（如 `/api/search`）。

### 页面与静态资源

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（SPA 入口，托管前端构建产物） |
| `/graph` | GET | 关系图谱页面（前端路由，由 `/` 托管） |
| `/assets/*` | GET | 前端静态资源（带 hash，长缓存） |
| `/files/{path}` | GET | 读取笔记目录下的文件（图片等附件），含路径遍历防护 |

### 笔记索引 / 搜索 / 用户数据（`routers/notes.py`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/data` | GET | 笔记全量数据 + 用户行为数据 |
| `/api/note` | GET | 笔记列表（精简版） |
| `/api/note/{name}` | GET | 读取指定笔记内容 |
| `/api/search?q=&cat=&tag=&sort=&page=&size=` | GET | 全文搜索（子串 + 子序列模糊匹配） |
| `/api/insights` | GET | 统一洞察：评分推荐 / 知识缺口 / 分类覆盖度 / 陈旧笔记 / 知识枢纽 / 热门标签 / 兴趣推荐 |
| `/api/rebuild` | POST | 强制重新扫描笔记目录并刷新缓存 |
| `/api/data/save` | POST | 持久化用户数据到 `app/data/user_data.json` |
| `/api/typora/status` | GET | 检测 Typora 可执行文件与 `typora://` 协议可用状态 |
| `/api/typora/open/{name}` | POST | 用 Typora 打开指定笔记 |
| `/api/typora/repair` | POST | 修复 Typora 协议注册（运行 `scripts/fix_typora_protocol.ps1`） |

### 脚本库（`routers/scripts.py`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/scripts` | GET | 脚本库列表 |
| `/api/script/{path}` | GET | 读取指定脚本内容 |
| `/api/script-locate/{path}` | GET | 定位脚本在磁盘上的路径 |
| `/api/script-download/{path}` | GET | 下载脚本文件 |
| `/api/script-note/{path}` | PUT | 保存脚本的 AI 解读（用途/用法/工作过程） |
| `/api/script-note/{path}` | DELETE | 删除脚本解读 |

### 文件夹（`routers/folders.py`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/folders` | GET | 一级文件夹列表 |
| `/api/folder/{name}/tree` | GET | 文件夹目录树 |
| `/api/folder/{name}/readme` | GET | 文件夹 README（AI 生成的解读） |
| `/api/folder/{name}/file/{path}` | GET | 读取文件夹内文件 |
| `/api/folder/{name}/asset/{path}` | GET | 读取文件夹内图片等静态资源 |
| `/api/folder/{name}/download/{path}` | GET | 下载文件夹内文件 |
| `/api/folder/{name}/note` | PUT | 保存文件夹级笔记 |
| `/api/folder/{name}/note` | DELETE | 删除文件夹级笔记 |
| `/api/folder-file-note/{name}/{path}` | PUT | 保存文件夹内某文件的解读 |
| `/api/folder-file-note/{name}/{path}` | DELETE | 删除文件夹内某文件的解读 |

### AI Agent（`routers/agent.py`：SSE 流式 + 普通 JSON）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/agent/config` | GET/POST | 读取 / 更新 Agent 配置（模型、API Key 等） |
| `/api/agent/health` | GET | 检查 LLM 后端连通性 |
| `/api/agent/summarize` | POST | 总结单篇笔记 |
| `/api/agent/organize` | POST | 整理多篇笔记结构 |
| `/api/agent/recommend-path` | POST | 推荐学习路径 |
| `/api/agent/optimize-algorithm` | POST | 给出算法/代码优化建议 |
| `/api/agent/study-plan` | GET | 获取动态学习计划 |
| `/api/agent/study-plan/generate` | POST | 生成学习计划 |
| `/api/agent/study-plan/feedback` | POST | 学习计划反馈 |
| `/api/agent/study-plan/item` | POST | 更新学习计划单项状态 |
| `/api/agent/study-path` | GET | 获取学习路径图数据 |
| `/api/agent/chat` | POST | 非流式对话（前端 SSE 失败时的兜底通道，已用线程池避免阻塞事件循环） |
| `/api/agent/chat/stream` | POST | SSE 流式对话 |
| `/api/agent/describe` | GET/POST | 解读单个笔记 / 脚本 |
| `/api/agent/describe-folder` | GET/POST | 解读文件夹 |
| `/api/agent/describe-folder-readme` | POST | 生成文件夹 README |
| `/api/agent/refresh-all` | POST | 一键全量更新描述（AI 生成/刷新所有脚本解读 + 一级文件夹描述），`?force=1` 强制重生成；后台串行执行，返回 `{started,total}` |
| `/api/agent/refresh-all/progress` | GET | 查询一键更新任务进度：`{running,total,done,failed,stage,current,recentDetails}` |
| `/api/agent/sessions` | GET | 列出对话会话 |
| `/api/agent/session/{sid}` | GET/DELETE | 读取 / 删除指定会话 |

### 外观（`routers/appearance.py`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/appearance` | GET/POST | 读取 / 更新界面外观配置 |
| `/api/appearance/image` | GET | 读取外观相关图片资源 |

### 全文搜索示例

```bash
# 搜索 nginx 相关笔记（按相关性排序）
curl "http://localhost:8000/api/search?q=nginx"

# 搜索 + 按分类过滤 + 分页
curl "http://localhost:8000/api/search?q=docker&cat=容器与编排&page=1&size=10"

# 按最近更新时间排序
curl "http://localhost:8000/api/search?q=mysql&sort=mtime"
```

---

## ⚠️ 安全说明

- `/api/note/{name}` 和 `/files/{path}` 做了**路径遍历防护**，只能访问笔记目录内的文件
- 如果部署到公网，建议在前面加一层 Nginx 反向代理做访问控制
- 用户学习进度数据（`app/data/user_data.json`）不含敏感信息

---

## ♻️ 迁移到新机器

```bash
1. 拷贝整个 E:/运维之路/ 到新机器
2. 双击 backend/start.bat（自动检测环境）
   - 或 Linux 下运行 bash backend/start.sh
3. 浏览器打开 http://localhost:8000
```

用户学习进度在 `app/data/` 目录（已 gitignore），拷贝时带上即可保留收藏/已读记录。

---

## 🐾 作者

- **笔记维护：** 杨（运维工程师）
- **系统构建：** 阿勒（AI 搭档）

---

*知识库持续迭代中。如有配置问题，在 `backend/` 下的 `main.py` 和 `build_core.py` 中搜索对应关键词即可找到配置项。*

# 动态学习计划功能实现方案（给 qwen 的提示词）

## 需求概述

用户希望系统能自动告诉他"今天该学什么、明天该学什么、本周该学什么、本月该学什么"。
- 如果接入了 Agent（Hermes 可用），根据笔记进度 + 学习路径 + 用户反馈自动更新计划
- 如果没接入 Agent（Hermes 不可用），保持上次的计划不变
- 跟现有的 `recommend_path` 不同：那个是一次性生成完整路径，这个是**分时间维度的动态计划**，且能自动更新

## 核心设计

### 数据结构（新增到 user_data.json）

```json
{
  "studyPlan": {
    "version": 1,
    "lastUpdated": "2026-08-26T10:00:00",
    "lastUpdatedBy": "hermes",
    "goal": "成为全栈运维工程师",
    "daily": {
      "date": "2026-08-26",
      "items": [
        {"noteId": "abc123", "noteName": "Redis 运维实战笔记", "reason": "你在学存储，这是下一步", "estimatedHours": 2, "status": "pending"}
      ]
    },
    "tomorrow": {
      "date": "2026-08-27",
      "items": [
        {"noteId": "def456", "noteName": "Ceph 分布式存储系统学习笔记", "reason": "存储方向深入", "estimatedHours": 3, "status": "pending"}
      ]
    },
    "weekly": {
      "weekStart": "2026-08-25",
      "items": [
        {"noteId": "abc123", "noteName": "Redis 运维实战笔记", "reason": "存储方向", "estimatedHours": 2, "status": "done"},
        {"noteId": "def456", "noteName": "Ceph 分布式存储系统学习笔记", "reason": "存储深入", "estimatedHours": 3, "status": "pending"},
        {"noteId": "ghi789", "noteName": "华为FusionCompute iSCSI存储接入实战学习笔记", "reason": "存储接入实战", "estimatedHours": 2, "status": "pending"}
      ]
    },
    "monthly": {
      "monthStart": "2026-08-01",
      "theme": "存储与虚拟化",
      "items": [
        {"category": "数据库与存储", "targetCount": 5, "currentCount": 2, "reason": "存储方向是这个月的重点"},
        {"category": "容器与编排", "targetCount": 3, "currentCount": 1, "reason": "K8s 暂缓但 Docker 要深入"}
      ]
    },
    "history": [
      {"date": "2026-08-25", "completed": 2, "planned": 3, "notes": ["id1", "id2"]}
    ]
  }
}
```

### 后端实现（routers/agent.py 新增端点）

```python
# ===== 新增 API 端点 =====

@router.get("/agent/study-plan")
async def api_get_study_plan():
    """获取当前学习计划（如果不存在返回空）"""
    cfg = _get_agent_config()
    ud = app_data.get("user_data", {})
    plan = ud.get("studyPlan")
    if not plan:
        return JSONResponse({"plan": None, "message": "尚未生成学习计划"})
    return JSONResponse({"plan": plan})

@router.post("/agent/study-plan/generate")
async def api_generate_study_plan(request: Request):
    """生成或更新学习计划（调用 Hermes/pcl AI）"""
    try:
        body = await request.json()
        goal = body.get("goal", "")
        feedback = body.get("feedback", "")  # 用户反馈："今天学的太难了"/"想多学点网络"
        
        _sync_agent_config()
        from build_core import build_index
        payload = build_index()
        result = ai_agent.generate_study_plan(
            notes=payload["notes"],
            user_data=app_data.get("user_data", {}),
            goal=goal,
            feedback=feedback
        )
        
        if result.get("ok"):
            # 保存到 user_data
            ud = app_data.get("user_data", {})
            ud["studyPlan"] = result["plan"]
            save_user_data(ud)
            return JSONResponse({"ok": True, "plan": result["plan"]})
        else:
            # AI 不可用 → 保持旧计划不变
            old_plan = app_data.get("user_data", {}).get("studyPlan")
            return JSONResponse({"ok": False, "plan": old_plan, "message": "AI 不可用，保持上次计划不变"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@router.post("/agent/study-plan/feedback")
async def api_study_plan_feedback(request: Request):
    """用户反馈：标记完成/调整难度/反馈意见"""
    try:
        body = await request.json()
        note_id = body.get("noteId", "")
        action = body.get("action", "")  # "done" / "skip" / "hard" / "easy" / "feedback"
        feedback_text = body.get("feedback", "")
        
        ud = app_data.get("user_data", {})
        plan = ud.get("studyPlan", {})
        
        # 更新 daily/weekly 中的状态
        for period in ["daily", "tomorrow", "weekly"]:
            if period in plan:
                for item in plan[period].get("items", []):
                    if item.get("noteId") == note_id:
                        item["status"] = "done" if action == "done" else action
                        if feedback_text:
                            item["feedback"] = feedback_text
        
        ud["studyPlan"] = plan
        save_user_data(ud)
        
        return JSONResponse({"ok": True, "plan": plan})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
```

### AI 生成逻辑（agent.py 新增函数）

```python
def generate_study_plan(notes: list[dict], user_data: dict, goal: str = "", feedback: str = "") -> dict:
    """根据笔记进度 + 已读记录 + 用户反馈，生成分时间维度的学习计划。"""
    
    # 1. 分析当前进度
    read_ids = set(user_data.get("read", []))
    total = len([n for n in notes if not n.get("stub")])
    read_count = len([n for n in notes if n["id"] in read_ids and not n.get("stub")])
    
    # 2. 按分类统计已读/未读
    from collections import Counter
    cat_total = Counter(n["cat"] for n in notes if not n.get("stub"))
    cat_read = Counter(n["cat"] for n in notes if n["id"] in read_ids and not n.get("stub"))
    
    # 3. 找出未读笔记（候选）
    unread = [n for n in notes if n["id"] not in read_ids and not n.get("stub")]
    
    # 4. 构建 AI 提示词
    user_ctx = f"""## 当前进度
- 总笔记: {total} 篇，已读: {read_count} 篇，未读: {len(unread)} 篇
- 各分类进度: {', '.join(f'{c}({cat_read[c]}/{cat_total[c]})' for c in cat_total)}

## 已读笔记（最近）
{chr(10).join(f'- {n["name"].replace(".md","")}' for n in notes if n["id"] in read_ids)[:2000]}

## 未读笔记（候选）
{chr(10).join(f'- id={n["id"]} | {n["name"].replace(".md","")} | {n["cat"]}' for n in unread[:50])[:3000]}

## 用户反馈
{feedback if feedback else "无"}"""

    prompt = f"""你是一位运维学习规划师。请基于用户的学习进度，生成一个分时间维度的学习计划。

{user_ctx}

## 学习目标
{goal if goal else "根据已有笔记推断合理目标"}

## 输出要求
1. **今日（1-2篇）**：选最该学的，优先跟上次学的内容连续
2. **明日（1-2篇）**：今日学完后的下一步
3. **本周（3-5篇）**：这一周要覆盖的内容，有主题
4. **本月主题**：这个月的重点方向 + 各分类目标篇数
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
}}"""

    try:
        r = _chat_with_fallback(
            [{"role": "system", "content": "你是运维学习规划师，只输出JSON。"},
             {"role": "user", "content": prompt}],
            temperature=0.5
        )
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error", "AI 不可用")}
        
        plan_data = _safe_json(r["content"])
        if not plan_data:
            return {"ok": False, "error": "AI 返回格式错误"}
        
        # 补充元数据
        from datetime import datetime, timedelta
        today = datetime.now()
        plan_data["version"] = 1
        plan_data["lastUpdated"] = today.isoformat(timespec='hours')
        plan_data["lastUpdatedBy"] = r.get("backend", "unknown")
        plan_data["daily"]["date"] = today.strftime("%Y-%m-%d")
        plan_data["tomorrow"]["date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        plan_data["weekly"]["weekStart"] = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        plan_data["monthly"]["monthStart"] = today.strftime("%Y-%m-01")
        
        return {"ok": True, "plan": plan_data}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

### 前端实现

#### 新增页面：StudyPlanPage.vue

```vue
<!-- 路由：#/study-plan -->
<!-- 四个卡片：今日 / 明日 / 本周 / 本月 -->
<!-- 每个卡片里有学习项列表，可标记完成/跳过/反馈 -->
<!-- 顶部有"刷新计划"按钮（调 AI 重新生成） -->
<!-- AI 不可用时显示"保持上次计划" -->
```

#### 前端路由新增

```javascript
// router/index.js 新增
{ path: '/study-plan', name: 'study-plan', component: StudyPlanPage }
```

#### 前端 Store 新增（stores/studyPlan.js）

```javascript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useStudyPlanStore = defineStore('studyPlan', () => {
  const plan = ref(null)
  const loading = ref(false)
  
  async function load() {
    const res = await fetch('/api/agent/study-plan')
    const data = await res.json()
    plan.value = data.plan
  }
  
  async function generate(goal = '', feedback = '') {
    loading.value = true
    const res = await fetch('/api/agent/study-plan/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, feedback })
    })
    const data = await res.json()
    if (data.ok) {
      plan.value = data.plan
    }
    loading.value = false
    return data
  }
  
  async function feedback(noteId, action, text = '') {
    const res = await fetch('/api/agent/study-plan/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ noteId, action, feedback: text })
    })
    const data = await res.json()
    if (data.ok) plan.value = data.plan
    return data
  }
  
  return { plan, loading, load, generate, feedback }
})
```

### 自动更新机制

```python
# 在 routers/agent.py 启动时注册一个定时检查
# 每天凌晨自动检查是否需要更新计划

# 方式1：前端每次打开学习计划页面时检查
# 如果 daily.date != 今天 → 调 AI 更新计划
# 如果 AI 不可用 → 保持旧计划

# 方式2：后端定时任务（在 main.py 里用 APScheduler）
# 每天 6:00 自动更新今日计划
# 如果 AI 不可用 → 保持不变，等 AI 恢复后再更新
```

### 前端交互流程

```
用户打开学习计划页面
  │
  ├── 加载现有计划（GET /api/agent/study-plan）
  │     ├── 有计划且日期是今天 → 显示
  │     └── 无计划或日期过期 → 显示"生成计划"按钮
  │
  ├── 用户点"生成计划"或"刷新计划"
  │     ├── 调 POST /api/agent/study-plan/generate
  │     │     ├── AI 可用 → 生成新计划 → 保存 → 显示
  │     │     └── AI 不可用 → 保持旧计划 → 提示"AI 不可用，保持上次计划"
  │     └── 用户可填反馈："想多学点网络" / "太难了" / "太简单"
  │
  ├── 每个学习项卡片
  │     ├── 点"完成" → POST /api/agent/study-plan/feedback {action: "done"}
  │     ├── 点"跳过" → POST /api/agent/study-plan/feedback {action: "skip"}
  │     └── 点"反馈" → 输入意见 → 下次生成时 AI 会参考
  │
  └── 完成今日所有项后
        └── 提示"今日学习完成！明日计划已就绪"
```

### 页面布局建议

```
┌─────────────────────────────────────────────────┐
│  📅 学习计划          [刷新计划] [设置目标]       │
│  目标：成为全栈运维工程师 | 上次更新：2小时前      │
├─────────────────────────────────────────────────┤
│                                                 │
│  📌 今日（8月26日）           2/3 完成           │
│  ┌───────────────────────────────────────────┐  │
│  │ ✅ Redis 运维实战笔记          2h  [完成]  │  │
│  │ ⬜ Ceph 分布式存储系统学习笔记  3h  [完成]  │  │
│  │ ⬜ iSCSI 存储接入实战笔记       2h  [跳过]  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  📌 明日（8月27日）                              │
│  ┌───────────────────────────────────────────┐  │
│  │ ⬜ Kubernetes 集群部署笔记      4h  [待学]  │  │
│  │ ⬜ Ansible 运维自动化学习笔记   2h  [待学]  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  📌 本周（8月25日-31日）      主题：存储与虚拟化  │
│  ┌───────────────────────────────────────────┐  │
│  │ ✅ Redis 运维实战笔记                      │  │
│  │ ⬜ Ceph 分布式存储系统学习笔记              │  │
│  │ ⬜ iSCSI 存储接入实战笔记                   │  │
│  │ ⬜ FusionCompute iSCSI存储接入              │  │
│  │ ⬜ 华为防火墙多公网接入                      │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  📌 本月（8月）             主题：存储与虚拟化    │
│  ┌───────────────────────────────────────────┐  │
│  │ 数据库与存储    2/5 篇  ████████░░░░ 40%  │  │
│  │ 容器与编排      1/3 篇  ████░░░░░░░░ 33%  │  │
│  │ 网络通信        3/4 篇  ██████████░░ 75%  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  💬 反馈：[太难了] [太简单] [自定义反馈...]       │
└─────────────────────────────────────────────────┘
```

## 核心原则

1. **AI 可用 → 自动更新计划**：根据进度+反馈重新生成
2. **AI 不可用 → 保持上次计划不变**：不报错，不覆盖
3. **用户反馈驱动**：标记完成/跳过/太难/太简单，下次生成时 AI 参考
4. **分时间维度**：今日/明日/本周/本月，不是一次性生成完整路径
5. **进度可视化**：每个维度有完成度，本月有分类进度条
6. **日期过期自动更新**：前端检测到 daily.date != 今天 → 自动调 generate

## 不要改的
- 不改现有 recommend_path（那个是完整路径，跟动态计划互补）
- 不改现有 chat 功能（独立功能）
- 不改 build_core.py（只用它的 build_index 获取笔记列表）
- 不改 db.py（学习计划存 user_data.json 不存 SQLite）

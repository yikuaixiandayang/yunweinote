<script setup>
/**
 * 动态学习计划页（联动版 v2，#/study-plan）
 *
 * 方案 B 布局：主题横幅 → 已完成折叠 → 当前步骤大卡片（今日任务内嵌）→ 待学习弱化
 *            → 展望面板（明日/本周）→ 本月分类进度 → 学习轨迹
 *
 * - 路径是唯一事实来源：计划任务带 pathStepId，完成回流路径（步骤变绿）
 * - 顺序归代码：今日 = 路径下一个未完成步骤（后端保证），前端只展示
 * - 双向锚定：任务"第N步"徽章 → 滚动高亮步骤行；步骤行 → 滚动高亮其任务组
 * - 手动任务带"手动"徽章（source=manual），完成不推进路径
 * - 过期不自动调 AI：顶部横幅提示，用户主动点"刷新计划"
 * - 无路径：引导卡一键"生成学习路径并创建计划"
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyPlanStore } from '../stores/studyPlan'
import { useNotesStore } from '../stores/notes'
import AppHeader from '../components/AppHeader.vue'
import AppIcon from '../components/AppIcon.vue'

const planStore = useStudyPlanStore()
const notes = useNotesStore()
const router = useRouter()

/** 跳转学习路径页（执行 → 地图），带当前步骤 noteId 让 /path 聚焦到"我在哪"。
 *  P3.2 语义修正：跳转后 /path 会聚焦当前步骤节点（时间线滚动定位 + 图谱高亮上下游），
 *  而非展示无重点的全库拓扑。 */
function goPath() {
  const focusNoteId = currentStep.value?.noteId || ''
  router.push(focusNoteId ? `/learning?focus=${encodeURIComponent(focusNoteId)}` : '/learning')
}

const plan = computed(() => planStore.plan)
const loading = computed(() => planStore.loading)
const errorMsg = computed(() => planStore.error)
const degraded = computed(() => planStore.degraded)

const goalInput = ref('')
const goalEditing = ref(false)
const feedbackInput = ref('')
const feedbackTargetId = ref(null)
const globalFeedback = ref('')   // 刷新计划时附带的整体反馈
const manualName = ref('')
const manualHours = ref(1)

const todayStr = new Date().toISOString().slice(0, 10)

// ───────── 路径派生状态（唯一事实来源：recommendPath.steps）─────────
const pathSteps = computed(() => {
  const steps = planStore.path?.steps || []
  return [...steps].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
})
const hasPath = computed(() => pathSteps.value.length > 0)
const doneSteps = computed(() => pathSteps.value.filter(s => s.status === 'done'))
const pendingSteps = computed(() => pathSteps.value.filter(s => s.status !== 'done'))
/** 当前步骤：优先 in_progress，否则第一个未完成 */
const currentStep = computed(() =>
  pathSteps.value.find(s => s.status === 'in_progress') || pendingSteps.value[0] || null)
/** 待学习：除当前步骤外的未完成步骤 */
const upcomingSteps = computed(() =>
  currentStep.value ? pendingSteps.value.filter(s => s.id !== currentStep.value.id) : [])

const pathDoneCount = computed(() => doneSteps.value.length)

/** 今日完成度 */
const todayProgress = computed(() => {
  const items = plan.value?.daily?.items || []
  return { done: items.filter(i => i.status === 'done').length, total: items.length }
})

/** 今日计划是否过期（手动刷新，不自动调 AI） */
const isStale = computed(() => {
  const d = plan.value?.daily?.date
  return !d || d !== todayStr
})

/** 上次更新时间友好显示 */
const lastUpdatedText = computed(() => {
  const ts = plan.value?.lastUpdated
  if (!ts) return ''
  try {
    const d = new Date(ts)
    const diff = Date.now() - d.getTime()
    const h = Math.floor(diff / 3600000)
    if (h < 1) return '刚刚'
    if (h < 24) return `${h} 小时前`
    return d.toLocaleDateString('zh-CN')
  } catch { return ts }
})

/** 某步骤的全部任务（三时间桶中 pathStepId 匹配；manual/legacy 项不属任何步骤） */
function stepTasks(stepId) {
  const p = plan.value
  if (!p || !stepId) return []
  const out = []
  for (const period of ['daily', 'tomorrow', 'weekly']) {
    for (const it of (p[period]?.items || [])) {
      if (it.pathStepId === stepId) out.push({ ...it, _bucket: period })
    }
  }
  return out
}

/** 步骤序号（徽章"第N步"用） */
function stepOrderOf(stepId) {
  const s = pathSteps.value.find(x => x.id === stepId)
  return s?.order ?? '?'
}

/** 展望面板数据：待学习步骤 + 其在明日/本周桶里的任务 */
const outlook = computed(() =>
  upcomingSteps.value.map(s => ({ step: s, tasks: stepTasks(s.id) }))
    .filter(g => g.tasks.length || g.step))

onMounted(async () => {
  if (!notes.items.length) {
    try { await notes.load() } catch { /* 笔记库加载失败不阻塞计划页 */ }
  }
  await Promise.all([planStore.load(), planStore.loadPath()])
  goalInput.value = plan.value?.goal || ''
})

// ───────── 操作 ─────────

async function handleRefresh() {
  await planStore.generate(goalInput.value || '', globalFeedback.value)
  globalFeedback.value = ''
}

async function handleSaveGoal() {
  goalEditing.value = false
  await planStore.generate(goalInput.value || '', '')
}

/** 无路径引导：生成学习路径（落盘）→ 自动生成联动计划 */
async function handleGenPathAndPlan() {
  await planStore.generatePathAndPlan(goalInput.value || '')
}

function startFeedback(noteId) {
  feedbackTargetId.value = noteId
  feedbackInput.value = ''
}

async function submitFeedback(noteId, action) {
  if (action === 'feedback') {
    if (!feedbackInput.value.trim()) return
    await planStore.feedback(noteId, 'feedback', feedbackInput.value.trim())
    feedbackTargetId.value = null
    feedbackInput.value = ''
  } else {
    await planStore.feedback(noteId, action)
  }
}

/** 跳转全屏阅读页（手动任务无真实 noteId 时不跳） */
function openNote(noteId) {
  if (noteId && !String(noteId).startsWith('manual-')) {
    window.open(`#/reader/${noteId}`, '_blank')
  }
}

/** 手动添加任务：任务名精确/模糊匹配笔记库则自动关联 noteId（可跳阅读页） */
async function addManual() {
  const name = manualName.value.trim()
  if (!name) return
  let nid = ''
  const pool = (notes.items || []).map(n => ({ id: n.id, name: String(n.name).replace(/\.md$/, '') }))
  const hit = pool.find(n => n.name === name)
    || pool.find(n => n.name.includes(name) || name.includes(n.name))
  if (hit) nid = hit.id
  await planStore.addManualItem(name, nid, Number(manualHours.value) || 1)
  manualName.value = ''
  manualHours.value = 1
}

// ───────── 双向锚定 ─────────

function flashEl(id) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.remove('sp-flash')
  void el.offsetWidth // 强制 reflow，保证动画可重复触发
  el.classList.add('sp-flash')
}

const scrollToStep = (stepId) => flashEl(`steprow-${stepId}`)
const scrollToTasks = (stepId) => flashEl(`steptasks-${stepId}`)

function progressPct(cur, total) {
  return total ? Math.min(100, Math.round(cur / total * 100)) : 0
}
</script>

<template>
  <div class="sp-page">
    <AppHeader title="学习计划" />

    <main class="sp-content">

      <!-- ═══════════ 工具栏 ═══════════ -->
      <div class="sp-toolbar surface-card">
        <div class="flex items-center gap-3 flex-wrap min-w-0">
          <span v-if="plan" class="text-sm" :style="{ color: 'var(--muted)' }">
            🎯 目标：<span :style="{ color: 'var(--text)', fontWeight: 600 }">{{ plan.goal || '未设置' }}</span>
          </span>
          <button v-if="plan && !goalEditing" @click="goalEditing = true"
            class="text-xs px-2.5 py-1 rounded-md cursor-pointer transition-all hover:opacity-80"
            :style="{ border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--accent)' }">
            ✏️ 修改目标
          </button>
          <div v-if="goalEditing" class="flex items-center gap-2">
            <input v-model="goalInput" type="text" placeholder="例：成为全栈运维工程师"
              class="sp-goal-input" @keydown.enter="handleSaveGoal" />
            <button @click="handleSaveGoal"
              class="text-xs px-3 py-1.5 rounded-md cursor-pointer font-semibold"
              :style="{ background: 'var(--accent)', color: '#fff' }">保存</button>
            <button @click="goalEditing = false; goalInput = plan?.goal || ''"
              class="text-xs px-2.5 py-1.5 rounded-md cursor-pointer"
              :style="{ border: '1px solid var(--line)', color: 'var(--muted)' }">取消</button>
          </div>
          <span v-if="lastUpdatedText" class="text-xs ml-auto" :style="{ color: 'var(--muted)' }">
            上次更新：{{ lastUpdatedText }}
          </span>
        </div>

        <div class="flex items-center gap-2 mt-3 flex-wrap">
          <button @click="handleRefresh" :disabled="loading || !hasPath"
            class="sp-btn-primary inline-flex items-center gap-1.5"
            :style="(loading || !hasPath) ? { opacity: 0.6, cursor: 'not-allowed' } : {}">
            <AppIcon name="refresh" :size="14" :class="{ 'spin': loading }" />
            {{ loading ? '生成中…' : '刷新计划' }}
          </button>
          <input v-model="globalFeedback" type="text" placeholder="反馈：太难了 / 想多学点网络 / …（可选）"
            class="sp-feedback-input" />
        </div>

        <!-- 过期提示（不自动调 AI，由用户主动点刷新） -->
        <div v-if="plan && isStale" class="sp-stale-tip mt-3">
          ⚠️ 今日计划已过期（上次日期：{{ plan.daily?.date || '无' }}），点击上方"刷新计划"生成新的
        </div>
        <!-- AI 不可用 / 无路径等错误 -->
        <div v-if="errorMsg" class="sp-error-tip mt-3">⚠️ {{ errorMsg }}</div>
        <!-- 规则模式提示 -->
        <div v-if="degraded" class="sp-degraded-tip mt-3">
          ⚙️ 规则模式：AI 拆解暂不可用，笔记按步骤关键词匹配，顺序仍然正确
        </div>
      </div>

      <!-- ═══════════ 无路径引导 ═══════════ -->
      <div v-if="!hasPath && !loading" class="sp-empty surface-card">
        <div class="text-5xl mb-3">🗺️</div>
        <p class="text-lg mb-1" :style="{ color: 'var(--text)' }">学习计划需要一个学习路径作为地图</p>
        <p class="text-sm mb-1" :style="{ color: 'var(--muted)' }">
          路径决定"先学什么后学什么"（宏观顺序），计划决定"今天学哪几篇"（微观执行）。
        </p>
        <p class="text-sm mb-4" :style="{ color: 'var(--muted)' }">
          一键生成路径并创建第一份联动计划：
        </p>
        <div class="flex items-center gap-2 justify-center flex-wrap">
          <input v-model="goalInput" type="text" placeholder="学习目标（可选）：例：成为全栈运维工程师"
            class="sp-goal-input" style="width: 320px" @keydown.enter="handleGenPathAndPlan" />
          <button @click="handleGenPathAndPlan" class="sp-btn-primary">
            🚀 生成学习路径并创建计划
          </button>
        </div>
        <p v-if="plan" class="text-xs mt-3" :style="{ color: 'var(--muted)' }">
          已有一份旧版计划；生成路径后会自动切换到联动版（旧计划归档进学习轨迹）
        </p>
      </div>

      <!-- 加载中 -->
      <div v-else-if="loading && !plan" class="sp-empty surface-card">
        <div class="loading-spinner-sm mb-3"></div>
        <p class="text-sm" :style="{ color: 'var(--muted)' }">AI 正在为你规划学习计划…</p>
      </div>

      <!-- 有路径但还没生成过计划 -->
      <div v-else-if="hasPath && !plan" class="sp-empty surface-card">
        <div class="text-4xl mb-3">🧭</div>
        <p class="text-lg mb-2" :style="{ color: 'var(--text)' }">路径已就绪</p>
        <p class="text-sm mb-4" :style="{ color: 'var(--muted)' }">点击上方"刷新计划"生成第一份联动计划</p>
      </div>

      <!-- ═══════════ 方案 B 主体 ═══════════ -->
      <template v-else-if="plan">

        <!-- 主题横幅 + 路径总进度 -->
        <div class="sp-hero surface-card">
          <div class="flex items-center gap-3 flex-wrap">
            <h2 class="sp-hero-title">🎯 本月主题：{{ plan.monthly?.theme || '路径推进' }}</h2>
            <span class="sp-pathver" v-if="planStore.path?.pathVersion">{{ planStore.path.pathVersion }}</span>
            <button class="sp-hero-link" type="button"
              title="查看完整知识路径图谱：各主题依赖关系与掌握度"
              @click="goPath">🗺️ 知识路径图谱</button>
          </div>
          <div class="sp-hero-progress">
            <div class="sp-progress-track flex-1">
              <div class="sp-progress-fill" :style="{ width: progressPct(pathDoneCount, pathSteps.length) + '%' }"></div>
            </div>
            <span class="text-xs font-semibold" :style="{ color: 'var(--muted)' }">
              路径进度 {{ pathDoneCount }}/{{ pathSteps.length }} 步
            </span>
          </div>
        </div>

        <!-- 已完成折叠 -->
        <details v-if="doneSteps.length" class="sp-done-fold surface-card">
          <summary>
            ✅ 已完成 {{ doneSteps.length }}/{{ pathSteps.length }} 步
            <span :style="{ color: 'var(--muted)' }">（点击展开回顾）</span>
          </summary>
          <ul class="sp-done-list">
            <li v-for="s in doneSteps" :key="s.id" class="sp-done-item">
              <span class="sp-step-dot" style="background:#10b981"></span>
              <span class="font-medium">{{ s.order }}. {{ s.title }}</span>
            </li>
          </ul>
        </details>

        <!-- 路径全部完成 -->
        <div v-if="!currentStep" class="sp-empty surface-card">
          <div class="text-5xl mb-3">🎉</div>
          <p class="text-lg mb-2" :style="{ color: 'var(--text)' }">学习路径已全部完成！</p>
          <p class="text-sm mb-4" :style="{ color: 'var(--muted)' }">可以重新生成一条新路径继续进阶</p>
          <button @click="handleGenPathAndPlan" class="sp-btn-primary">🔄 重新生成路径并创建计划</button>
        </div>

        <!-- 当前步骤大卡片（今日任务内嵌其中） -->
        <section v-if="currentStep" class="surface-card sp-current-card" :id="`stepcard-${currentStep.id}`">
          <header class="sp-current-head">
            <div class="flex items-center gap-2 flex-wrap min-w-0">
              <span class="sp-current-order">第 {{ currentStep.order }} 步</span>
              <h2 class="sp-current-title">{{ currentStep.title }}</h2>
              <span class="sp-target-badge">🎯 当前指向</span>
            </div>
            <span class="sp-progress-badge">{{ todayProgress.done }}/{{ todayProgress.total }} 完成</span>
          </header>
          <p v-if="currentStep.reason" class="sp-current-reason">{{ currentStep.reason }}</p>

          <!-- 今日任务（内嵌在步骤卡片中：联动从文字标注变成物理嵌套） -->
          <div class="sp-tasks-label">今日任务（{{ plan.daily?.date || todayStr }}）</div>
          <div v-if="!(plan.daily?.items || []).length" class="sp-card-empty">今日无安排</div>
          <ul v-else class="sp-item-list">
            <li v-for="it in plan.daily.items" :key="it.noteId" class="sp-item">
              <div class="sp-item-main" @click="openNote(it.noteId)">
                <span class="sp-item-status">{{ it.status === 'done' ? '✅' : it.status === 'skipped' ? '⏭️' : '⬜' }}</span>
                <div class="min-w-0 flex-1">
                  <div class="sp-item-name" :class="{ 'line-through opacity-60': it.status === 'done' }">{{ it.noteName }}</div>
                  <div class="sp-item-reason">{{ it.reason }}</div>
                  <div class="flex items-center gap-1.5 flex-wrap mt-1">
                    <button v-if="it.pathStepId" class="sp-step-badge" @click.stop="scrollToStep(it.pathStepId)"
                      :title="'点击定位路径第 ' + stepOrderOf(it.pathStepId) + ' 步'">
                      ↳ 路径第 {{ stepOrderOf(it.pathStepId) }} 步
                    </button>
                    <span v-if="it.source === 'manual'" class="sp-manual-badge">✋ 手动</span>
                    <span v-if="it.feedback" class="sp-item-feedback">💬 {{ it.feedback }}</span>
                  </div>
                </div>
                <span class="sp-item-hours">{{ it.estimatedHours }}h</span>
              </div>
              <div class="sp-item-actions">
                <button v-if="it.status !== 'done'" @click.stop="submitFeedback(it.noteId, 'done')"
                  class="sp-action-btn sp-action-done">完成</button>
                <button v-if="it.status === 'done'" @click.stop="submitFeedback(it.noteId, 'undo')"
                  class="sp-action-btn">撤销</button>
                <button v-if="it.status === 'pending'" @click.stop="submitFeedback(it.noteId, 'skip')"
                  class="sp-action-btn">跳过</button>
                <button v-if="it.status === 'skipped'" @click.stop="submitFeedback(it.noteId, 'undo')"
                  class="sp-action-btn">恢复</button>
                <button @click.stop="startFeedback(it.noteId)" class="sp-action-btn">反馈</button>
                <div v-if="feedbackTargetId === it.noteId" class="sp-feedback-row">
                  <input v-model="feedbackInput" type="text" placeholder="太难了 / 太简单 / …"
                    @keydown.enter="submitFeedback(it.noteId, 'feedback')"
                    class="sp-feedback-inline" />
                  <button @click="submitFeedback(it.noteId, 'feedback')"
                    class="sp-action-btn sp-action-done">提交</button>
                  <button @click="feedbackTargetId = null" class="sp-action-btn">取消</button>
                </div>
              </div>
            </li>
          </ul>

          <!-- 手动添加任务 -->
          <div class="sp-manual-add">
            <input v-model="manualName" type="text" placeholder="手动添加任务（任务名或笔记名）"
              class="sp-feedback-inline" style="flex:1" @keydown.enter="addManual" />
            <input v-model="manualHours" type="number" min="0.5" step="0.5" class="sp-feedback-inline"
              style="width: 72px" title="预计时长（小时）" />
            <button @click="addManual" class="sp-action-btn sp-action-done">＋ 添加</button>
          </div>
          <p class="text-xs mt-1.5" :style="{ color: 'var(--muted)' }">
            手动任务带"手动"徽章，完成后不推进路径进度
          </p>
        </section>

        <!-- 待学习（灰阶弱化，点击定位其任务） -->
        <section v-if="upcomingSteps.length" class="surface-card sp-upcoming-card">
          <header class="sp-card-head">
            <h2 class="sp-card-title">○ 待学习（{{ upcomingSteps.length }} 步）</h2>
          </header>
          <ul class="sp-upcoming-list">
            <li v-for="s in upcomingSteps" :key="s.id" class="sp-upcoming-item"
              :id="`steprow-${s.id}`" @click="scrollToTasks(s.id)"
              :title="'点击定位「' + s.title + '」的任务安排'">
              <span class="sp-step-dot" style="background:var(--muted)"></span>
              <span class="sp-upcoming-order">{{ s.order }}</span>
              <span class="sp-upcoming-name">{{ s.title }}</span>
              <span v-if="s.estimatedHours" class="sp-item-hours">{{ s.estimatedHours }}h</span>
            </li>
          </ul>
        </section>

        <!-- 展望：明日 / 本周（按步骤分组，双向锚定目标） -->
        <section v-if="outlook.some(g => g.tasks.length)" class="surface-card">
          <header class="sp-card-head">
            <h2 class="sp-card-title">🧭 展望：明日 {{ plan.tomorrow?.date || '' }} · 本周（{{ plan.weekly?.weekStart || '' }} 起）</h2>
          </header>
          <div v-for="g in outlook" :key="g.step.id" class="sp-outlook-group" :id="`steptasks-${g.step.id}`">
            <div class="sp-outlook-step" @click="scrollToStep(g.step.id)"
              :title="'点击定位路径第 ' + g.step.order + ' 步'">
              <span class="sp-step-dot" style="background:var(--muted)"></span>
              第 {{ g.step.order }} 步：{{ g.step.title }}
            </div>
            <ul v-if="g.tasks.length" class="sp-item-list sp-outlook-tasks">
              <li v-for="it in g.tasks" :key="it._bucket + it.noteId" class="sp-item sp-item-weak">
                <div class="sp-item-main" @click="openNote(it.noteId)">
                  <span class="sp-bucket-tag" :class="it._bucket">{{ it._bucket === 'tomorrow' ? '明日' : '本周' }}</span>
                  <div class="min-w-0 flex-1">
                    <div class="sp-item-name" :class="{ 'line-through opacity-60': it.status === 'done' }">{{ it.noteName }}</div>
                    <div class="sp-item-reason">{{ it.reason }}</div>
                  </div>
                  <span class="sp-item-hours">{{ it.estimatedHours }}h</span>
                </div>
              </li>
            </ul>
            <div v-else class="sp-card-empty">暂无任务安排</div>
          </div>
        </section>

        <!-- 本月分类进度 -->
        <section v-if="plan.monthly?.items?.length" class="surface-card sp-card">
          <header class="sp-card-head">
            <h2 class="sp-card-title">📌 本月（{{ plan.monthly.monthStart }}）</h2>
            <span class="sp-theme-badge">{{ plan.monthly.theme }}</span>
          </header>
          <ul class="sp-month-list">
            <li v-for="(it, i) in plan.monthly.items" :key="i" class="sp-month-item">
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-sm font-semibold" :style="{ color: 'var(--text)' }">{{ it.category }}</span>
                <span class="text-xs" :style="{ color: 'var(--muted)' }">{{ it.currentCount ?? 0 }}/{{ it.targetCount }} 篇</span>
              </div>
              <div class="sp-progress-track">
                <div class="sp-progress-fill" :style="{ width: progressPct(it.currentCount ?? 0, it.targetCount) + '%' }"></div>
              </div>
              <div v-if="it.reason" class="text-xs mt-1" :style="{ color: 'var(--muted)' }">{{ it.reason }}</div>
            </li>
          </ul>
        </section>

        <!-- 学习轨迹（history） -->
        <section v-if="plan.history && plan.history.length" class="surface-card sp-card">
          <header class="sp-card-head">
            <h2 class="sp-card-title">📚 学习轨迹</h2>
            <span class="sp-progress-badge">{{ plan.history.length }} 天</span>
          </header>
          <ul class="sp-history-list">
            <li v-for="(h, i) in plan.history.slice(-15).reverse()" :key="i" class="sp-history-item">
              <span class="sp-history-date">{{ h.date }}</span>
              <span class="sp-history-stat" :style="{ color: h.completed === h.planned && h.planned > 0 ? 'var(--accent)' : 'var(--muted)' }">
                {{ h.completed }}/{{ h.planned }}
              </span>
            </li>
          </ul>
        </section>

        <!-- 联动说明脚注 -->
        <p class="sp-foot-note">
          联动模式：路径（{{ planStore.path?.steps?.length || 0 }} 步）是唯一事实来源，今日任务取自"下一个未完成步骤"，
          完成后自动回流路径进度。
        </p>
      </template>
    </main>
  </div>
</template>

<style scoped>
.sp-page { min-height: 100vh; background: var(--bg); color: var(--text); }
.sp-content { max-width: 1100px; margin: 0 auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.sp-toolbar { padding: 16px 20px; }
.sp-goal-input {
  width: 280px; padding: 6px 12px; border: 1px solid var(--line);
  border-radius: var(--radius-sm, 6px); background: var(--bg); color: var(--text);
  font-size: 13px; outline: none;
}
.sp-goal-input:focus { border-color: var(--accent); }
.sp-btn-primary {
  padding: 8px 16px; border-radius: 8px; border: none; cursor: pointer;
  background: var(--accent); color: #fff; font-size: 13px; font-weight: 600;
  transition: opacity .15s;
}
.sp-btn-primary:hover { opacity: .88; }
.sp-feedback-input, .sp-feedback-inline {
  flex: 1; min-width: 160px; padding: 7px 12px; border: 1px solid var(--line);
  border-radius: var(--radius-sm, 6px); background: var(--bg); color: var(--text);
  font-size: 13px; outline: none;
}
.sp-feedback-input:focus, .sp-feedback-inline:focus { border-color: var(--accent); }

.sp-stale-tip, .sp-error-tip, .sp-degraded-tip {
  padding: 9px 14px; border-radius: 8px; font-size: 13px;
}
.sp-stale-tip { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
.sp-error-tip { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
.sp-degraded-tip { background: #f0f9ff; border: 1px solid #bae6fd; color: #075985; }

.sp-empty {
  padding: 40px 24px; text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
}

/* ── 主题横幅 ── */
.sp-hero { padding: 18px 22px; }
.sp-hero-title { font-size: 17px; font-weight: 700; }
.sp-hero-link {
  margin-left: auto;
  padding: 5px 14px;
  border: 1px solid var(--accent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.sp-hero-link:hover { background: var(--accent); color: #fff; }
.sp-pathver {
  font-size: 11px; color: var(--muted); border: 1px dashed var(--line);
  padding: 2px 8px; border-radius: 999px;
}
.sp-hero-progress { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.sp-progress-track {
  height: 9px; border-radius: 999px; background: var(--line); overflow: hidden; flex: 1; min-width: 120px;
}
.sp-progress-fill {
  height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), #60a5fa);
  transition: width .4s ease;
}

/* ── 已完成折叠 ── */
.sp-done-fold { padding: 12px 20px; }
.sp-done-fold summary { cursor: pointer; font-size: 14px; font-weight: 600; }
.sp-done-list { list-style: none; padding: 10px 0 2px; margin: 0; }
.sp-done-item {
  display: flex; align-items: center; gap: 10px; padding: 7px 4px;
  font-size: 13px; color: var(--muted);
}

/* ── 当前步骤大卡片 ── */
.sp-current-card { padding: 18px 22px; border-left: 4px solid var(--accent); }
.sp-current-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
}
.sp-current-order {
  font-size: 12px; font-weight: 700; color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border: 1px solid var(--accent); padding: 2px 10px; border-radius: 999px;
}
.sp-current-title { font-size: 18px; font-weight: 700; }
.sp-target-badge { font-size: 12px; color: var(--accent); font-weight: 600; }
.sp-current-reason { font-size: 13px; color: var(--muted); margin-top: 6px; }
.sp-tasks-label {
  font-size: 13px; font-weight: 700; color: var(--muted);
  margin: 16px 0 10px; display: flex; align-items: center; gap: 8px;
}
.sp-tasks-label::after { content: ""; flex: 1; height: 1px; background: var(--line); }

/* ── 任务列表（今日内嵌 + 展望复用）── */
.sp-item-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.sp-item {
  border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px;
  background: var(--bg); transition: border-color .15s;
}
.sp-item:hover { border-color: var(--accent); }
.sp-item-weak { opacity: .85; }
.sp-item-main { display: flex; align-items: flex-start; gap: 10px; cursor: pointer; }
.sp-item-status { font-size: 15px; line-height: 1.4; }
.sp-item-name { font-weight: 600; font-size: 14px; }
.sp-item-reason { font-size: 12px; color: var(--muted); margin-top: 2px; }
.sp-item-feedback { font-size: 12px; color: var(--accent); }
.sp-item-hours { font-size: 12px; color: var(--muted); white-space: nowrap; }
.sp-item-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.sp-action-btn {
  padding: 4px 12px; border-radius: 7px; font-size: 12px; font-weight: 600; cursor: pointer;
  border: 1px solid var(--line); background: var(--card); color: var(--text);
  transition: all .15s;
}
.sp-action-btn:hover { border-color: var(--accent); color: var(--accent); }
.sp-action-done { background: var(--accent); color: #fff; border-color: var(--accent); }
.sp-action-done:hover { color: #fff; opacity: .88; }
.sp-feedback-row { display: flex; align-items: center; gap: 6px; width: 100%; margin-top: 6px; }

.sp-step-badge {
  font-size: 11px; color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent);
  border: 1px solid var(--accent); padding: 1px 8px; border-radius: 999px;
  cursor: pointer; transition: all .15s;
}
.sp-step-badge:hover { background: var(--accent); color: #fff; }
.sp-manual-badge {
  font-size: 11px; color: var(--muted); border: 1px dashed var(--muted);
  padding: 1px 8px; border-radius: 999px;
}

/* ── 手动添加 ── */
.sp-manual-add { display: flex; align-items: center; gap: 8px; margin-top: 14px; }

/* ── 待学习 ── */
.sp-upcoming-card { padding: 14px 20px; }
.sp-upcoming-list { list-style: none; padding: 0; margin: 0; }
.sp-upcoming-item {
  display: flex; align-items: center; gap: 10px; padding: 8px 6px;
  font-size: 13px; color: var(--muted); cursor: pointer;
  border-radius: 8px; transition: background .15s;
}
.sp-upcoming-item:hover { background: var(--bg); }
.sp-upcoming-order { font-size: 12px; font-weight: 700; width: 18px; text-align: center; }
.sp-upcoming-name { flex: 1; min-width: 0; }
.sp-step-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

/* ── 展望 ── */
.sp-outlook-group { padding: 10px 0; border-top: 1px dashed var(--line); }
.sp-outlook-group:first-of-type { border-top: none; }
.sp-outlook-step {
  display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600;
  color: var(--muted); cursor: pointer; padding: 2px 4px;
}
.sp-outlook-step:hover { color: var(--accent); }
.sp-outlook-tasks { margin-top: 8px; padding-left: 18px; }
.sp-bucket-tag {
  font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px;
  white-space: nowrap; flex-shrink: 0;
}
.sp-bucket-tag.tomorrow { color: #b45309; background: #fef3c7; }
.sp-bucket-tag.weekly { color: #1d4ed8; background: #dbeafe; }

/* ── 通用卡片 ── */
.sp-card { padding: 16px 20px; }
.sp-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.sp-card-title { font-size: 14px; font-weight: 700; }
.sp-card-empty { font-size: 13px; color: var(--muted); padding: 8px 2px; }
.sp-progress-badge {
  font-size: 12px; color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent);
  padding: 2px 10px; border-radius: 999px; font-weight: 600;
}
.sp-theme-badge {
  font-size: 12px; color: var(--muted); border: 1px dashed var(--line);
  padding: 2px 10px; border-radius: 999px;
}
.sp-month-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.sp-month-item { padding: 2px 0; }

/* ── 学习轨迹 ── */
.sp-history-list { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.sp-history-item {
  display: flex; align-items: center; gap: 8px; font-size: 12px;
  border: 1px solid var(--line); border-radius: 8px; padding: 4px 10px;
}
.sp-history-date { color: var(--muted); }
.sp-history-stat { font-weight: 700; }

.sp-foot-note { font-size: 12px; color: var(--muted); text-align: center; padding: 4px 0 12px; }

/* ── 双向锚定闪烁 ── */
.sp-flash { animation: spFlash 1.4s ease; }
@keyframes spFlash {
  0%, 55% { outline: 2px solid var(--accent); outline-offset: 3px; }
  100% { outline: 2px solid transparent; outline-offset: 3px; }
}
</style>

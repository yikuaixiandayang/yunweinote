<script setup>
/**
 * 学习路径页面 — 容器组件（重构版）
 *
 * 两种视图切换：
 *   - 路径（默认）：垂直时间线，按拓扑排序展示学习步骤
 *   - 图谱：DAG 依赖关系图谱（d3-force）
 *
 * 顶栏：返回 + 标题 + 视图切换 + 搜索 + 掌握度进度条
 * 顶栏下方：分类 chip 条 + 筛选下拉
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import { useLearningPath } from '../composables/useLearningPath'
import { useStudyPlanStore } from '../stores/studyPlan'
import PathTimeline from '../components/learning-path/PathTimeline.vue'
import DependencyGraph from '../components/learning-path/DependencyGraph.vue'

const router = useRouter()
const route = useRoute()
const studyPlan = useStudyPlanStore()
const {
  searchQuery, selectedCat, showOrphans, showUnreadOnly, pathOnly,
  categories, mastery, graphData, exportLearningOrder, focusId,
} = useLearningPath()

// 加载 recommendPath（软锚定定序的数据源）。
// 即使用户没开过 /study-plan，也要拿到后端落盘的路径来给拓扑排序破平局。
// loadPath 内部吞异常（失败时 path=null → pathOrderMap 为空 → 退回纯拓扑序，无回归）。
// P3.2：若带 ?focus=<noteId> 来，设置共享 focusId，让时间线滚动定位 + 图谱高亮上下游。
onMounted(() => {
  studyPlan.loadPath()
  const f = route.query.focus
  if (f && typeof f === 'string') focusId.value = f
})

const viewMode = ref('path') // 'path' | 'graph'
const filterOpen = ref(false)
const graphRef = ref(null)

const masteryTitle = computed(() =>
  `已读 ${mastery.value.read} / ${mastery.value.total} 节点`
)

function openNote(id) {
  router.push('/')
  sessionStorage.setItem('graph_open_note', id)
}

/** 跳转学习计划页（地图 → 执行） */
function goPlan() {
  router.push('/study-plan')
}

function onSearchEnter() {
  if (viewMode.value === 'graph' && graphRef.value) {
    graphRef.value.searchSubmit()
  }
}
</script>

<template>
  <div class="lp-page">
    <!-- 顶栏 -->
    <header class="lp-topbar">
      <h1 class="lp-title" role="button" tabindex="0" title="返回首页" @click="router.push('/')" @keydown.enter.prevent="router.push('/')"><AppIcon name="route" :size="17" style="vertical-align: -3px" /> 学习路径</h1>

      <!-- 视图切换 -->
      <div class="view-toggle" role="tablist">
        <button
          :class="['tab', { active: viewMode === 'path' }]"
          role="tab"
          :aria-selected="viewMode === 'path'"
          @click="viewMode = 'path'"
        >路径</button>
        <button
          :class="['tab', { active: viewMode === 'graph' }]"
          role="tab"
          :aria-selected="viewMode === 'graph'"
          @click="viewMode = 'graph'"
        >图谱</button>
      </div>

      <!-- 搜索 -->
      <input
        v-model="searchQuery"
        class="search-input"
        type="text"
        placeholder="搜索步骤…"
        @keydown.enter="onSearchEnter"
        aria-label="搜索学习步骤"
      />

      <!-- 跳转学习计划（地图 → 执行） -->
      <button
        class="lp-plan-btn"
        type="button"
        title="进入 AI 学习计划：今日该学哪几篇"
        @click="goPlan"
      >📅 我的计划</button>

      <!-- 掌握度进度条 -->
      <div class="mastery-bar" :title="masteryTitle">
        <div class="mastery-label">{{ mastery.pct }}%</div>
        <div class="mastery-track">
          <div class="mastery-fill" :style="{ width: mastery.pct + '%' }"></div>
        </div>
      </div>
    </header>

    <!-- 分类 chip 条 + 筛选 -->
    <div class="lp-subbar">
      <div class="cat-chips">
        <button
          :class="['chip', { active: !selectedCat }]"
          @click="selectedCat = ''"
        >全部</button>
        <button
          v-for="c in categories"
          :key="c.name"
          :class="['chip', { active: selectedCat === c.name }]"
          @click="selectedCat = selectedCat === c.name ? '' : c.name"
        >
          <span class="chip-dot" :style="{ background: c.color }"></span>
          {{ c.icon }} {{ c.name }}
          <span class="chip-count">{{ c.count }}</span>
        </button>
      </div>

      <!-- 筛选下拉 -->
      <div class="filter-dropdown">
        <button
          class="filter-btn"
          :aria-expanded="filterOpen"
          @click="filterOpen = !filterOpen"
        >
          筛选
          <span v-if="showUnreadOnly || showOrphans" class="filter-badge"></span>
        </button>
        <div v-if="filterOpen" class="filter-menu" @click.stop>
          <label class="filter-item">
            <input type="checkbox" v-model="showUnreadOnly" />
            <span>仅未读</span>
          </label>
          <label class="filter-item">
            <input type="checkbox" v-model="showOrphans" />
            <span>显示孤立节点</span>
          </label>
          <label class="filter-item" title="仅展示 recommendPath 内的学习步骤，隐藏全库其余笔记">
            <input type="checkbox" v-model="pathOnly" />
            <span>仅看路径（10步）</span>
          </label>
          <button class="filter-action" @click="exportLearningOrder">
            导出学习顺序
          </button>
        </div>
      </div>
    </div>

    <!-- 视图内容 -->
    <main class="lp-content">
      <PathTimeline
        v-show="viewMode === 'path'"
        class="lp-view"
        @open-note="openNote"
      />
      <DependencyGraph
        v-show="viewMode === 'graph'"
        :visible="viewMode === 'graph'"
        class="lp-view"
        ref="graphRef"
        @open-note="openNote"
      />
    </main>
  </div>
</template>

<style scoped>
.lp-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

/* ───────── 顶栏 ───────── */
.lp-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  height: 56px;
  min-height: 56px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
}

.lp-title {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
  white-space: nowrap;
  color: var(--text);
  cursor: pointer;
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  transition: background 0.15s, color 0.15s;
}
.lp-title:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--accent);
}
.lp-title:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* 视图切换 */
.view-toggle {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: var(--hover);
  border-radius: var(--radius-sm);
}
.tab {
  padding: 5px 14px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  border-radius: 4px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.tab.active {
  background: var(--card);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

/* 搜索 */
.search-input {
  width: 200px;
  padding: 7px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 12%, transparent);
}
.search-input::placeholder { color: var(--muted); }

/* 掌握度 */
.mastery-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.mastery-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  min-width: 36px;
  text-align: right;
}
.mastery-track {
  width: 80px;
  height: 6px;
  border-radius: 3px;
  background: var(--hover);
  overflow: hidden;
}
.mastery-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 70%, #22d3ee));
  transition: width 0.4s cubic-bezier(.4, 0, .2, 1);
}

/* 跳转学习计划按钮（地图 → 执行） */
.lp-plan-btn {
  flex-shrink: 0;
  margin-left: 12px;
  padding: 6px 14px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm, 6px);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.lp-plan-btn:hover {
  background: var(--accent);
  color: #fff;
}

/* ───────── 子栏（分类 + 筛选） ───────── */
.lp-subbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 20px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
  min-height: 44px;
}

.cat-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
  flex: 1;
}
.cat-chips::-webkit-scrollbar { display: none; }

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.chip:hover {
  border-color: var(--muted);
  color: var(--text);
}
.chip.active {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.chip-count {
  opacity: 0.6;
  font-size: 11px;
}

/* 筛选下拉 */
.filter-dropdown { position: relative; }
.filter-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.filter-btn:hover {
  border-color: var(--muted);
  color: var(--text);
}
.filter-badge {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}
.filter-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 180px;
  padding: 8px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  transition: background 0.15s;
}
.filter-item:hover { background: var(--hover); }
.filter-item input { accent-color: var(--accent); }
.filter-action {
  margin-top: 4px;
  padding: 6px 8px;
  border: none;
  border-top: 1px solid var(--line);
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition: opacity 0.15s;
}
.filter-action:hover { opacity: 0.7; }

/* ───────── 内容区 ───────── */
.lp-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}
.lp-view {
  position: absolute;
  inset: 0;
}

/* ───────── 响应式 ───────── */
@media (max-width: 640px) {
  .lp-topbar { padding: 0 12px; gap: 8px; }
  .search-input { width: 120px; }
  .mastery-track { width: 50px; }
  .lp-subbar { padding: 8px 12px; }
}
</style>

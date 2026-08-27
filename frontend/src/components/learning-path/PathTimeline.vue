<script setup>
/**
 * 学习路径时间线视图
 *
 * 按拓扑排序垂直展示学习步骤，每步为一张可展开的卡片。
 * 已读步骤默认折叠，未读步骤默认展开。
 */
import { ref, computed, watch, nextTick } from 'vue'
import { useLearningPath } from '../../composables/useLearningPath'
import PathCard from './PathCard.vue'

const {
  topoOrder, filteredData, searchQuery, focusId,
  isRead, isFav,
} = useLearningPath()

const emit = defineEmits(['open-note'])

// 展开状态：记录哪些步骤 ID 是展开的
const expandedSet = ref(new Set())

// 默认：未读步骤展开，已读步骤折叠
watch(topoOrder, (order) => {
  const next = new Set()
  for (const item of order.items) {
    if (!isRead(item)) next.add(item.id)
  }
  expandedSet.value = next
}, { immediate: true })

function isExpanded(id) { return expandedSet.value.has(id) }

function toggle(id) {
  const next = new Set(expandedSet.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedSet.value = next
}

// 缓存每个节点的依赖关系（避免 focusId 切换影响所有卡片）
const nodeDeps = computed(() => {
  const map = {}
  const data = filteredData.value
  // 正向邻接表
  const fwd = {}
  const rev = {}
  for (const l of data.links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (!fwd[s]) fwd[s] = []
    fwd[s].push(t)
    if (!rev[t]) rev[t] = []
    rev[t].push(s)
  }
  const nodeMap = {}
  for (const n of data.nodes) nodeMap[n.id] = n
  for (const item of topoOrder.value.items) {
    const preIds = rev[item.id] || []
    const sucIds = fwd[item.id] || []
    map[item.id] = {
      predecessors: preIds.map(id => nodeMap[id]).filter(Boolean).map(n => ({
        id: n.id, name: n.name, color: n.color,
      })),
      successors: sucIds.map(id => nodeMap[id]).filter(Boolean).map(n => ({
        id: n.id, name: n.name, color: n.color,
      })),
    }
  }
  return map
})

function getPre(id) { return nodeDeps.value[id]?.predecessors || [] }
function getSuc(id) { return nodeDeps.value[id]?.successors || [] }

// 跳转到目标步骤：展开目标卡片并滚动
function jumpTo(id) {
  if (!expandedSet.value.has(id)) toggle(id)
  nextTick(() => {
    const el = document.querySelector(`[data-step-id="${id}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

function openNote(id) { emit('open-note', id) }

// P3.2 聚焦锚定：focusId 变化时（如从 /study-plan 带 ?focus= 跳来），
// 自动展开目标步骤卡片并滚动定位。
// 同时 watch topoOrder：处理跳转时 topoOrder 尚未就绪的时序（等数据到了再跳）。
watch(focusId, (id) => {
  if (!id) return
  const exists = topoOrder.value.items.some(it => it.id === id)
  if (exists) nextTick(() => jumpTo(id))
}, { immediate: false })

watch(topoOrder, (order) => {
  const fid = focusId.value
  if (!fid) return
  const exists = order.items.some(it => it.id === fid)
  if (exists) nextTick(() => jumpTo(fid))
}, { immediate: true })

// 筛选后的步骤列表
const items = computed(() => topoOrder.value.items)

const isEmpty = computed(() => items.value.length === 0)
</script>

<template>
  <div class="path-timeline">
    <!-- 空状态 -->
    <div v-if="isEmpty" class="empty-state">
      <div class="empty-icon">🗺️</div>
      <div class="empty-text" v-if="searchQuery">未找到匹配「{{ searchQuery }}」的学习步骤</div>
      <div class="empty-text" v-else>暂无学习路径数据</div>
    </div>

    <!-- 时间线 -->
    <div v-else class="timeline-track">
      <div class="timeline-line"></div>
      <div
        v-for="item in items"
        :key="item.id"
        class="timeline-step"
        :data-step-id="item.id"
      >
        <div class="timeline-dot" :style="{ background: item.color }"></div>
        <PathCard
          :item="item"
          :is-read="isRead(item)"
          :is-fav="isFav(item)"
          :predecessors="getPre(item.id)"
          :successors="getSuc(item.id)"
          :expanded="isExpanded(item.id)"
          :search-query="searchQuery"
          @toggle="toggle(item.id)"
          @open-note="openNote"
          @jump-to="jumpTo"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.path-timeline {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 24px 0 48px;
  scrollbar-width: thin;
}
.path-timeline::-webkit-scrollbar { width: 7px; }
.path-timeline::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--muted) 30%, transparent);
  border-radius: 4px;
}

.timeline-track {
  position: relative;
  max-width: 760px;
  margin: 0 auto;
  padding: 0 24px;
}

/* 垂直时间线 */
.timeline-line {
  position: absolute;
  left: 36px;
  top: 12px;
  bottom: 12px;
  width: 2px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--accent) 40%, transparent) 0%,
    var(--line) 20%,
    var(--line) 80%,
    color-mix(in srgb, var(--accent) 20%, transparent) 100%
  );
  border-radius: 1px;
}

.timeline-step {
  position: relative;
  padding-left: 28px;
  margin-bottom: 8px;
}

/* 时间线圆点 */
.timeline-dot {
  position: absolute;
  left: 31px;
  top: 20px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--bg);
  box-shadow: 0 0 0 1px var(--line), 0 0 8px color-mix(in srgb, currentColor 40%, transparent);
  z-index: 1;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--muted);
}
.empty-icon { font-size: 48px; opacity: 0.5; }
.empty-text { font-size: 14px; }

/* 响应式 */
@media (max-width: 640px) {
  .timeline-track { padding: 0 12px; }
  .timeline-line { left: 24px; }
  .timeline-step { padding-left: 24px; }
  .timeline-dot { left: 19px; }
}
</style>

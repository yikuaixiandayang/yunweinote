<script setup>
import AppIcon from './AppIcon.vue'
import { computed, ref, watch } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { CAT_COLORS, noteMatchesCat } from '../constants'
import { getInsights } from '../api'

const notes = useNotesStore()
const userData = useUserDataStore()

const suggestData = ref(null)
const loading = ref(false)

watch(() => notes.raw, async () => {
  if (notes.items.length) {
    loading.value = true
    try {
      suggestData.value = await getInsights()
    } catch { /* ignore */ }
    loading.value = false
  }
}, { immediate: false })

function scrollToNote(id) {
  // 始终交给 IndexPage：它会在筛选状态下给出明确提示，避免有时能跳转、有时无响应。
  const note = notes.items.find(n => n.id === id)
  if (note) {
    window.dispatchEvent(new CustomEvent('note-navigation-request', { detail: { id, cat: note.cat } }))
  }
}

const grouped = computed(() => {
  // 分类+标签联动：分布条计数与分类筛选一致，含跨分类标签关联的笔记
  const m = {}
  notes.catOrder.forEach(c => { m[c] = [] })
  notes.items.forEach(n => {
    notes.catOrder.forEach(c => {
      if (noteMatchesCat(n, c)) m[c].push(n)
    })
  })
  return notes.catOrder.filter(c => m[c] && m[c].length).map(c => ({ name: c, items: m[c] }))
})

const maxCount = computed(() => {
  return Math.max(...grouped.value.map(g => g.items.length), 1)
})

const topHot = computed(() => {
  return [...notes.items]
    .sort((a, b) => (userData.openCounts[b.id] || 0) - (userData.openCounts[a.id] || 0))
    .slice(0, 10)
})

const maxHot = computed(() => Math.max(...topHot.value.map(n => userData.openCounts[n.id] || 0), 1))

/** 总打开次数：为 0 时说明新用户尚未使用，TOP10 无意义 */
const totalOpens = computed(() =>
  Object.values(userData.openCounts || {}).reduce((s, c) => s + c, 0)
)

const tagFreq = computed(() => {
  const f = {}
  notes.items.forEach(n => (n.tags || []).forEach(t => {
    f[t] = (f[t] || 0) + 1
  }))
  return Object.entries(f).sort((a, b) => b[1] - a[1]).slice(0, 30)
})

const maxTagFreq = computed(() => Math.max(...tagFreq.value.map(([_, c]) => c), 1))

const TAG_COLORS = Object.values(CAT_COLORS)

function emitTagFilter(tag) {
  window.dispatchEvent(new CustomEvent('tag-filter', { detail: tag }))
}

/** 看板分类分布条点击 → 派发 cat-filter 事件，IndexPage 监听后筛选该分类 */
function emitCatFilter(cat) {
  window.dispatchEvent(new CustomEvent('cat-filter', { detail: cat }))
}
</script>

<template>
  <div class="px-1.5">
    <div class="text-xs font-bold uppercase tracking-wider mb-1.5" :style="{ color: 'var(--muted)' }">分类分布</div>
    <div class="flex flex-col gap-1 py-0.5">
      <div
        v-for="g in grouped" :key="g.name"
        @click="emitCatFilter(g.name)"
        class="flex items-center gap-1.5 text-xs cursor-pointer rounded-lg px-1 py-0.5 transition-all hover:bg-[var(--hover)] hover:translate-x-0.5"
      >
        <span class="w-20 flex-none truncate" :style="{ color: 'var(--muted)' }">{{ g.name }}</span>
        <div class="flex-1 h-3.5 rounded overflow-hidden" :style="{ background: 'var(--hover)' }">
          <div
            class="h-full rounded transition-all duration-400"
            :style="{ width: (g.items.length / maxCount * 100) + '%', background: CAT_COLORS[g.name] || '#2563eb' }"
          ></div>
        </div>
        <span class="w-6 text-right font-semibold" :style="{ color: 'var(--text)' }">{{ g.items.length }}</span>
      </div>
    </div>

    <div class="text-xs font-bold uppercase tracking-wider mb-1.5 mt-3">🔥 热门笔记 TOP10</div>
    <div v-if="totalOpens > 0" class="flex flex-col gap-1.5 py-0.5">
      <div
        v-for="(n, i) in topHot" :key="n.id"
        @click="scrollToNote(n.id)"
        class="flex items-center gap-1.5 text-xs cursor-pointer rounded-lg px-1 py-0.5 transition-all hover:bg-[var(--hover)] hover:translate-x-0.5"
      >
        <span class="w-4 text-center font-bold flex-none" :style="{ color: i === 0 ? '#f59e0b' : i < 3 ? '#94a3b8' : 'var(--muted)' }">{{ i + 1 }}</span>
        <span class="w-[120px] truncate flex-none" :title="n.name" :style="{ color: 'var(--text)' }">{{ n.name.replace(/\.md$/, '').slice(0, 16) }}</span>
        <div class="flex-1 h-4 rounded overflow-hidden" :style="{ background: 'var(--hover)' }">
          <div
            class="h-full rounded transition-all duration-400"
            :style="{ width: ((userData.openCounts[n.id] || 0) / maxHot * 100) + '%', background: 'linear-gradient(90deg, #f59e0b, #fbbf24)' }"
          ></div>
        </div>
        <span class="w-7 text-right font-semibold text-xs" :style="{ color: '#f59e0b' }">{{ userData.openCounts[n.id] || 0 }}</span>
      </div>
    </div>
    <div v-else class="text-xs py-2 text-center" :style="{ color: 'var(--muted)' }">
      暂无热度数据，打开笔记后自动生成
    </div>

    <div class="text-xs font-bold uppercase tracking-wider mb-2 mt-3">🏷️ 标签云</div>
    <div class="flex flex-wrap gap-1.5 py-1">
      <span
        v-for="([t, c], i) in tagFreq" :key="t"
        @click="emitTagFilter(t)"
        class="tag-cloud-item inline-block cursor-pointer rounded-full transition-all duration-200 hover:scale-110 hover:shadow-sm"
        :style="{
          fontSize: (11 + Math.round((c / maxTagFreq) * 6)) + 'px',
          color: TAG_COLORS[i % TAG_COLORS.length],
          background: TAG_COLORS[i % TAG_COLORS.length] + '15',
          border: '1px solid ' + TAG_COLORS[i % TAG_COLORS.length] + '40',
          padding: '2px 10px',
          fontWeight: 500,
        }"
      >{{ t }}<span style="opacity: 0.55; font-weight: 400; margin-left: 3px">{{ c }}</span></span>
    </div>
  </div>
</template>

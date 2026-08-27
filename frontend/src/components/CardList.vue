<script setup>
import AppIcon from './AppIcon.vue'
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { CAT_COLORS, noteMatchesCat } from '../constants'
import { highlightHtml } from '../utils/safeHtml.js'

const props = defineProps({
  sort: { type: String, default: 'default' },
  cat: { type: String, default: null },
  tags: { type: Set, default: () => new Set() },
  favOnly: Boolean,
  q: String,
})

const emit = defineEmits(['card-click', 'tag-click'])
const notes = useNotesStore()
const userData = useUserDataStore()

/** 每个分类首屏显示条数 */
const PAGE_SIZE = 12
/** 每个分类当前已加载的页数，key=分类名 */
const pagesLoaded = ref({})

function hl(text, query) {
  return highlightHtml(text, query)
}

const grouped = computed(() => {
  let list = notes.filterItems({
    cat: props.cat,
    favOnly: props.favOnly,
    q: props.q,
    favs: userData.favs,
    tags: props.tags,
  })
  if (props.sort === 'mtime') {
    list.sort((a, b) => b.ts - a.ts)
  } else if (props.sort === 'hot') {
    list.sort((a, b) => (userData.openCounts[b.id] || 0) - (userData.openCounts[a.id] || 0) || b.ts - a.ts)
  }
  return list
})

const groupedByCat = computed(() => {
  if (props.sort !== 'default') {
    const name = props.sort === 'mtime' ? '最近更新' : '热门笔记'
    return [{ name, items: grouped.value }]
  }
  // 选了分类筛选时，所有命中笔记（含跨分类标签联动的）归入该分类一组展示，
  // 不再按各自主分类拆分（否则 SSH 编译升级会跑到"安全防护"组去）。
  if (props.cat) {
    return [{ name: props.cat, items: grouped.value }]
  }
  const m = {}
  grouped.value.forEach(n => {
    if (!m[n.cat]) m[n.cat] = []
    m[n.cat].push(n)
  })
  return notes.catOrder.filter(c => m[c]).map(c => ({ name: c, items: m[c] }))
})

/**
 * 分页后的分组数据：每个分类只返回前 (pagesLoaded * PAGE_SIZE) 条。
 * 配合 loadMore() 实现渐进加载，避免大量笔记一次性渲染。
 */
const pagedGroupedByCat = computed(() => {
  return groupedByCat.value.map(g => {
    const pages = pagesLoaded.value[g.name] || 1
    const limit = pages * PAGE_SIZE
    return {
      ...g,
      visibleItems: g.items.slice(0, limit),
      hasMore: g.items.length > limit,
    }
  })
})

/** 加载某个分类的下一页 */
function loadMore(catName) {
  pagesLoaded.value[catName] = (pagesLoaded.value[catName] || 1) + 1
}

// 过滤条件变化时重置分页
watch([() => props.cat, () => props.q, () => props.favOnly, () => props.tags], () => {
  pagesLoaded.value = {}
})

/**
 * 监听全局 scroll-to-note 事件：
 * TreeView 点击的笔记如果被分页截断（不在 DOM 中），这里展开分页后滚动。
 */
function onScrollToNote(e) {
  const { id, cat } = e.detail
  // 展开目标分类的分页，确保所有条目都渲染
  const group = groupedByCat.value.find(g => g.name === cat)
  if (group) {
    pagesLoaded.value[cat] = Math.ceil(group.items.length / PAGE_SIZE) + 1
  }
  // 抑制 scroll-spy 避免平滑滚动过程中目录树抖动
  suppressSpy = true
  clearTimeout(suppressTimer)
  suppressTimer = setTimeout(() => { suppressSpy = false }, 1200)
  // 等待：nextTick 等 Vue DOM 更新（分页展开/视图切换），rAF 等布局完成。
  nextTick(() => {
    requestAnimationFrame(() => {
      const el = document.getElementById(id)
      if (!el) return
      const scrollWindow = document.querySelector('.notes-scroll-window')
      if (scrollWindow) {
        // 手动计算位置，明确避开 main 内部的粘性筛选栏。scrollIntoView 在
        // 嵌套滚动容器中偶尔不会正确应用 scroll-margin，导致笔记标题被遮住。
        const target = scrollWindow.scrollTop + el.getBoundingClientRect().top - scrollWindow.getBoundingClientRect().top - 12
        scrollWindow.scrollTo({ top: Math.max(0, target), behavior: 'auto' })
      } else {
        el.scrollIntoView({ behavior: 'auto', block: 'start' })
      }
      // 先清除其他卡片残留的 card-flash（上次点击加的，动画结束但 class 未移除），
      // 再给当前卡片加，保证同一时刻只有一张卡片高亮。
      document.querySelectorAll('.card-flash').forEach(n => n.classList.remove('card-flash'))
      void el.offsetWidth
      el.classList.add('card-flash')
    })
  })
}

// ==================== Scroll-spy：页面滚动时同步目录树高亮 ====================
let spyRaf = null
let suppressSpy = false
let suppressTimer = null
let lastSpyId = null

function onWindowScroll(e) {
  const scrollWindow = document.querySelector('.notes-scroll-window')
  if (!scrollWindow || e?.target !== scrollWindow) return
  if (spyRaf || suppressSpy) return
  spyRaf = requestAnimationFrame(() => {
    spyRaf = null
    // 详情视图时 CardList 不在 DOM，跳过
    const cards = document.querySelectorAll('[data-card]')
    if (!cards.length) return
    // 找到最后一个 top ≤ threshold 的卡片 = 用户正在看的卡片
    const threshold = scrollWindow.getBoundingClientRect().top + 24
    let bestId = null
    for (const card of cards) {
      const rect = card.getBoundingClientRect()
      if (rect.top <= threshold) {
        bestId = card.id
      }
    }
    if (bestId && bestId !== lastSpyId) {
      lastSpyId = bestId
      // expand: false → scroll-spy 不自动展开折叠的分类，只更新高亮和滚动
      window.dispatchEvent(new CustomEvent('note-activated', {
        detail: { id: bestId, expand: false }
      }))
    }
  })
}

onMounted(() => {
  window.addEventListener('scroll-to-note', onScrollToNote)
  // 滚动容器已从 window 改为 main（IndexPage），用 capture 监听 document
  // 才能收到 main 元素的 scroll 事件
  document.addEventListener('scroll', onWindowScroll, { passive: true, capture: true })
})
onUnmounted(() => {
  window.removeEventListener('scroll-to-note', onScrollToNote)
  document.removeEventListener('scroll', onWindowScroll, { capture: true })
  clearTimeout(suppressTimer)
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <div v-if="!notes.items.length && notes.loading">
      <div class="flex flex-col gap-3">
        <div v-for="i in 6" :key="i" class="skeleton"></div>
      </div>
    </div>
    <div v-else-if="notes.error" class="surface-card text-center py-12 rounded-xl" :style="{ color: '#ef4444' }">
      <div class="text-3xl mb-3">⚠️</div>
      <div class="text-sm font-semibold">数据加载失败</div>
      <div class="text-xs mt-1" :style="{ color: 'var(--muted)' }">{{ notes.error }}</div>
      <button
        @click="notes.load()"
        class="mt-4 px-4 py-2 rounded-lg text-sm font-semibold cursor-pointer transition-all hover:scale-[1.04]"
        :style="{ background: 'var(--accent)', color: '#fff', border: 'none' }"
      >🔄 重新加载</button>
    </div>
    <div v-else-if="groupedByCat.length === 0 || groupedByCat.every(g => g.items.length === 0)" class="text-center py-16 rounded-xl surface-card">
      <div class="mb-3 inline-flex" :style="{ color: 'var(--muted)' }"><AppIcon name="search" :size="36" stroke-width="1.5" /></div>
      <div class="text-base font-semibold" :style="{ color: 'var(--text)' }">没有匹配的笔记</div>
      <div class="text-sm mt-1 text-muted">
        尝试调整搜索关键词或筛选条件
      </div>
    </div>
    <template v-else>
      <section v-for="g in pagedGroupedByCat" :key="g.name" class="scroll-mt-[110px]">
        <h2
          class="flex items-center gap-2.5 text-lg font-semibold m-0 pb-2 mb-3"
          :style="{ borderBottom: '2px solid ' + (CAT_COLORS[g.name] || 'var(--accent)') }"
        >
          <span>{{ notes.catIcons[g.name] || '' }}</span>
          <span>{{ g.name }}</span>
          <span
            class="text-xs font-normal rounded-full px-2.5 py-0.5 ml-1"
            :style="{ background: 'var(--hover)', color: 'var(--muted)' }"
          >{{ g.items.length }}</span>
        </h2>
        <div class="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <div
            v-for="n in g.visibleItems"
            :key="n.id"
            :id="n.id"
            data-card
            @click="emit('card-click', n.id)"
            class="surface-card-r p-4 cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg scroll-mt-[110px]"
            :class="{ 'border-dashed': n.type === 'pdf' }"
          >
            <div class="flex items-baseline gap-1.5 mb-1.5 text-sm">
              <button
                @click.stop="userData.toggleFav(n.id)"
                :aria-label="userData.favs.has(n.id) ? '取消收藏' : '收藏'"
                class="text-base leading-none p-0 border-none bg-transparent cursor-pointer transition-all hover:scale-110 inline-flex"
                :style="{ color: userData.favs.has(n.id) ? 'var(--star)' : 'var(--muted)' }"
              ><AppIcon name="star" :size="14" :fill="userData.favs.has(n.id) ? 'currentColor' : 'none'" /></button>
              <a
                v-if="n.openurl"
                :href="n.openurl"
                @click.stop
                class="font-semibold no-underline break-all hover:opacity-80 transition-opacity"
                :class="{ 'opacity-60': userData.readSet.has(n.id) }"
                :style="{ color: 'var(--accent)' }"
                v-html="hl(n.name, q)"
              ></a>
              <a
                v-else
                @click.prevent.stop="emit('card-click', n.id)"
                class="font-semibold no-underline break-all hover:opacity-80 transition-opacity cursor-pointer"
                :class="{ 'opacity-60': userData.readSet.has(n.id) }"
                :style="{ color: 'var(--accent)' }"
                v-html="hl(n.name, q)"
              ></a>
              <a
                :href="n.fileurl ? '/files/' + n.fileurl.replace(/^\.\//, '') : '#'"
                target="_blank"
                @click.stop
                aria-label="在新标签页打开文件"
                class="no-underline text-sm hover:opacity-70 transition-opacity ml-auto"
                :style="{ color: 'var(--muted)' }"
              >↗</a>
            </div>
            <div class="flex items-center gap-2 flex-wrap text-xs mb-2" :style="{ color: 'var(--muted)' }">
              <span class="inline-flex items-center gap-0.5">{{ n.cat }}</span>
              <span class="opacity-40">·</span>
              <span>{{ n.size }}</span>
              <span v-if="n.lines" class="opacity-40">·</span>
              <span v-if="n.lines">约{{ n.lines }}行</span>
              <span class="opacity-40">·</span>
              <span>{{ n.mtime }}</span>
              <span v-if="n.stub" class="inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded ml-1" :style="{ background: 'var(--star-bg)', color: 'var(--star-text)' }">占位</span>
              <span v-if="userData.readSet.has(n.id)" class="inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded ml-1" :style="{ background: 'var(--hover)', color: 'var(--muted)' }">已读</span>
              <span v-if="(userData.openCounts[n.id] || 0) >= 3" class="inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded ml-1" :style="{ background: 'var(--danger-bg)', color: 'var(--danger-text)' }">🔥 {{ userData.openCounts[n.id] }}</span>
            </div>
            <div class="flex gap-1.5 flex-wrap">
              <button
                v-for="t in (n.tags || [])"
                :key="t"
                @click.stop="emit('tag-click', t)"
                class="text-xs px-2 py-0.5 rounded-full cursor-pointer border transition-all hover:scale-[1.04]"
                :class="tags.has(t) ? 'text-white border-solid' : 'border-dashed'"
                :style="tags.has(t) ? { background: 'var(--accent2)', borderColor: 'var(--accent2)' } : { background: 'transparent', color: 'var(--muted)', borderColor: 'var(--line)' }"
              >{{ t }}</button>
            </div>
            <details v-if="n.heads && n.heads.length" class="mt-2.5 text-xs" :open="!!q">
              <summary class="inline-flex items-center gap-1 font-medium cursor-pointer select-none transition-colors hover:opacity-80" :style="{ color: 'var(--accent2)' }">📑 章节大纲 ({{ n.heads.length }})</summary>
              <ul class="list-none p-0 m-2 text-xs" :style="{ color: 'var(--text)' }">
                <li v-for="([lvl, t]) in n.heads.slice(0, 30)" :key="t" class="py-0.5" :style="{ paddingLeft: (lvl - 1) * 16 + 'px', borderBottom: '1px dashed var(--line)' }">
                  <span v-html="hl(t, q)"></span>
                </li>
              </ul>
            </details>
          </div>
        </div>
        <!-- 加载更多：该分类还有未显示的笔记时显示 -->
        <div v-if="g.hasMore" class="text-center mt-2 mb-1">
          <button
            @click="loadMore(g.name)"
            class="px-5 py-2 rounded-lg text-sm font-medium cursor-pointer transition-all hover:scale-[1.03] surface-card-r text-accent"
          >加载更多（剩余 {{ g.items.length - g.visibleItems.length }} 篇）</button>
        </div>
      </section>
    </template>
  </div>
</template>

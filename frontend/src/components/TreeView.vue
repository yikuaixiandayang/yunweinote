<script setup>
import AppIcon from './AppIcon.vue'
import { computed, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'

const emit = defineEmits(['select-cat', 'navigate'])
const notes = useNotesStore()
const userData = useUserDataStore()

/** 当前高亮的笔记 id（由全局 note-activated 事件驱动） */
const activeNoteId = ref(null)
const activeCategory = ref(null)

/** 目录树 nav 区域 ref，用于内部滚动定位 */
const navRef = ref(null)

const grouped = computed(() => {
  const m = {}
  notes.items.forEach(n => {
    if (!m[n.cat]) m[n.cat] = []
    m[n.cat].push(n)
  })
  return notes.catOrder.filter(c => m[c]).map(c => ({ name: c, items: m[c] }))
})

function isCollapsed(name) {
  return userData.collapsed.has(name)
}

function toggle(name) {
  userData.toggleCollapsed(name)
}

function toggleAll() {
  if (userData.collapsed.size >= grouped.value.length) {
    userData.expandAll()
  } else {
    userData.collapseAll(grouped.value.map(g => g.name))
  }
}

/**
 * 同步高亮 + 自动展开父级 + 滚动到目录树中的对应节点。
 * 由全局 note-activated 事件触发（所有导航场景统一入口）。
 * @param id  笔记 id
 * @param expand  是否自动展开父级分类（scroll-spy 时为 false，避免打断用户折叠意图）
 */
function syncToNote(id, expand = true) {
  if (!id) {
    activeNoteId.value = null
    activeCategory.value = null
    return
  }
  const note = notes.items.find(n => n.id === id)
  if (!note) return

  activeNoteId.value = id
  activeCategory.value = note.cat

  // 仅在明确需要时自动展开父级分类
  if (expand && userData.collapsed.has(note.cat)) {
    userData.toggleCollapsed(note.cat)
  }

  // 等待 DOM 更新（展开分类后子节点才渲染）再滚动定位
  nextTick(() => {
    const el = document.getElementById('tree-' + id)
    if (el && navRef.value) {
      const container = navRef.value
      const containerRect = container.getBoundingClientRect()
      const elRect = el.getBoundingClientRect()
      const offsetTop = elRect.top - containerRect.top + container.scrollTop
      container.scrollTo({ top: Math.max(0, offsetTop - 60), behavior: 'smooth' })
    }
  })
}

/** 监听全局 note-activated 事件（所有导航入口统一派发） */
function onNoteActivated(e) {
  syncToNote(e.detail.id, e.detail.expand ?? true)
}

onMounted(() => {
  window.addEventListener('note-activated', onNoteActivated)
})
onUnmounted(() => {
  window.removeEventListener('note-activated', onNoteActivated)
})

/**
 * 点击目录树中的笔记条目：
 * - PDF → 直接在新标签打开
 * - MD → emit navigate 让 IndexPage 统一处理（清分类筛选 + 滚动到卡片）
 * 同时派发 note-activated 高亮自身。
 */
function handleNoteClick(n) {
  window.dispatchEvent(new CustomEvent('note-activated', { detail: { id: n.id } }))

  if (n.type === 'pdf') {
    const url = '/files/' + String(n.fileurl || '').replace(/^\.\//, '')
    window.open(url, '_blank')
    userData.markOpen(n.id)
    return
  }

  emit('navigate', n)
}

/**
 * 点击分类名：既筛选分类（emit select-cat），又展开/折叠该分类。
 * 用 @click.prevent.stop 阻止冒泡到外层 div 的 toggle，避免双重 toggle 相互抵消。
 * 点箭头 ▸ 走外层 div 的 toggle（只折叠/展开，不筛选）。
 */
function handleCatClick(name) {
  activeCategory.value = name
  emit('select-cat', name)
  userData.toggleCollapsed(name)   // 切换折叠状态（展开↔折叠）
}

function categoryStyle(name) {
  return activeCategory.value === name
    ? {
        color: 'var(--accent)',
        background: 'color-mix(in srgb, var(--accent) 10%, transparent)',
        boxShadow: 'inset 3px 0 0 var(--accent)',
      }
    : { color: 'var(--text)' }
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center text-sm font-semibold px-1.5 pb-2 mb-1.5" :style="{ borderBottom: '1px solid var(--line)' }">
      <span class="inline-flex items-center gap-1.5"><AppIcon name="panelLeft" :size="13" /> 目录树</span>
      <button
        @click="toggleAll"
        class="text-xs px-2.5 py-0.5 rounded-md cursor-pointer transition-all hover:opacity-80"
        :style="{ border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--muted)' }"
      >{{ userData.collapsed.size >= grouped.length ? '全部展开' : '全部折叠' }}</button>
    </div>
    <nav ref="navRef">
      <div v-for="g in grouped" :key="g.name" class="mb-0.5">
        <div
          @click="toggle(g.name)"
          @keydown.enter="toggle(g.name)"
          @keydown.space.prevent="toggle(g.name)"
          role="button" tabindex="0" :aria-expanded="!isCollapsed(g.name)" :aria-current="activeCategory === g.name ? 'location' : undefined"
          class="flex items-center gap-1 px-1.5 py-1.5 rounded-lg cursor-pointer text-sm font-semibold select-none transition-all hover:opacity-80"
          :style="categoryStyle(g.name)"
        >
          <span class="text-xs transition-transform" :class="{ 'rotate-90': !isCollapsed(g.name) }" :style="{ color: 'var(--muted)', width: '14px', flex: 'none' }">▸</span>
          <a
            @click.prevent.stop="handleCatClick(g.name)"
            @keydown.enter.prevent="handleCatClick(g.name)"
            @keydown.space.prevent="handleCatClick(g.name)"
            role="button" tabindex="0" :aria-label="`筛选分类 ${g.name}`"
            class="flex-1 no-underline truncate"
            :style="{ color: 'var(--text)' }"
          >{{ g.name }}</a>
          <span class="text-xs font-normal" :style="{ color: 'var(--muted)' }">{{ g.items.length }}</span>
        </div>
        <div v-show="!isCollapsed(g.name)" class="ml-4">
          <a
            v-for="n in g.items" :key="n.id"
            :id="'tree-' + n.id"
            @click.prevent="handleNoteClick(n)"
            @keydown.enter.prevent="handleNoteClick(n)"
            @keydown.space.prevent="handleNoteClick(n)"
            role="button" tabindex="0" :aria-current="activeNoteId === n.id ? 'page' : undefined"
            class="block text-xs px-1.5 py-1 rounded-md truncate cursor-pointer no-underline transition-all hover:opacity-80 hover:pl-2.5"
            :style="activeNoteId === n.id
              ? { color: 'var(--accent)', background: 'var(--hover)', fontWeight: 600, paddingLeft: '10px' }
              : { color: 'var(--muted)' }"
          ><span v-if="userData.favs.has(n.id)" class="inline-flex mr-0.5" :style="{ color: 'var(--star)' }"><AppIcon name="star" :size="10" /></span>{{ n.name }}</a>
        </div>
      </div>
    </nav>
    <!-- 阅读进度 -->
    <div class="mt-3">
      <div class="flex justify-between text-xs mb-1" :style="{ color: 'var(--muted)' }">
        <span>阅读进度</span>
        <span class="font-semibold">{{ userData.stats.pct }}%</span>
      </div>
      <div class="h-1.5 rounded-full overflow-hidden" :style="{ background: 'var(--hover)' }">
        <div
          class="h-full rounded-full transition-all duration-700 ease-out"
          :style="{ width: userData.stats.pct + '%', background: 'linear-gradient(90deg, var(--accent), var(--accent2))' }"
        ></div>
      </div>
      <div class="text-xs mt-1" :style="{ color: 'var(--muted)' }">已读 {{ userData.stats.read }}/{{ userData.stats.total }}</div>
    </div>
  </div>
</template>

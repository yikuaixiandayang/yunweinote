<script setup>
import AppIcon from './AppIcon.vue'
import { ref } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { searchNotes } from '../api'
import { highlightHtml } from '../utils/safeHtml.js'

const emit = defineEmits(['search', 'open-note'])
const notes = useNotesStore()
const userData = useUserDataStore()
const q = ref('')
const showSuggest = ref(false)
const suggestItems = ref([])
const hoverIdx = ref(-1)
const inputEl = ref(null)

let timer = null
let searchTimer = null

function onInput(val) {
  q.value = val
  clearTimeout(timer)
  clearTimeout(searchTimer)
  // 即时本地过滤（响应快，用于卡片列表高亮）
  timer = setTimeout(() => {
    emit('search', val.trim())
    if (val.trim()) {
      userData.addSearchHist(val.trim())
    }
  }, 120)
  // 300ms 防抖后端全文搜索（用于搜索建议下拉，可搜正文）
  searchTimer = setTimeout(() => {
    updateSuggest(val.trim())
  }, 300)
}

async function updateSuggest(val) {
  if (!val) {
    showSuggest.value = false
    return
  }
  try {
    const res = await searchNotes(val, { size: 6 })
    if (res.results && res.results.length > 0) {
      suggestItems.value = res.results.map(r => ({
        id: r.id,
        name: r.name,
        excerpt: r.excerpt || '',
        cat: r.cat || '',
        score: r.score || 0,
      }))
      showSuggest.value = true
      return
    }
  } catch { /* 网络错误时 fallback 到本地 */ }
  // Fallback: 本地搜索笔记名和标签
  const list = notes.items.filter(n => {
    const hay = (n.name + ' ' + n.cat + ' ' + (n.tags || []).join(' ')).toLowerCase()
    return hay.includes(val.toLowerCase())
  })
  if (list.length > 0) {
    suggestItems.value = list.slice(0, 5).map(n => ({ id: n.id, name: n.name, excerpt: '', cat: n.cat }))
    showSuggest.value = true
  } else {
    const tags = new Set()
    notes.items.forEach(n => (n.tags || []).forEach(t => tags.add(t)))
    const matched = [...tags].filter(t => t.includes(val.toLowerCase())).slice(0, 8)
    suggestItems.value = matched.map(t => ({ tag: t }))
    showSuggest.value = true
  }
}

function goToNote(id) {
  emit('open-note', id)
  // 清空搜索框 + 取消过滤，让用户返回列表时看到全部笔记
  q.value = ''
  emit('search', '')
  showSuggest.value = false
}

function filterByTag(tag) {
  emit('search', '')
  q.value = ''
  showSuggest.value = false
  window.dispatchEvent(new CustomEvent('tag-filter', { detail: tag }))
}

function clearSearch() {
  q.value = ''
  emit('search', '')
  showSuggest.value = false
}

/** 聚焦搜索框（供父组件快捷键调用） */
function focus() {
  if (inputEl.value) inputEl.value.focus()
}

function hl(text, query) {
  return highlightHtml(text, query)
}

defineExpose({ focus, clearSearch })
</script>

<template>
  <div class="relative flex-1 min-w-[200px]">
    <div class="relative">
      <span class="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none inline-flex" :style="{ color: 'var(--muted)' }"><AppIcon name="search" :size="14" /></span>
      <input
        ref="inputEl"
        :value="q"
        @input="onInput($event.target.value)"
        @focus="q && updateSuggest(q)"
        @keydown.esc="clearSearch"
        type="text"
        placeholder="搜索笔记名称 / 正文 / 标签…  (按 / 快速聚焦)"
        class="w-full h-10 pl-9 pr-9 text-sm rounded-lg outline-none transition-all duration-200 focus:border-[var(--accent)]"
        :style="{
          background: 'var(--card)',
          color: 'var(--text)',
          border: '1px solid var(--line)',
        }"
      />
      <button
        v-show="q"
        @click="clearSearch"
        class="absolute right-2 top-1/2 -translate-y-1/2 text-lg leading-none p-0.5 rounded transition-all hover:scale-110"
        :style="{ color: 'var(--muted)' }"
      >&times;</button>
    </div>
    <div
      v-show="showSuggest"
      class="absolute top-11 left-0 right-0 z-10 border rounded-xl shadow-lg overflow-hidden text-sm"
      :style="{
        background: 'var(--card)',
        borderColor: 'var(--line)',
      }"
    >
      <div
        v-for="(item, i) in suggestItems"
        :key="item.id || item.tag"
        class="px-3.5 py-2.5 cursor-pointer transition-colors"
        :style="{
          color: 'var(--text)',
          borderBottom: i < suggestItems.length - 1 ? '1px solid var(--line)' : 'none',
          background: hoverIdx === i ? 'var(--hover)' : '',
        }"
        @mouseenter="hoverIdx = i"
        @mouseleave="hoverIdx = -1"
      >
        <div v-if="item.id" class="flex flex-col gap-0.5" @click="goToNote(item.id)">
          <div class="flex items-center gap-2">
            <span class="flex-none inline-flex" :style="{ color: 'var(--muted)' }"><AppIcon name="paper" :size="12" /></span>
            <span class="truncate font-medium" v-html="hl(item.name, q)"></span>
            <span v-if="item.cat" class="text-xs ml-auto flex-none" :style="{ color: 'var(--muted)' }">{{ item.cat }}</span>
          </div>
          <div v-if="item.excerpt" class="text-xs pl-5 truncate" :style="{ color: 'var(--muted)' }" v-html="hl(item.excerpt.slice(0, 80), q)"></div>
        </div>
        <div v-else class="flex items-center gap-2 w-full" @click="filterByTag(item.tag)">
          <span class="text-xs flex-none">🏷️</span>
          <span :style="{ color: 'var(--accent)', fontWeight: 600 }">{{ item.tag }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

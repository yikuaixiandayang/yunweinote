import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getData } from '../api'
import { useUserDataStore } from './userData'
import { noteMatchesCat } from '../constants'

export const useNotesStore = defineStore('notes', () => {
  const raw = ref({ notes: [], pdfs: [], catOrder: [], catIcons: {}, stats: {}, editors: {} })
  const loading = ref(true)
  const error = ref(null)
  const contentCache = ref({})

  const items = computed(() => {
    const md = raw.value.notes.map(n => ({ ...n, type: 'md' }))
    const pdf = raw.value.pdfs.map(p => ({ ...p, type: 'pdf' }))
    return [...md, ...pdf]
  })

  const stats = computed(() => raw.value.stats)
  const catOrder = computed(() => raw.value.catOrder)
  const catIcons = computed(() => raw.value.catIcons)
  const editors = computed(() => raw.value.editors || {})

  async function load() {
    loading.value = true
    error.value = null
    try {
      const res = await getData()
      raw.value = res.payload || res
      // 从 /api/data 返回的 user_data 合并到本地 userData store
      if (res.user_data) {
        const userData = useUserDataStore()
        userData.mergeFromServer(res.user_data)
      }
      // 目录树默认折叠：每次加载时如果所有分类都展开（collapsed 为空），
      // 就自动折叠全部。"全部展开"不作为持久状态，用户手动展开某个分类后
      // collapsed 里会少那个分类（size > 0），不再触发自动折叠。
      const SP = 'wbidx_'
      const userData = useUserDataStore()
      if (userData.collapsed.size === 0 && raw.value.catOrder?.length) {
        userData.collapseAll(raw.value.catOrder)
      }
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  /** 缓存上限：超过后删除最早的条目（简易 LRU） */
  const CACHE_MAX = 20

  async function getContent(id, fileurl) {
    if (contentCache.value[id]) return contentCache.value[id]
    // fileurl 形如 ./Ansible...md（相对路径），在浏览器里会解析到站点根导致 404。
    // 统一改走后端 /api/note/{rel}：它返回解析好的 markdown，且会将相对图片引用
    // 重写为 /files/{目录}/图片，保证内嵌预览正文和图片都能正确加载。
    const rel = String(fileurl || '').replace(/^\.\//, '')
    const res = await fetch(`/api/note/${rel}`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    const text = data.content ?? ''
    // LRU 淘汰：超过上限时删除最早写入的条目
    const keys = Object.keys(contentCache.value)
    if (keys.length >= CACHE_MAX) {
      delete contentCache.value[keys[0]]
    }
    contentCache.value[id] = text
    return text
  }

  function findNote(id) {
    return items.value.find(n => n.id === id)
  }

  /**
   * 模糊匹配：q 的每个字符按顺序出现在 text 中即匹配。
   * 用于短关键词（≥2 字符）的宽容搜索。
   */
  function fuzzyMatch(q, text) {
    let i = 0
    const s = text.toLowerCase()
    for (const c of s) {
      if (c === q[i]) i++
      if (i === q.length) return true
    }
    return false
  }

  /**
   * 统一过滤函数：按分类/收藏/搜索/标签筛选笔记列表。
   * IndexPage.filteredCount 和 CardList.grouped 共用此函数，避免逻辑重复。
   * @param {Object} opts - { cat, favOnly, q, favs, tags }
   * @returns {Array} 过滤后的笔记数组
   */
  function filterItems(opts = {}) {
    let list = [...items.value]
    const { cat, favOnly, q, favs, tags } = opts

    if (cat) list = list.filter(n => noteMatchesCat(n, cat))
    if (favOnly && favs) list = list.filter(n => favs.has(n.id))
    if (q) {
      const ql = q.toLowerCase()
      list = list.filter(n => {
        const hay = (n.name + ' ' + (n.rel || '') + ' ' + n.cat + ' ' + (n.tags || []).join(' ') + ' ' + (n.heads || []).map(h => h[1]).join(' ')).toLowerCase()
        return hay.includes(ql) || (ql.length >= 2 && fuzzyMatch(ql, n.name))
      })
    }
    if (tags && tags.size) {
      list = list.filter(n => [...tags].every(t => (n.tags || []).includes(t)))
    }
    return list
  }

  return { raw, loading, error, contentCache, items, stats, catOrder, catIcons, editors, load, findNote, getContent, filterItems }
})

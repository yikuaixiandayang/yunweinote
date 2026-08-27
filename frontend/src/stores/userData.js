import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { saveUserData } from '../api'
import { useNotesStore } from './notes'

const STORAGE_PREFIX = 'wbidx_'

function loadFromStorage(key, fallback) {
  try {
    const v = localStorage.getItem(STORAGE_PREFIX + key)
    return v !== null ? JSON.parse(v) : fallback
  } catch {
    return fallback
  }
}

function saveToStorage(key, value) {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value))
  } catch { /* quota exceeded */ }
}

// 防抖同步到服务端（500ms 内多次操作合并为一次请求）
let _syncTimer = null
function debouncedSync(syncFn) {
  if (_syncTimer) clearTimeout(_syncTimer)
  _syncTimer = setTimeout(() => {
    syncFn().catch(() => {})
    _syncTimer = null
  }, 500)
}

export const useUserDataStore = defineStore('userData', () => {
  const favs = ref(new Set(loadFromStorage('favs', [])))
  const readSet = ref(new Set(loadFromStorage('read', [])))
  const openCounts = ref(loadFromStorage('opens', {}))
  const collapsed = ref(new Set(loadFromStorage('collapsed', [])))
  const searchHist = ref(loadFromStorage('searchHist', []))
  // 最近浏览记录：[{ id, ts }] 倒序（最新在前），同一笔记只保留最近一次，上限 100 条。
  // ts 为 Unix 毫秒时间戳，用于按"今天/昨天/前天/更早"分组展示。
  const viewHist = ref(loadFromStorage('viewHist', []))

  const favList = computed(() => [...favs.value])
  const stats = computed(() => {
    const store = useNotesStore()
    const total = store.items.length
    const read = readSet.value.size
    return { total, read, pct: total ? Math.round(read / total * 100) : 0 }
  })

  function toggleFav(id) {
    const s = new Set(favs.value)
    s.has(id) ? s.delete(id) : s.add(id)
    favs.value = s
    saveToStorage('favs', [...s])
    debouncedSync(syncToServer)
  }

  function toggleRead(id) {
    const s = new Set(readSet.value)
    s.has(id) ? s.delete(id) : s.add(id)
    readSet.value = s
    saveToStorage('read', [...s])
    debouncedSync(syncToServer)
  }

  function markOpen(id) {
    const c = { ...openCounts.value }
    c[id] = (c[id] || 0) + 1
    openCounts.value = c
    saveToStorage('opens', c)
    if (!readSet.value.has(id)) {
      toggleRead(id)
    }
    pushViewHist(id)
    debouncedSync(syncToServer)
  }

  /**
   * 追加浏览历史：把同一笔记的旧记录剔除，新记录插到头部，倒序保留最多 100 条。
   * 与 markOpen 调用栈分离，便于将来在"阅读页"等其他入口复用。
   */
  function pushViewHist(id) {
    const next = [{ id, ts: Date.now() }, ...viewHist.value.filter(v => v.id !== id)]
    if (next.length > 100) next.length = 100
    viewHist.value = next
    saveToStorage('viewHist', next)
  }

  /** 手动清空浏览历史（供设置面板"清除浏览记录"调用） */
  function clearViewHist() {
    viewHist.value = []
    saveToStorage('viewHist', [])
    debouncedSync(syncToServer)
  }

  function toggleCollapsed(name) {
    const s = new Set(collapsed.value)
    s.has(name) ? s.delete(name) : s.add(name)
    collapsed.value = s
    saveToStorage('collapsed', [...s])
    debouncedSync(syncToServer)
  }

  function collapseAll(names) {
    collapsed.value = new Set(names)
    saveToStorage('collapsed', [...names])
    debouncedSync(syncToServer)
  }

  function expandAll() {
    collapsed.value = new Set()
    saveToStorage('collapsed', [])
    debouncedSync(syncToServer)
  }

  function addSearchHist(q) {
    const h = [...searchHist.value]
    const idx = h.indexOf(q)
    if (idx > -1) h.splice(idx, 1)
    h.unshift(q)
    if (h.length > 20) h.length = 20
    searchHist.value = h
    saveToStorage('searchHist', h)
    debouncedSync(syncToServer)
  }

  /**
   * 删除一条搜索历史关键词。
   * 复习面板的"搜索未覆盖"(gap) 是从 searchHist 实时派生的——
   * 后端 _uncovered() 把 searchHist 里没匹配到任何笔记标题/标签的关键词算作缺口。
   * 所以删掉这条搜索词后，下次 /api/insights 该 gap 自动消失，无需改后端。
   */
  function removeSearchHist(q) {
    const h = searchHist.value.filter(x => x !== q)
    if (h.length === searchHist.value.length) return
    searchHist.value = h
    saveToStorage('searchHist', h)
    debouncedSync(syncToServer)
  }

  /** 清空全部搜索历史 */
  function clearSearchHist() {
    searchHist.value = []
    saveToStorage('searchHist', [])
    debouncedSync(syncToServer)
  }

  /**
   * 从服务端 user_data 合并到本地（首次加载时调用）。
   * 服务端有数据但本地无 → 使用服务端；两者都有 → 本地优先（本地为最新操作源）。
   */
  function mergeFromServer(serverData) {
    if (!serverData || typeof serverData !== 'object') return
    const sf = serverData.favs || []
    const sr = serverData.read || []
    const so = serverData.opens || {}
    const ss = serverData.searchHist || []
    const svh = serverData.viewHist || []

    // 本地为空且服务端有数据 → 采用服务端
    if (!favs.value.size && sf.length) {
      favs.value = new Set(sf)
      saveToStorage('favs', sf)
    }
    if (!readSet.value.size && sr.length) {
      readSet.value = new Set(sr)
      saveToStorage('read', sr)
    }
    if (!Object.keys(openCounts.value).length && Object.keys(so).length) {
      openCounts.value = so
      saveToStorage('opens', so)
    }
    if (!searchHist.value.length && ss.length) {
      searchHist.value = ss
      saveToStorage('searchHist', ss)
    }
    if (!viewHist.value.length && svh.length) {
      viewHist.value = svh
      saveToStorage('viewHist', svh)
    }
  }

  async function syncToServer() {
    try {
      await saveUserData({
        favs: [...favs.value],
        read: [...readSet.value],
        opens: openCounts.value,
        collapsed: [...collapsed.value],
        searchHist: searchHist.value,
        viewHist: viewHist.value,
      })
    } catch { /* silent */ }
  }

  return {
    favs, readSet, openCounts, collapsed, searchHist, viewHist,
    favList, stats,
    toggleFav, toggleRead, markOpen, pushViewHist, clearViewHist,
    toggleCollapsed, collapseAll, expandAll,
    addSearchHist, removeSearchHist, clearSearchHist,
    syncToServer, mergeFromServer,
  }
})

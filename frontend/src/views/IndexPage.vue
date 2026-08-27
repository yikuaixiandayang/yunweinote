<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { noteMatchesCat } from '../constants'
import AppHeader from '../components/AppHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import Sidebar from '../components/Sidebar.vue'
import TreeView from '../components/TreeView.vue'
import Dashboard from '../components/Dashboard.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import SearchBar from '../components/SearchBar.vue'
import CardList from '../components/CardList.vue'
import DetailPanel from '../components/DetailPanel.vue'
import Heatmap from '../components/Heatmap.vue'
import Breadcrumb from '../components/Breadcrumb.vue'
import ScrollTop from '../components/ScrollTop.vue'

const notes = useNotesStore()
const userData = useUserDataStore()

const q = ref('')
const cat = ref(null)
const sort = ref('default')
const favOnly = ref(false)
const tags = ref(new Set())
const tagExpanded = ref(false)
const currentView = ref('cards')
const detailId = ref(null)
const detailNote = ref(null)
const sidebarOpen = ref(false)
const searchBarRef = ref(null)
const navigationMessage = ref('')
let navigationMessageTimer = null
const reviewPanelOpen = ref(true)   // 右侧复习栏：默认展开，用户可点击收起腾出主内容空间

// 复用 CardList 的过滤结果避免重复计算
const _filterKey = computed(() => JSON.stringify({
  cat: cat.value, q: q.value, favOnly: favOnly.value,
  tags: [...tags.value].sort(), favs: [...userData.favs].sort(),
}))
const _cachedFilter = ref({ key: '', count: 0 })

const filteredCount = computed(() => {
  const key = _filterKey.value
  if (_cachedFilter.value.key === key) return _cachedFilter.value.count
  const count = notes.filterItems({
    cat: cat.value, favOnly: favOnly.value, q: q.value,
    favs: userData.favs, tags: tags.value,
  }).length
  _cachedFilter.value = { key, count }
  return count
})

const catChips = computed(() => {
  // 分类+标签联动：一篇笔记可能属于多个分类（主分类 + 标签关联的分类），
  // 各分类计数均包含关联笔记，点分类时能跨分类发现。
  const m = {}
  notes.catOrder.forEach(c => { m[c] = [] })
  notes.items.forEach(n => {
    notes.catOrder.forEach(c => {
      if (noteMatchesCat(n, c)) m[c].push(n)
    })
  })
  return notes.catOrder.filter(c => m[c] && m[c].length).map(c => ({ name: c, count: m[c].length }))
})

const availableTags = computed(() => {
  const freq = {}
  let base = [...notes.items]
  if (cat.value) base = base.filter(n => noteMatchesCat(n, cat.value))
  if (q.value) {
    const ql = q.value.toLowerCase()
    base = base.filter(n => n.name.toLowerCase().includes(ql))
  }
  base.forEach(n => (n.tags || []).forEach(t => freq[t] = (freq[t] || 0) + 1))
  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 24)
  return { all: sorted, visible: tagExpanded.value ? sorted : sorted.slice(0, 12) }
})

function handleSearch(val) {
  q.value = val
}

function handleCardClick(id) {
  const n = notes.findNote(id)
  // PDF 卡片：直接在新标签打开 PDF（浏览器原生渲染），不走 DetailPanel
  if (n && n.type === 'pdf') {
    const url = '/files/' + String(n.fileurl || '').replace(/^\.\//, '')
    window.open(url, '_blank')
    userData.markOpen(id)
    // 仍然同步目录树高亮
    window.dispatchEvent(new CustomEvent('note-activated', { detail: { id } }))
    return
  }
  detailNote.value = null
  detailId.value = id
  currentView.value = 'detail'
  // 派发全局事件：目录树同步高亮 + 展开父级 + 滚动定位
  window.dispatchEvent(new CustomEvent('note-activated', { detail: { id } }))
}

function handleTagClick(t) {
  const s = new Set(tags.value)
  s.has(t) ? s.delete(t) : s.add(t)
  tags.value = s
}

function handleCloseDetail() {
  detailId.value = null
  detailNote.value = null
  currentView.value = 'cards'
  // 关闭详情时清除目录树高亮
  window.dispatchEvent(new CustomEvent('note-activated', { detail: { id: null } }))
}

function handleStar(id) {
  userData.toggleFav(id)
}

/**
 * 顶部"已收藏"统计卡点击：切回卡片视图并启用"仅看收藏"筛选，
 * 让数字背后的具体笔记立刻可见。同时把搜索/分类/标签筛选清掉，
 * 避免叠加筛选导致收藏列表被进一步过滤看不见。
 */
function handleFavCardClick() {
  q.value = ''
  cat.value = null
  tags.value = new Set()
  sort.value = 'default'
  favOnly.value = true
  currentView.value = 'cards'
  detailId.value = null
  detailNote.value = null
  if (searchBarRef.value) searchBarRef.value.clearSearch()
  window.dispatchEvent(new CustomEvent('note-activated', { detail: { id: null } }))
  // 滚动到列表顶部
  nextTick(() => {
    const el = document.querySelector('.notes-scroll-window')
    if (el) el.scrollTo({ top: 0, behavior: 'smooth' })
  })
}

function handleToggleRead(id) {
  userData.toggleRead(id)
}

function openExternal(url) {
  const a = document.createElement('a')
  a.href = url
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/**
 * 打开笔记浏览（从 DetailPanel 的标签关联/卡片点击进入）：
 * 一律在网页端内嵌正式渲染阅读（Typora 风格排版），外部编辑器仅用于编辑。
 * 需要编辑时由 DetailPanel 的"在 Obsidian 中打开"按钮显式触发 handleEditInEditor。
 */
function handleOpenNote(id) {
  const n = notes.findNote(id)
  if (n) {
    userData.markOpen(id)
    handleCardClick(id)
  }
}

/**
 * 显式"在 Obsidian 中打开"：仅在用户主动点击时调用外部编辑器，阅读不经过它。
 * Obsidian 已定为唯一外部编辑器——Typora 为破解版，命令行拉起后只建空白文档、
 * 不加载已有内容（CVE-2023-2316 类协议问题 + 破解 patch 对文件加载的破坏），故弃用。
 */
async function handleEditInEditor(id) {
  const n = notes.findNote(id)
  if (!n) return
  userData.markOpen(id)
  const obsidian = notes.editors.obsidian || {}
  if (obsidian.installed && n.obsidianurl) {
    openExternal(n.obsidianurl)
    showNavigationMessage('已在 Obsidian 中打开')
    return
  }
  showNavigationMessage('未检测到 Obsidian，请在网页内直接阅读')
}

function handleSelectCat(name) {
  if (requireClearFilters()) return
  cat.value = name
}

/**
 * 目录树点击笔记 → 统一导航入口：
 * 筛选为空时，将侧栏笔记定位到卡片列表；有筛选时由 requireClearFilters 提示用户处理。
 */
function handleNavigate(n) {
  if (requireClearFilters()) return
  if (currentView.value !== 'cards') {
    currentView.value = 'cards'
  }
  // 双 nextTick：第一个等 currentView 切到 cards 让 CardList 渲染，
  // 第二个等 CardList 的 groupedByCat/pagedGroupedByCat computed 更新完 DOM
  nextTick(() => {
    nextTick(() => {
      window.dispatchEvent(new CustomEvent('scroll-to-note', {
        detail: { id: n.id, cat: n.cat }
      }))
    })
  })
}

const hasActiveFilters = computed(() => Boolean(
  cat.value || q.value || tags.value.size || favOnly.value || sort.value !== 'default'
))

function requireClearFilters() {
  if (!hasActiveFilters.value) return false
  showNavigationMessage('当前正在筛选，请先点击“清除筛选”后再从侧栏定位笔记')
  return true
}

function onNoteNavigationRequest(e) {
  const note = notes.findNote(e.detail.id)
  if (note) handleNavigate(note)
}

function showNavigationMessage(message) {
  navigationMessage.value = message
  clearTimeout(navigationMessageTimer)
  navigationMessageTimer = setTimeout(() => { navigationMessage.value = '' }, 3200)
}

function handleBreadcrumbHome() {
  cat.value = null
  q.value = ''
  tags.value = new Set()
  favOnly.value = false
  sort.value = 'default'
  if (searchBarRef.value) searchBarRef.value.clearSearch()
}

function handleBreadcrumbCatClear() {
  cat.value = null
}

function handleBreadcrumbClear() {
  handleBreadcrumbHome()
}

function handleExport() {
  const a = {}
  ;['favs', 'read', 'opens', 'collapsed', 'theme', 'searchHist'].forEach(k => {
    try {
      const v = localStorage.getItem('wbidx_' + k)
      if (v) a[k] = JSON.parse(v)
    } catch {}
  })
  const blob = new Blob([JSON.stringify(a, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '_user_data.json'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

onMounted(async () => {
  // 首次加载索引；若已在 store 缓存（从其他页跳来），load 内部会直接 resolve，不会重复请求
  if (notes.loading || !notes.items.length) await notes.load()
  window.addEventListener('tag-filter', onTagFilter)
  window.addEventListener('cat-filter', onCatFilter)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('note-navigation-request', onNoteNavigationRequest)
  // 学习路径 / 关系图谱页跳转过来时，目标笔记 id 写在 sessionStorage['graph_open_note']。
  // 之前只写不读导致只跳到首页、不打开笔记——这里补上消费逻辑。
  const pendingId = sessionStorage.getItem('graph_open_note')
  if (pendingId) {
    sessionStorage.removeItem('graph_open_note')
    // 确保目标笔记在索引中存在再打开，避免拿到脏 id
    if (notes.findNote(pendingId)) {
      handleCardClick(pendingId)
    }
  }
})

onUnmounted(() => {
  window.removeEventListener('tag-filter', onTagFilter)
  window.removeEventListener('cat-filter', onCatFilter)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('note-navigation-request', onNoteNavigationRequest)
  clearTimeout(navigationMessageTimer)
})

/**
 * 全局键盘快捷键：
 *   / 或 Ctrl+K → 聚焦搜索框
 *   Esc        → 清除搜索 / 关闭详情面板
 */
function onKeydown(e) {
  const tag = (e.target.tagName || '').toUpperCase()
  const isInputFocused = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'

  // / 或 Ctrl+K → 聚焦搜索（输入框中按 / 不触发，避免冲突）
  if ((e.key === '/' && !isInputFocused) || ((e.ctrlKey || e.metaKey) && e.key === 'k')) {
    e.preventDefault()
    if (searchBarRef.value) searchBarRef.value.focus()
    return
  }

  // Esc → 优先关闭详情面板，其次清除搜索
  if (e.key === 'Escape') {
    if (currentView.value === 'detail') {
      handleCloseDetail()
    } else if (searchBarRef.value) {
      searchBarRef.value.clearSearch()
    }
  }
}

function onTagFilter(e) {
  const s = new Set(tags.value)
  s.add(e.detail)
  tags.value = s
  currentView.value = 'cards'
  detailId.value = null
}

/** 看板分类分布条点击 → 筛选该分类，切回卡片列表 */
function onCatFilter(e) {
  cat.value = e.detail
  currentView.value = 'cards'
  detailId.value = null
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <!-- 共享顶栏 -->
    <AppHeader
      title="运维笔记总索引"
      show-menu
      @menu="sidebarOpen = !sidebarOpen"
    >
      <template #below>
        <div class="w-full text-xs pb-2 -mt-1" style="padding-left:150px; padding-right:150px; color: var(--header-meta)" v-if="notes.stats">
          源目录：运维笔记 ｜ 生成时间：{{ notes.raw.generated }}
        </div>
      </template>
    </AppHeader>

    <div class="flex gap-4 w-full pb-4 items-stretch flex-1 min-h-0" style="padding-left:150px; padding-right:150px">
      <!-- 移动端遮罩 -->
      <div
        v-if="sidebarOpen"
        @click="sidebarOpen = false"
        class="fixed inset-0 z-29"
        style="background: rgba(0,0,0,0.4)"
        :class="{ 'sm:hidden': true }"
      ></div>

      <!-- Sidebar wrapper（桌面端固定不动，侧边栏内部自滚动；移动端仍为抽屉 fixed） -->
      <div
        class="w-[264px] flex-none sticky top-0 self-start max-h-screen max-sm:fixed max-sm:left-0 max-sm:top-0 max-sm:bottom-0 max-sm:z-30 max-sm:rounded-none max-sm:w-[280px] max-sm:transition-transform max-sm:duration-300"
        :class="{ 'max-sm:hidden': !sidebarOpen }"
      >
        <Sidebar>
          <template #tree>
            <TreeView @select-cat="handleSelectCat" @navigate="handleNavigate" />
            <div class="px-1.5 pt-2">
              <Heatmap />
            </div>
          </template>
          <template #dashboard>
            <Dashboard />
          </template>
        </Sidebar>
      </div>

      <!-- Main（独立滚动容器：侧边栏固定不动，只有这里上下滚动） -->
      <main class="flex-1 min-w-0 flex flex-col gap-3 overflow-hidden">
        <!-- Stats：中性数字 + tabular-nums，颜色只保留语义（收藏=琥珀） -->
        <div class="grid grid-cols-4 max-sm:grid-cols-2 gap-3 flex-none" v-if="notes.stats">
          <div class="surface-card-xl p-3.5 stat-card">
            <div class="flex items-center gap-2 mb-1 text-muted">
              <AppIcon name="fileText" :size="14" />
              <span class="text-xs font-medium">Markdown 笔记</span>
            </div>
            <b class="block text-2xl font-extrabold num">{{ notes.stats.md || 0 }}</b>
          </div>
          <div class="surface-card-xl p-3.5 stat-card">
            <div class="flex items-center gap-2 mb-1 text-muted">
              <AppIcon name="paper" :size="14" />
              <span class="text-xs font-medium">PDF 参考资料</span>
            </div>
            <b class="block text-2xl font-extrabold num">{{ notes.stats.pdf || 0 }}</b>
          </div>
          <div class="surface-card-xl p-3.5 stat-card">
            <div class="flex items-center gap-2 mb-1 text-muted">
              <AppIcon name="hardDrive" :size="14" />
              <span class="text-xs font-medium">总体积</span>
            </div>
            <b class="block text-2xl font-extrabold num">{{ notes.stats.totalSize || 0 }}</b>
          </div>
          <div
            class="surface-card-xl p-3.5 stat-card cursor-pointer transition-all hover:translate-y-[-1px] hover:shadow-md"
            role="button"
            tabindex="0"
            title="点击查看收藏列表"
            @click="handleFavCardClick"
            @keydown.enter.prevent="handleFavCardClick"
            @keydown.space.prevent="handleFavCardClick"
          >
            <div class="flex items-center gap-2 mb-1" :style="{ color: 'var(--star)' }">
              <AppIcon name="star" :size="14" />
              <span class="text-xs font-medium">已收藏</span>
            </div>
            <b class="block text-2xl font-extrabold num count-up" :style="{ color: 'var(--star)' }">{{ userData.favs.size }}</b>
          </div>
        </div>

        <!-- Controls -->
        <div data-sticky-controls class="flex flex-col gap-2.5 flex-none" v-if="currentView === 'cards'" style="z-index: 6; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate)); -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate)); padding: 6px 0;">
          <div class="flex gap-2.5 items-center flex-wrap">
            <SearchBar ref="searchBarRef" @search="handleSearch" @open-note="handleCardClick" />
            <select
              v-model="sort"
              class="h-10 px-3 rounded-lg text-sm border-none cursor-pointer transition-shadow"
              :style="{
                background: 'var(--card)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
              }"
            >
              <option value="default">按分类</option>
              <option value="mtime">最近更新</option>
              <option value="hot">热门笔记</option>
            </select>
            <button
              @click="favOnly = !favOnly"
              :aria-pressed="favOnly"
              class="h-10 px-4 rounded-lg text-sm cursor-pointer transition-all inline-flex items-center gap-1.5"
              :style="favOnly ? { background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' } : { background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"
            ><AppIcon name="star" :size="14" /> 收藏</button>
          </div>
          <div class="surface-card-r p-3 flex flex-col gap-2.5">
            <div class="flex gap-2 items-start">
              <span class="flex-none text-xs font-medium pt-1 text-muted">分类</span>
              <div class="flex gap-1.5 flex-wrap flex-1 items-center">
                <button
                  v-for="c in catChips" :key="c.name"
                  @click="cat = cat === c.name ? null : c.name"
                  class="text-xs px-3 py-1.5 rounded-full cursor-pointer border transition-all hover:scale-[1.03]"
                  :class="cat === c.name ? 'text-white' : ''"
                  :style="cat === c.name
                    ? { background: 'var(--accent)', borderColor: 'var(--accent)' }
                    : { background: 'var(--card)', color: 'var(--text)', borderColor: 'var(--line)' }"
                >{{ c.name }} <span :class="cat === c.name ? 'opacity-80' : ''" :style="{ color: cat === c.name ? 'inherit' : 'var(--muted)' }">({{ c.count }})</span></button>
              </div>
            </div>
            <div class="flex gap-2 items-start" v-if="availableTags.visible.length">
              <span class="flex-none text-xs font-medium pt-1 text-muted">标签</span>
              <div class="flex gap-1.5 flex-wrap flex-1 items-center">
                <button
                  v-for="([t, c]) in availableTags.visible" :key="t"
                  @click="handleTagClick(t)"
                  class="text-xs px-2.5 py-1 rounded-full cursor-pointer transition-all"
                  :class="tags.has(t) ? 'text-white border-solid' : 'border-dashed'"
                  :style="tags.has(t)
                    ? { background: 'var(--accent2)', borderColor: 'var(--accent2)' }
                    : { background: 'transparent', color: 'var(--muted)', borderColor: 'var(--line)' }"
                >{{ t }} <i :style="tags.has(t) ? { opacity: 0.8 } : { opacity: 0.6 }">{{ c }}</i></button>
                <button
                  v-if="availableTags.all.length > 12"
                  @click="tagExpanded = !tagExpanded"
                  class="text-xs px-2.5 py-1 rounded-full cursor-pointer border-solid transition-all hover:scale-[1.03]"
                  :style="{ color: 'var(--accent)', borderColor: 'var(--accent)' }"
                >{{ tagExpanded ? '收起 ▴' : `更多 ${availableTags.all.length - 12} 个 ▾` }}</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Breadcrumb -->
        <Breadcrumb
          class="flex-none"
          v-if="currentView === 'cards'"
          :cat="cat"
          :tags="tags"
          :sort="sort"
          :fav-only="favOnly"
          :q="q"
          :result-count="filteredCount"
          @home="handleBreadcrumbHome"
          @cat-clear="handleBreadcrumbCatClear"
          @clear="handleBreadcrumbClear"
        />

        <div class="notes-scroll-window flex-1 min-h-0 overflow-y-auto pr-1">
        <!-- Content -->
        <div v-if="currentView === 'detail' && detailId">
          <DetailPanel
            :note="detailNote || notes.findNote(detailId)"
            :all-items="notes.items"
            :favs="userData.favs"
            :read-set="userData.readSet"
            :open-counts="userData.openCounts"
            :q="q"
            @close="handleCloseDetail"
            @star="handleStar"
            @toggle-read="handleToggleRead"
            @tag-click="handleTagClick"
            @open-note="handleOpenNote"
            @edit="handleEditInEditor"
          />
        </div>
        <CardList
          v-else
          :sort="sort"
          :cat="cat"
          :tags="tags"
          :fav-only="favOnly"
          :q="q"
          @card-click="handleCardClick"
          @tag-click="handleTagClick"
        />

        <footer class="text-center text-xs pt-4 pb-2 mt-4 flex items-center justify-center gap-2" :style="{ color: 'var(--muted)', borderTop: '1px solid var(--line)' }">
          <span>索引由 build_core.py 自动构建</span>
          <span class="opacity-50">·</span>
          <span>收藏/已读/热度数据保存在本机</span>
          <button
            @click="handleExport"
            class="text-xs px-2.5 py-1 rounded-md cursor-pointer ml-1 inline-flex items-center gap-1.5 transition-all"
            :style="{ border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--accent)' }"
          ><AppIcon name="download" :size="12" /> 导出数据</button>
        </footer>
        </div>
      </main>

      <!-- 右侧复习栏（PC 常驻，可收起） -->
      <aside
        v-if="reviewPanelOpen"
        class="w-[300px] flex-none sticky top-0 self-start max-h-screen flex flex-col"
      >
        <div
          class="rounded-xl border flex flex-col flex-1 min-h-0 overflow-hidden"
          :style="{ background: 'var(--card)', borderColor: 'var(--line)' }"
        >
          <div
            class="flex items-center justify-between px-3 py-2 flex-none"
            :style="{ borderBottom: '1px solid var(--line)' }"
          >
            <span class="text-xs font-semibold inline-flex items-center gap-1.5" :style="{ color: 'var(--text)' }">
              <AppIcon name="clock" :size="13" /> 复习
            </span>
            <button
              @click="reviewPanelOpen = false"
              class="text-xs cursor-pointer hover:opacity-70 transition-opacity"
              :style="{ color: 'var(--muted)' }"
              title="收起复习栏（点击底部按钮恢复）"
            >收起 ▸</button>
          </div>
          <div class="overflow-y-auto flex-1 min-h-0 p-2">
            <ReviewPanel />
          </div>
        </div>
      </aside>

      <!-- 复习栏收起后的恢复按钮（贴右边竖排） -->
      <button
        v-else
        @click="reviewPanelOpen = true"
        class="flex-none sticky top-0 self-start max-h-screen px-1.5 py-3 rounded-lg cursor-pointer transition-all hover:opacity-80"
        :style="{ background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--accent)' }"
        title="展开复习栏"
      >
        <span class="text-xs writing-vertical" style="writing-mode: vertical-rl; letter-spacing: 2px;">复习 ◂</span>
      </button>
    </div>

    <ScrollTop />
    <div v-if="navigationMessage" class="fixed top-5 left-1/2 -translate-x-1/2 z-[100] px-4 py-2.5 rounded-xl text-sm shadow-lg max-w-[calc(100vw-32px)] text-center"
      :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--accent)' }">
        <span class="mr-1.5" :style="{ color: 'var(--accent)' }">✓</span>{{ navigationMessage }}
    </div>
  </div>
</template>

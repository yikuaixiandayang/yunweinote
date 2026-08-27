<script setup>
/**
 * 全屏阅读页：从详情面板"全屏查看"进入（新标签打开 #/reader/:id）。
 * - 无侧栏/顶栏，正文占满整个窗口，右侧 sticky 章节大纲（点击滚动 + 随滚动高亮）
 * - 复用全局主题变量与 .preview-content 排版样式，跟随明暗/预设主题
 * - PDF 笔记用 iframe 全屏展示（浏览器原生 PDF 查看器）
 */
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { CAT_ICONS } from '../constants'
import { slugifyTitle, renderMarkdown } from '../utils/markdown.js'
import AppIcon from '../components/AppIcon.vue'

const route = useRoute()
const notes = useNotesStore()
const userData = useUserDataStore()

const noteId = computed(() => String(route.params.id || ''))
const note = computed(() => notes.findNote(noteId.value))

const previewLoading = ref(true)
const previewError = ref(null)
const mdText = ref('')
const safeHtml = computed(() => renderMarkdown(mdText.value))

const bodyRef = ref(null)            // 正文渲染容器
const activeHeading = ref(null)      // 当前阅读章节（大纲高亮）
let headingObserver = null

const pdfSrc = computed(() => {
  if (note.value?.type !== 'pdf') return ''
  return '/files/' + String(note.value.fileurl || '').replace(/^\.\//, '')
})

/** PDF 直接内嵌 iframe；Markdown 走渲染链路 */
watch(note, async (n) => {
  if (!n) return
  previewLoading.value = true
  previewError.value = null
  mdText.value = ''
  activeHeading.value = null
  teardownHeadingObserver()
  if (n.type === 'pdf') {
    previewLoading.value = false
    return
  }
  try {
    const text = await notes.getContent(n.id, n.fileurl)
    mdText.value = text
    previewLoading.value = false
    await nextTick()
    setupHeadingObserver()
  } catch (e) {
    previewLoading.value = false
    previewError.value = e.message
  }
}, { immediate: true })

onMounted(async () => {
  // 新标签页是全新 SPA：确保索引数据就绪后再取笔记（watch(note) 会在数据到达后自动加载正文）
  if (notes.loading) await notes.load()
  if (note.value) userData.markOpen(noteId.value)
})

/** 点击章节大纲 → 滚动定位 + 短暂高亮 */
function scrollToHeading(title) {
  const id = slugifyTitle(title)
  const el = bodyRef.value?.querySelector(`#${CSS.escape(id)}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeHeading.value = title
    el.classList.add('heading-flash')
    setTimeout(() => el.classList.remove('heading-flash'), 1600)
  }
}

/** 正文标题观察：随滚动高亮大纲中当前阅读章节 */
function setupHeadingObserver() {
  teardownHeadingObserver()
  if (!bodyRef.value || typeof IntersectionObserver === 'undefined') return
  const slugs = [...(note.value?.heads || [])].map(([, t]) => slugifyTitle(t))
  const headings = [...bodyRef.value.querySelectorAll('h1[id],h2[id],h3[id]')]
    .filter(h => slugs.includes(h.id))
    .slice(0, 6)
  if (!headings.length) return
  const visible = new Set()
  const elById = {}
  headings.forEach(h => { elById[h.id] = h })
  headingObserver = new IntersectionObserver(entries => {
    for (const en of entries) {
      if (en.isIntersecting) visible.add(en.target.id)
      else visible.delete(en.target.id)
    }
    if (!visible.size) return
    const first = headings.find(h => visible.has(h.id))
    if (first) activeHeading.value = note.value.heads.find(([, t]) => slugifyTitle(t) === first.id)?.[1] ?? null
  }, { rootMargin: '-10% 0px -60% 0px', threshold: 0 })
  headings.forEach(h => headingObserver.observe(h))
}

function teardownHeadingObserver() {
  if (headingObserver) {
    headingObserver.disconnect()
    headingObserver = null
  }
}

onBeforeUnmount(teardownHeadingObserver)

/** 打开 Obsidian 编辑（与详情面板同一入口逻辑） */
function editInObsidian() {
  const n = note.value
  if (!n) return
  const obsidian = notes.editors.obsidian || {}
  if (obsidian.installed && n.obsidianurl) {
    const a = document.createElement('a')
    a.href = n.obsidianurl
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }
}
</script>

<template>
  <div class="reader-page min-h-screen" style="background: var(--bg);">
    <!-- ══ 顶部工具条 ══ -->
    <header class="sticky top-0 z-20 border-b backdrop-blur-sm"
      :style="{ background: 'color-mix(in srgb, var(--card) 82%, transparent)', borderColor: 'var(--line)' }">
      <div class="flex items-center gap-2.5 px-4 py-2.5 max-w-[1400px] mx-auto w-full">
        <a href="#/"
          class="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-semibold rounded-lg no-underline cursor-pointer transition-all hover:opacity-80 shadow-sm flex-none"
          :style="{ background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--accent)' }">
          <AppIcon name="arrowLeft" :size="14" /> 返回列表
        </a>
        <div class="min-w-0 flex-1 flex items-center gap-2.5">
          <span v-if="note" class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full flex-none"
            :style="{ color: 'var(--accent)', background: 'var(--hover)' }">
            {{ CAT_ICONS[note.cat] || '' }} {{ note.cat }}
          </span>
          <h1 class="text-base font-bold truncate m-0" :style="{ color: 'var(--text)' }">{{ note?.name || '笔记不存在' }}</h1>
        </div>
        <a v-if="note" :href="note.fileurl ? '/files/' + note.fileurl.replace(/^\.\//, '') : '#'" target="_blank"
          class="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-semibold rounded-lg no-underline cursor-pointer transition-all hover:opacity-80 flex-none"
          :style="{ background: 'var(--card)', color: 'var(--muted)', border: '1px solid var(--line)' }">
          <AppIcon name="download" :size="13" /> 源文件
        </a>
        <button v-if="note && note.type === 'md'"
          @click="editInObsidian"
          class="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-semibold rounded-lg cursor-pointer transition-all hover:opacity-90 flex-none"
          :style="{ background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' }">
          <AppIcon name="edit" :size="13" /> 在 Obsidian 中打开
        </button>
      </div>
    </header>

    <!-- ══ 主体 ══ -->
    <main v-if="note" class="max-w-[1400px] mx-auto w-full px-4 py-5 grid gap-5 items-start max-lg:!block"
      style="grid-template-columns: minmax(0, 1fr) 272px;">

      <!-- 左栏：正文 -->
      <div class="min-w-0 flex flex-col gap-3">
        <!-- 窄屏折叠大纲 -->
        <details v-if="note.heads && note.heads.length" class="surface-card rounded-xl p-4 lg:hidden">
          <summary class="text-base font-bold list-none cursor-pointer flex items-center gap-2" :style="{ color: 'var(--text)' }">
            📑 章节大纲 ({{ note.heads.length }})
          </summary>
          <ul class="list-none p-0 m-0 mt-3" style="max-height: 320px; overflow-y: auto;">
            <li v-for="([lvl, t]) in note.heads" :key="t"
              class="py-1 text-sm cursor-pointer rounded-md transition-all hover:bg-[var(--hover)]"
              :style="{ paddingLeft: 8 + (lvl - 1) * 20 + 'px', borderLeft: activeHeading === t ? '3px solid var(--accent)' : '3px solid transparent' }"
              @click="scrollToHeading(t)">
              <span class="block truncate"
                :style="activeHeading === t
                  ? { color: 'var(--accent)', fontWeight: 600 }
                  : (lvl === 1 ? { color: 'var(--text)', fontWeight: 600 } : { color: 'var(--muted)' })">{{ t }}</span>
            </li>
          </ul>
        </details>

        <div class="surface-card rounded-xl p-4 sm:p-8">
          <!-- PDF：全屏内嵌 -->
          <div v-if="note.type === 'pdf'" class="rounded-lg overflow-hidden" style="border: 1px solid var(--line);">
            <iframe :src="pdfSrc" class="w-full" style="height: calc(100vh - 190px); border: none; background: #fff;"></iframe>
          </div>
          <!-- Markdown：渲染正文 -->
          <template v-else>
            <div v-if="previewLoading" class="text-center py-12 flex flex-col items-center gap-2" :style="{ color: 'var(--muted)' }">
              <div class="loading-spinner-sm"></div>
              <span>正在加载内容…</span>
            </div>
            <div v-else-if="previewError" class="text-center py-12" :style="{ color: '#ef4444' }">⚠️ 加载失败：{{ previewError }}</div>
            <div v-else ref="bodyRef" class="preview-content typora-body" v-html="safeHtml"></div>
          </template>
        </div>
      </div>

      <!-- 右栏：章节大纲（桌面端 sticky 固定） -->
      <aside v-if="note.heads && note.heads.length" class="hidden lg:block sticky top-0 self-start">
        <div class="surface-card rounded-xl p-4 flex flex-col" style="max-height: calc(100vh - 90px);">
          <h3 class="text-base font-bold m-0 pb-2 mb-3 flex items-center gap-2 flex-none"
            :style="{ borderBottom: '1px solid var(--line)' }">📑 章节大纲 ({{ note.heads.length }})</h3>
          <ul class="list-none p-0 m-0 overflow-y-auto" style="min-height: 0;">
            <li v-for="([lvl, t]) in note.heads" :key="t"
              class="py-1 text-sm cursor-pointer rounded-md transition-all hover:bg-[var(--hover)]"
              :style="{ paddingLeft: 8 + (lvl - 1) * 20 + 'px', borderLeft: activeHeading === t ? '3px solid var(--accent)' : '3px solid transparent' }"
              @click="scrollToHeading(t)">
              <span class="block truncate"
                :style="activeHeading === t
                  ? { color: 'var(--accent)', fontWeight: 600 }
                  : (lvl === 1 ? { color: 'var(--text)', fontWeight: 600 } : { color: 'var(--muted)' })">{{ t }}</span>
            </li>
          </ul>
        </div>
      </aside>
    </main>

    <!-- 笔记不存在 -->
    <main v-else class="max-w-[1400px] mx-auto w-full px-4 py-20 text-center" :style="{ color: 'var(--muted)' }">
      <div class="text-4xl mb-3">🤔</div>
      <p class="text-lg mb-4">未找到该笔记（id: {{ noteId }}），可能索引已更新。</p>
      <a href="#/" class="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg text-sm font-semibold no-underline cursor-pointer transition-all hover:opacity-80"
        :style="{ background: 'var(--accent)', color: '#fff' }">← 返回列表</a>
    </main>
  </div>
</template>

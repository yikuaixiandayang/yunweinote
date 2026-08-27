<script setup>
import AppIcon from './AppIcon.vue'
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { CAT_ICONS } from '../constants'
import { slugifyTitle, renderMarkdown } from '../utils/markdown.js'

// 渲染链路（标题锚点 id 注入 + 安全过滤）与全屏阅读页共用 utils/markdown.js
const props = defineProps({
  note: Object,
  allItems: Array,
  favs: Set,
  readSet: Set,
  openCounts: Object,
  q: String,
})

const emit = defineEmits(['close', 'star', 'toggle-read', 'tag-click', 'open-note', 'open-file', 'edit'])

const notes = useNotesStore()

/** 编辑按钮文案：外部编辑器已统一为 Obsidian（Typora 已弃用） */
const editBtnLabel = computed(() => '在 Obsidian 中打开')

const icon = computed(() => props.note?.cat ? (CAT_ICONS[props.note.cat] || '') : '')

const previewContent = ref('')
const previewLoading = ref(true)
const previewError = ref(null)
const linksExpanded = ref(false)   // 标签关联默认折叠，只显示前 8 个
const safePreviewHtml = computed(() => renderMarkdown(previewContent.value || ''))
const bodyRef = ref(null)          // 正文渲染容器
const activeHeading = ref(null)    // 当前正在阅读的章节标题（大纲高亮）
let headingObserver = null         // 章节高亮观察器

watch(() => props.note, async (n) => {
  if (!n) return
  previewLoading.value = true
  previewError.value = null
  previewContent.value = ''
  activeHeading.value = null
  teardownHeadingObserver()
  if (n.type === 'pdf') {
    previewLoading.value = false
    previewContent.value = '<p>PDF文件暂不支持内嵌预览</p>'
    return
  }
  try {
    const text = await notes.getContent(n.id, n.fileurl)
    previewLoading.value = false
    previewContent.value = text
    // 正文渲染完成后建立标题观察，供大纲高亮当前阅读章节
    await nextTick()
    setupHeadingObserver()
  } catch (e) {
    previewLoading.value = false
    previewError.value = e.message
  }
}, { immediate: true })

const noteLinks = computed(() => {
  if (!props.note) return []
  const rels = []
  for (const item of props.allItems || []) {
    if (item.id === props.note.id) continue
    if (item.cat === props.note.cat) continue
    const shared = (props.note.tags || []).filter(t => (item.tags || []).includes(t))
    if (shared.length) {
      rels.push({ note: item, shared })
    }
  }
  return rels
})

function findItem(id) {
  return (props.allItems || []).find(i => i.id === id)
}

/**
 * 点击章节大纲 → 滚动定位到对应标题并短暂高亮。
 */
function scrollToHeading(title) {
  const id = slugifyTitle(title)
  const el = bodyRef.value?.querySelector(`#${CSS.escape(id)}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeHeading.value = title
    // 短暂的黄色高亮提示当前章节位置
    el.classList.add('heading-flash')
    setTimeout(() => el.classList.remove('heading-flash'), 1600)
  }
}

/**
 * 正文标题观察：随页面滚动高亮大纲中当前阅读的章节。
 * 用 IntersectionObserver 记录进入可视区最靠上的标题。
 */
function setupHeadingObserver() {
  teardownHeadingObserver()
  if (!bodyRef.value || typeof IntersectionObserver === 'undefined') return
  const slugs = [...(props.note?.heads || [])].map(([, t]) => slugifyTitle(t))
  const headings = [...bodyRef.value.querySelectorAll('h1[id],h2[id],h3[id]')]
    .filter(h => slugs.includes(h.id))
    .slice(0, 6) // 只观察前几个章节，避免海量观察器
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
    // 取可视区中最靠上（第一个进入）的标题作为当前章节
    const first = headings.find(h => visible.has(h.id))
    if (first) activeHeading.value = props.note.heads.find(([, t]) => slugifyTitle(t) === first.id)?.[1] ?? null
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
</script>

<template>
  <div v-if="note" class="mt-3 grid gap-5 items-start max-lg:!block" style="grid-template-columns: minmax(0, 1fr) 272px;">
    <!-- ══ 左栏：主阅读内容（元信息 + 正文 + 关联）══ -->
    <div class="min-w-0 flex flex-col gap-3">
      <button
        @click="emit('close')"
        class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg sticky top-2 z-10 cursor-pointer transition-all hover:opacity-80 shadow-sm self-start"
        :style="{
          background: 'var(--card)',
          border: '1px solid var(--line)',
          color: 'var(--accent)'
        }"
      >← 返回列表</button>

    <div
      class="surface-card rounded-2xl p-6 mt-3 relative overflow-hidden"
    >
      <div
        class="absolute top-0 left-0 right-0 h-1"
        style="background: linear-gradient(90deg, var(--accent), var(--accent2))"
      ></div>
      <span
        class="inline-flex items-center gap-1.5 text-sm font-semibold px-3.5 py-1 rounded-full"
        :style="{ color: 'var(--accent)', background: 'var(--hover)' }"
      >{{ icon }} {{ note.cat }}</span>
      <h1 class="text-2xl font-extrabold my-2.5 break-all leading-tight" :style="{ color: 'var(--text)' }">{{ note.name }}</h1>
      <div
        class="flex flex-wrap gap-x-4 gap-y-1.5 text-sm mt-3 pt-3"
        :style="{ color: 'var(--muted)', borderTop: '1px solid var(--line)' }"
      >
        <span class="inline-flex items-center gap-1">📦 {{ note.size }}</span>
        <span v-if="note.lines" class="inline-flex items-center gap-1">📝 约{{ note.lines }}行</span>
        <span class="inline-flex items-center gap-1">🕐 {{ note.mtime }}</span>
        <span class="inline-flex items-center gap-1">🔗 {{ noteLinks.length }}个标签关联</span>
        <span class="inline-flex items-center gap-1">🔁 {{ (note.wikilinks || []).length }}个双向引用</span>
        <span v-if="note.stub" class="inline-flex items-center gap-1">⚠️ 占位/待补</span>
      </div>
      <div v-if="note.tags && note.tags.length" class="flex flex-wrap gap-2 mt-3.5">
        <button
          v-for="t in note.tags" :key="t"
          @click="emit('tag-click', t)"
          class="text-xs px-2.5 py-1 rounded-full cursor-pointer border border-dashed transition-all hover:opacity-80"
          :style="{ color: 'var(--muted)', borderColor: 'var(--line)' }"
        >{{ t }}</button>
      </div>
      <div class="flex flex-wrap gap-2.5 mt-4">
        <button
          @click="emit('edit', note.id)"
          class="px-5 py-2.5 rounded-lg text-sm font-semibold cursor-pointer transition-all inline-flex items-center gap-1.5 hover:opacity-90"
          :style="{ background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' }"
        ><AppIcon name="edit" :size="13" /> {{ editBtnLabel }}</button>
        <!-- 全屏查看：md 笔记 → #/reader/{id} 全屏阅读页（保留章节大纲）；pdf → 新标签打开原始文件 -->
        <a
          v-if="note.type === 'md'"
          :href="'#/reader/' + note.id" target="_blank"
          aria-label="在新标签页全屏查看"
          class="px-5 py-2.5 rounded-lg text-sm font-semibold no-underline cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
          :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"
        ><AppIcon name="fullscreen" :size="13" /> 全屏查看</a>
        <a
          v-else
          :href="note.fileurl ? '/files/' + note.fileurl.replace(/^\.\//, '') : '#'" target="_blank"
          aria-label="在新标签页查看 PDF"
          class="px-5 py-2.5 rounded-lg text-sm font-semibold no-underline cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
          :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"
        ><AppIcon name="externalLink" :size="13" /> 全屏查看</a>
        <button
          @click="emit('star', note.id)"
          :aria-label="favs.has(note.id) ? '取消收藏' : '收藏'"
          class="px-5 py-2.5 rounded-lg text-sm font-semibold cursor-pointer transition-all inline-flex items-center gap-1.5"
          :style="favs.has(note.id)
            ? { background: '#fef3c7', color: '#92400e', border: '1px solid #f59e0b' }
            : { background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"
        ><AppIcon name="star" :size="13" :fill="favs.has(note.id) ? 'currentColor' : 'none'" /> {{ favs.has(note.id) ? '已收藏' : '收藏' }}</button>
        <button
          @click="emit('toggle-read', note.id)"
          :aria-label="readSet.has(note.id) ? '取消已读' : '标记已读'"
          class="px-5 py-2.5 rounded-lg text-sm font-semibold cursor-pointer transition-all inline-flex items-center gap-1.5"
          :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"
        >{{ readSet.has(note.id) ? '✓ 已读' : '○ 标记已读' }}</button>
      </div>
    </div>

    <!-- 窄屏（<1024px）折叠大纲；桌面端大纲在右侧固定栏 -->
    <details v-if="note.heads && note.heads.length" class="surface-card rounded-xl p-4 lg:hidden">
      <summary class="text-base font-bold list-none cursor-pointer flex items-center gap-2" :style="{ color: 'var(--text)' }">
        📑 章节大纲 ({{ note.heads.length }})
      </summary>
      <ul class="list-none p-0 m-0 mt-3" style="max-height: 320px; overflow-y: auto;">
        <li
          v-for="([lvl, t]) in note.heads" :key="t"
          class="py-1 text-sm cursor-pointer rounded-md transition-all hover:bg-[var(--hover)]"
          :style="{ paddingLeft: 8 + (lvl - 1) * 20 + 'px', borderLeft: activeHeading === t ? '3px solid var(--accent)' : '3px solid transparent' }"
          @click="scrollToHeading(t)"
        >
          <span
            class="block truncate"
            :style="activeHeading === t
              ? { color: 'var(--accent)', fontWeight: 600 }
              : (lvl === 1 ? { color: 'var(--text)', fontWeight: 600 } : { color: 'var(--muted)' })"
          >{{ t }}</span>
        </li>
      </ul>
    </details>

    <div class="surface-card rounded-xl p-4 sm:p-7 mt-3">
      <div ref="bodyRef">
        <div v-if="previewLoading" class="text-center py-12 flex flex-col items-center gap-2" :style="{ color: 'var(--muted)' }">
          <div class="loading-spinner-sm"></div>
          <span>正在加载内容…</span>
        </div>
        <div v-else-if="previewError" class="text-center py-12" :style="{ color: '#ef4444' }">⚠️ 加载失败：{{ previewError }}</div>
        <div v-else class="preview-content typora-body" v-html="safePreviewHtml"></div>
      </div>
    </div>

    <div class="surface-card rounded-xl p-4 mt-3">
      <h3 class="text-base font-bold m-0 pb-2 mb-3 flex items-center gap-2" :style="{ borderBottom: '1px solid var(--line)' }">
        🔗 标签关联
        <span class="text-xs font-normal rounded-full px-2 py-0.5" :style="{ background: 'var(--accent)', color: '#fff' }">{{ noteLinks.length }}</span>
        <button v-if="noteLinks.length > 8" @click.stop="linksExpanded = !linksExpanded" class="ml-auto text-xs font-normal cursor-pointer hover:underline" :style="{ color: 'var(--accent)' }">{{ linksExpanded ? '收起' : `展开全部 ${noteLinks.length}` }}</button>
      </h3>
      <div v-if="noteLinks.length" class="flex flex-wrap gap-1.5">
        <span
          v-for="r in (linksExpanded ? noteLinks : noteLinks.slice(0, 8))" :key="r.note.id"
          @click="emit('open-note', r.note.id)"
          class="inline-block cursor-pointer rounded-lg px-2.5 py-1.5 transition-all duration-200 hover:scale-105 hover:shadow-sm"
          :style="{ background: 'var(--hover)', border: '1px solid var(--line)' }"
        >
          <span class="text-xs font-medium" :style="{ color: 'var(--text)' }">{{ r.note.name.replace(/\.md$/, '') }}</span>
          <span class="text-[10px] ml-1" :style="{ color: 'var(--accent2)' }">{{ r.shared.length }}共</span>
        </span>
      </div>
      <div v-else class="text-sm" :style="{ color: 'var(--muted)' }">暂无标签关联</div>
    </div>

    <div class="surface-card rounded-xl p-4 mt-3">
      <h3 class="text-base font-bold m-0 pb-2 mb-3 flex items-center gap-2" :style="{ borderBottom: '1px solid var(--line)' }">🔁 双向引用 ({{ (note.wikilinks || []).length }})</h3>
      <div v-if="note.wikilinks && note.wikilinks.length" class="grid gap-2.5" style="grid-template-columns: repeat(auto-fill, minmax(260px, 1fr))">
        <div v-for="wid in note.wikilinks" :key="wid" @click="emit('open-note', wid)" class="rounded-xl p-3 cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow" :style="{ background: 'var(--hover)', border: '1px solid var(--line)' }">
          <div class="text-sm font-semibold" :style="{ color: 'var(--accent)' }">{{ (findItem(wid)?.name || wid).replace(/\.md$/, '') }}</div>
          <div class="text-xs mt-1" :style="{ color: 'var(--muted)' }">{{ CAT_ICONS[findItem(wid)?.cat] || '' }} {{ findItem(wid)?.cat }}</div>
        </div>
      </div>
      <div v-else class="text-sm" :style="{ color: 'var(--muted)' }">该笔记暂无双向引用</div>
    </div>
    </div><!-- /左栏 -->

    <!-- ══ 右栏：章节大纲（桌面端 sticky 固定不动，随正文滚动高亮）══ -->
    <aside v-if="note.heads && note.heads.length" class="hidden lg:block sticky top-0 self-start max-h-screen">
      <div class="surface-card rounded-xl p-4 flex flex-col" style="max-height: calc(100vh - 8px);">
        <h3 class="text-base font-bold m-0 pb-2 mb-3 flex items-center gap-2 flex-none" :style="{ borderBottom: '1px solid var(--line)' }">📑 章节大纲 ({{ note.heads.length }})</h3>
        <ul class="list-none p-0 m-0 overflow-y-auto" style="min-height: 0;">
          <li
            v-for="([lvl, t]) in note.heads" :key="t"
            class="py-1 text-sm cursor-pointer rounded-md transition-all hover:bg-[var(--hover)]"
            :style="{ paddingLeft: 8 + (lvl - 1) * 20 + 'px', borderLeft: activeHeading === t ? '3px solid var(--accent)' : '3px solid transparent' }"
            @click="scrollToHeading(t)"
          >
            <span
              class="block truncate"
              :style="activeHeading === t
                ? { color: 'var(--accent)', fontWeight: 600 }
                : (lvl === 1 ? { color: 'var(--text)', fontWeight: 600 } : { color: 'var(--muted)' })"
            >{{ t }}</span>
          </li>
        </ul>
      </div>
    </aside>
  </div>
</template>

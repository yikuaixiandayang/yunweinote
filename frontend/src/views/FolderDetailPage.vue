<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import AppIcon from '../components/AppIcon.vue'
import { getFolderTree, getFolderFile, getFolderReadme, getFolderAssetUrl, getFolderDownloadUrl, agentDescribe, getCachedDescribe, saveFolderFileNote, deleteFolderFileNote } from '../api/index.js'
import { sanitizeHtml } from '../utils/safeHtml.js'

const route = useRoute()
const router = useRouter()
const folderName = computed(() => decodeURIComponent(route.params.name || ''))

const tree = ref(null)
const loading = ref(true)
const error = ref('')
const readme = ref(null)
const preview = ref(null)     // {name, content, isText, ext, truncated}
const previewLoading = ref(false)
const selectedDir = ref(null) // 当前选中的子目录（支持查看/编辑备注）
const expanded = ref(new Set())  // 展开的目录 rel 集合

// 备注编辑状态（预览栏内联编辑）
const noteEditing = ref(false)
const noteDraft = ref('')
const noteSaving = ref(false)

// 展开/收起目录
function toggleDir(rel) {
  if (expanded.value.has(rel)) expanded.value.delete(rel)
  else expanded.value.add(rel)
}

function isExpanded(rel) {
  return expanded.value.has(rel)
}

// 递归渲染目录树 → 扁平列表（仅已展开的）
function flatten(items, depth = 0, out = []) {
  if (!items) return out
  for (const it of items) {
    out.push({ ...it, depth })
    if (it.kind === 'dir' && isExpanded(it.rel)) {
      flatten(it.children, depth + 1, out)
    }
  }
  return out
}

const flatItems = computed(() => flatten(tree.value ? tree.value.items : []))
const previewUrl = computed(() => preview.value?.rel ? getFolderAssetUrl(folderName.value, preview.value.rel) : '')
const isImagePreview = computed(() => Boolean(preview.value && ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp'].includes(preview.value.ext)))
const isPdfPreview = computed(() => preview.value?.ext === '.pdf')
const isMarkdownPreview = computed(() => preview.value?.ext === '.md')
const markdownPreview = computed(() => sanitizeHtml(marked.parse(preview.value?.content || '')))
// README 摘要区也按 markdown 渲染（全文，区域内滚动，不再截断 800 字）
const readmeHtml = computed(() => readme.value?.exists ? sanitizeHtml(marked.parse(readme.value.content || '')) : '')

// 打开文件预览
async function openFile(item) {
  previewLoading.value = true
  preview.value = null
  selectedDir.value = null
  aiDoc.value = null
  aiLoading.value = false
  noteEditing.value = false
  noteDraft.value = ''
  try {
    const data = await getFolderFile(folderName.value, item.rel)
    // 保留树里附带的 note 字段（后端 /tree 已注入；详情接口未注入则回退用树节点的）
    if (!('note' in data)) data.note = item.note || ''
    preview.value = data
    // 回显已缓存的 AI 解读（GET 只读缓存，不会触发 LLM 调用）
    loadCachedDoc(item.rel)
  } catch (e) {
    preview.value = { name: item.name, isText: false, content: '', error: e.message, rel: item.rel, note: item.note || '' }
  } finally {
    previewLoading.value = false
  }
}

// 只读缓存的 AI 解读回显（无任何 LLM 调用）
async function loadCachedDoc(rel) {
  try {
    const p = await getCachedDescribe(`${folderName.value}/${rel}`, 'folderfile')
    if (p.cached && p.doc && !p.doc.error && preview.value?.rel === rel) {
      aiDoc.value = p.doc
    }
  } catch { /* 无缓存则静默 */ }
}

// 选中子目录：展开/收起 + 右侧展示目录详情（备注编辑）
function selectDir(item) {
  toggleDir(item.rel)
  preview.value = null
  aiDoc.value = null
  noteEditing.value = false
  noteDraft.value = ''
  selectedDir.value = item
}

function closeDir() {
  selectedDir.value = null
}

// AI 解读当前预览的文件（后端缓存，同一文件只调一次 LLM）
const aiDoc = ref(null)
const aiLoading = ref(false)

// 复制状态
const copySuccess = ref(false)
let copyTimer = null
async function runDescribe() {
  if (!preview.value || aiLoading.value) return
  aiLoading.value = true
  aiDoc.value = null
  try {
    const path = `${folderName.value}/${preview.value.rel}`
    aiDoc.value = await agentDescribe(path, 'folderfile')
  } catch (e) {
    aiDoc.value = { error: e.message }
  } finally {
    aiLoading.value = false
  }
}

function closePreview() {
  preview.value = null
}

// 复制当前预览的文本内容
async function copyContent() {
  if (!preview.value?.content) return
  try {
    await navigator.clipboard.writeText(preview.value.content)
  } catch {
    // fallback for non-HTTPS contexts
    const ta = document.createElement('textarea')
    ta.value = preview.value.content
    ta.style.cssText = 'position:fixed;left:-9999px'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  copySuccess.value = true
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copySuccess.value = false }, 2000)
}

// 下载当前预览的文件（后端 attachment 端点，任意类型都可下载）
function downloadFile() {
  if (!preview.value?.rel) return
  const a = document.createElement('a')
  a.href = getFolderDownloadUrl(folderName.value, preview.value.rel)
  a.download = preview.value.name
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// ── 自定义备注（文件预览 / 子目录面板共用） ──
const noteTarget = computed(() => preview.value || selectedDir.value)

function startEditNote() {
  noteDraft.value = noteTarget.value?.note || ''
  noteEditing.value = true
}

function cancelEditNote() {
  noteEditing.value = false
  noteDraft.value = ''
}

// 在树中找到对应 rel 的节点（递归），用于保存后同步更新树展示
function _findTreeNode(items, rel) {
  if (!items) return null
  for (const it of items) {
    if (it.rel === rel) return it
    if (it.kind === 'dir' && it.children) {
      const r = _findTreeNode(it.children, rel)
      if (r) return r
    }
  }
  return null
}

async function saveNote() {
  const target = noteTarget.value
  if (noteSaving.value || !target?.rel) return
  const text = noteDraft.value.trim()
  if (text.length > 2000) {
    alert('备注过长，请控制在 2000 字以内')
    return
  }
  noteSaving.value = true
  try {
    const r = text
      ? await saveFolderFileNote(folderName.value, target.rel, text)
      : await deleteFolderFileNote(folderName.value, target.rel)
    if (r && r.error) {
      alert('保存备注失败: ' + r.error)
      return
    }
    target.note = text
    // 同步更新树中对应节点
    const node = _findTreeNode(tree.value?.items, target.rel)
    if (node) node.note = text
    noteEditing.value = false
    noteDraft.value = ''
  } catch (e) {
    alert('保存备注失败: ' + e.message)
  } finally {
    noteSaving.value = false
  }
}

// 文件/目录图标（自制 SVG 图标名）
const extIcons = {
  '.md': 'fileText', '.txt': 'paper', '.py': 'fileText', '.sh': 'terminal', '.ps1': 'terminal', '.bat': 'terminal',
  '.js': 'fileText', '.ts': 'fileText', '.vue': 'fileText', '.json': 'paper', '.yml': 'settings', '.yaml': 'settings',
  '.conf': 'settings', '.html': 'paper', '.css': 'paper', '.sql': 'database', '.pdf': 'paper', '.svg': 'paper',
  '.png': 'paper', '.jpg': 'paper', '.jpeg': 'paper',
}

function iconOf(it) {
  if (it.kind === 'dir') return 'folder'
  if (it.kind === 'more') return 'chevronDown'
  return extIcons[it.ext] || 'paper'
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function load() {
  loading.value = true
  error.value = ''
  preview.value = null
  selectedDir.value = null
  try {
    const [treeData, readmeData] = await Promise.all([
      getFolderTree(folderName.value),
      getFolderReadme(folderName.value),
    ])
    tree.value = treeData
    readme.value = readmeData
    // 默认展开第一层目录
    expanded.value = new Set()
    treeData.items.forEach(it => { if (it.kind === 'dir') expanded.value.add(it.rel) })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(folderName, load)
</script>

<template>
  <div class="min-h-screen pb-10" :style="{ background: 'var(--bg)' }">
    <AppHeader :title="folderName">
      <button
        @click="router.push('/folders')"
        class="surface-card px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
        :style="{ color: 'var(--accent)' }"
      ><AppIcon name="folderOpen" :size="13" /> 全部文件夹</button>
      <span class="badge-pill">{{ tree ? tree.items.length : 0 }} 个顶层条目</span>
      <button
        @click="load"
        class="surface-card ml-auto px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
        :style="{ color: 'var(--accent)' }"
      ><AppIcon name="refresh" :size="12" /> 刷新</button>
    </AppHeader>
    <div class="p-6 max-w-[1200px] mx-auto">

      <!-- 加载中 / 错误 -->
      <div v-if="loading" class="text-center py-16" :style="{ color: 'var(--muted)' }">加载中...</div>
      <div v-else-if="error" class="text-center py-16" :style="{ color: 'var(--danger)' }">{{ error }}</div>

    <div v-else class="flex flex-col lg:flex-row gap-4 items-stretch lg:items-start">
        <!-- 左：目录树 -->
        <div class="flex-1 min-w-0">
          <!-- README 渲染（markdown，全文，区域内滚动） -->
          <div
            v-if="readme && readme.exists"
            class="surface-card rounded-xl p-4 mb-4 max-h-[60vh] overflow-y-auto preview-content"
          >
            <div class="text-xs font-semibold mb-2" :style="{ color: 'var(--muted)' }">README</div>
            <div class="text-sm leading-relaxed" v-html="readmeHtml"></div>
          </div>

          <!-- 内容树 -->
          <div class="rounded-xl overflow-hidden" :style="{ border: '1px solid var(--line)' }">
            <div class="px-4 py-2 text-xs font-semibold" :style="{ background: 'var(--bg-subtle)', borderBottom: '1px solid var(--line)', color: 'var(--muted)' }">
              内容结构
            </div>
            <div class="p-2" :style="{ background: 'var(--card)' }">
              <div v-if="flatItems.length === 0" class="text-center py-8 text-sm" :style="{ color: 'var(--muted)' }">
                此文件夹为空或无可展示内容
              </div>
              <div
                v-for="it in flatItems"
                :key="it.rel + it.kind"
                class="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:opacity-80"
                :style="{ paddingLeft: `${it.depth * 20 + 8}px` }"
                @click="it.kind === 'dir' ? selectDir(it) : openFile(it)"
              >
                <span class="flex-none inline-flex" :style="{ color: it.kind === 'dir' ? 'var(--accent)' : 'var(--muted)' }"><AppIcon :name="iconOf(it)" :size="14" /></span>
                <span class="text-sm truncate" :style="{ color: it.kind === 'dir' ? 'var(--text)' : 'var(--text-secondary)' }">
                  {{ it.name }}
                </span>
                <span v-if="it.note" class="inline-flex items-center shrink-0" :style="{ color: 'var(--accent2)' }" :title="it.note">
                  <AppIcon name="stickyNote" :size="11" />
                </span>
                <span v-if="it.note" class="text-xs truncate hidden md:inline" style="max-width: 38%" :style="{ color: 'var(--muted)' }" :title="it.note">
                  {{ it.note }}
                </span>
                <span v-if="it.kind === 'file'" class="text-xs ml-auto flex-none" :style="{ color: 'var(--muted)' }">
                  {{ it.size }}
                </span>
                <span v-if="it.kind === 'dir'" class="text-xs ml-auto flex-none" :style="{ color: 'var(--muted)' }">
                  {{ isExpanded(it.rel) ? '▾' : '▸' }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 右：文件预览 -->
        <div class="w-full lg:w-[420px] lg:flex-none" v-if="preview">
          <div class="rounded-xl overflow-hidden" :style="{ border: '1px solid var(--line)' }">
            <div class="px-4 py-2 text-xs font-semibold flex items-center gap-2" :style="{ background: 'var(--bg-subtle)', borderBottom: '1px solid var(--line)', color: 'var(--muted)' }">
              <span class="truncate flex-1">{{ preview.name }}</span>
              <button
                v-if="preview.isText"
                @click="copyContent"
                class="flex-none px-2 py-1 rounded-md cursor-pointer text-xs inline-flex items-center gap-1 font-semibold transition-all"
                :style="{ background: copySuccess ? 'var(--accent)' : 'var(--hover)', color: copySuccess ? '#fff' : 'var(--accent)', border: '1px solid var(--line)' }"
                title="复制文件内容"
              ><AppIcon :name="copySuccess ? 'check' : 'copy'" :size="11" /> {{ copySuccess ? '已复制' : '复制' }}</button>
              <button
                @click="downloadFile"
                class="flex-none px-2 py-1 rounded-md cursor-pointer text-xs inline-flex items-center gap-1 font-semibold transition-all"
                :style="{ background: 'var(--hover)', color: 'var(--accent)', border: '1px solid var(--line)' }"
                title="下载文件"
              ><AppIcon name="download" :size="11" /> 下载</button>
              <button
                v-if="preview.isText"
                @click="runDescribe"
                :disabled="aiLoading"
                class="flex-none px-2 py-1 rounded-md cursor-pointer text-xs inline-flex items-center gap-1 font-semibold transition-all"
                :style="{ background: aiLoading ? 'var(--hover)' : 'var(--accent)', color: aiLoading ? 'var(--muted)' : '#fff', border: 'none' }"
                title="AI 解读这个文件：用途 / 用法 / 工作过程"
              ><AppIcon name="zap" :size="11" /> {{ aiLoading ? '解读中…' : 'AI 解读' }}</button>
              <button @click="closePreview" class="flex-none cursor-pointer hover:opacity-80 inline-flex items-center gap-1" :style="{ color: 'var(--accent)' }"><AppIcon name="x" :size="11" /> 关闭</button>
            </div>

            <!-- AI 解读结果 -->
            <div v-if="aiLoading" class="px-4 py-3 text-sm" :style="{ background: 'var(--hover)', color: 'var(--muted)' }">
              ⏳ AI 正在阅读文件（首次约 10-30 秒，之后走缓存）…
            </div>
            <div v-else-if="aiDoc" class="px-4 py-3" :style="{ background: 'color-mix(in srgb, var(--accent) 5%, var(--card))', borderBottom: '1px solid var(--line)' }">
              <div v-if="aiDoc.error" class="text-sm" :style="{ color: 'var(--danger)' }">{{ aiDoc.error }}</div>
              <template v-else>
                <div class="text-xs font-bold uppercase tracking-wider mb-1.5 inline-flex items-center gap-1.5" :style="{ color: 'var(--accent)' }">
                  <AppIcon name="zap" :size="11" /> AI 解读
                </div>
                <div class="text-sm mb-1.5" :style="{ color: 'var(--text)' }"><b>用途：</b>{{ aiDoc.purpose }}</div>
                <div class="text-sm mb-1.5 whitespace-pre-wrap" :style="{ color: 'var(--text)' }" v-if="aiDoc.usage"><b>用法：</b>{{ aiDoc.usage }}</div>
                <div class="text-sm mb-1.5" v-if="aiDoc.workflow?.length">
                  <b :style="{ color: 'var(--text)' }">工作过程：</b>
                  <ol class="m-0 mt-1 pl-5 text-sm space-y-0.5" :style="{ color: 'var(--text-secondary)' }">
                    <li v-for="(step, i) in aiDoc.workflow" :key="i">{{ step }}</li>
                  </ol>
                </div>
                <div class="text-sm" :style="{ color: 'var(--text-secondary)' }" v-if="aiDoc.notes"><b>注意：</b>{{ aiDoc.notes }}</div>
              </template>
            </div>

            <!-- 自定义备注 -->
            <div v-if="noteEditing" class="px-4 py-3" :style="{ borderBottom: '1px solid var(--line)' }">
              <textarea
                v-model="noteDraft"
                rows="3"
                maxlength="2000"
                placeholder="写点备注，比如这个文件的用途、注意事项…"
                class="w-full p-2 rounded-lg outline-none text-sm resize-y"
                :style="{ background: 'var(--bg-subtle)', color: 'var(--text)', border: '1px solid var(--line)' }"
              ></textarea>
              <div class="flex gap-2 mt-2 justify-end">
                <button
                  @click="cancelEditNote"
                  class="px-2.5 py-1 text-xs rounded cursor-pointer"
                  :style="{ background: 'var(--hover)', color: 'var(--muted)' }"
                >取消</button>
                <button
                  @click="saveNote"
                  :disabled="noteSaving"
                  class="px-2.5 py-1 text-xs font-semibold rounded cursor-pointer"
                  :style="{ background: 'var(--accent)', color: '#fff', opacity: noteSaving ? 0.6 : 1 }"
                >{{ noteSaving ? '保存中…' : '保存' }}</button>
              </div>
            </div>
            <div v-else class="px-4 py-2.5 flex items-start gap-1.5" :style="{ borderBottom: '1px solid var(--line)' }">
              <span class="inline-flex mt-0.5 shrink-0" :style="{ color: preview.note ? 'var(--accent2)' : 'var(--muted)' }"><AppIcon name="stickyNote" :size="12" /></span>
              <span class="text-xs font-semibold shrink-0" :style="{ color: 'var(--muted)' }">用户备注</span>
              <span v-if="preview.note" class="text-xs whitespace-pre-wrap flex-1" :style="{ color: 'var(--text-secondary)' }">{{ preview.note }}</span>
              <span v-else class="text-xs italic flex-1" :style="{ color: 'var(--muted)' }">添加备注，说明这个文件的作用…</span>
              <button
                @click="startEditNote"
                class="text-xs px-1.5 py-0.5 rounded cursor-pointer shrink-0"
                :style="{ color: 'var(--accent)' }"
                title="编辑备注"
              >编辑</button>
            </div>

            <div v-if="previewLoading" class="p-6 text-center text-sm" :style="{ color: 'var(--muted)' }">加载中...</div>
            <div v-else-if="preview.error" class="p-6 text-sm" :style="{ color: 'var(--danger)' }">{{ preview.error }}</div>
            <div v-else-if="isImagePreview" class="p-3 max-h-[70vh] overflow-auto flex items-center justify-center" :style="{ background: 'var(--bg-subtle)' }">
              <img :src="previewUrl" :alt="preview.name" class="max-w-full max-h-[65vh] object-contain rounded-md" />
            </div>
            <div v-else-if="isPdfPreview" class="h-[70vh] bg-white">
              <iframe :src="previewUrl" :title="preview.name" class="w-full h-full border-0"></iframe>
            </div>
            <div v-else-if="isMarkdownPreview" class="p-4 max-h-[70vh] overflow-auto preview-content">
              <div class="text-sm leading-relaxed" v-html="markdownPreview"></div>
              <div v-if="preview.truncated" class="text-xs mt-2" :style="{ color: 'var(--muted)' }">（内容过长，已截断预览）</div>
            </div>
            <div v-else-if="preview.isText" class="p-4 max-h-[70vh] overflow-auto">
              <pre class="text-xs whitespace-pre-wrap break-words m-0" :style="{ color: 'var(--text-secondary)' }"><code>{{ preview.content }}</code></pre>
              <div v-if="preview.truncated" class="text-xs mt-2" :style="{ color: 'var(--muted)' }">（内容过长，已截断预览）</div>
            </div>
            <div v-else class="p-6 text-sm" :style="{ color: 'var(--muted)' }">
              该文件类型暂不支持在线预览
            </div>
          </div>
        </div>

        <!-- 右：子目录详情（备注查看/编辑） -->
        <div class="w-full lg:w-[420px] lg:flex-none" v-else-if="selectedDir">
          <div class="rounded-xl overflow-hidden" :style="{ border: '1px solid var(--line)' }">
            <div class="px-4 py-2 text-xs font-semibold flex items-center gap-2" :style="{ background: 'var(--bg-subtle)', borderBottom: '1px solid var(--line)', color: 'var(--muted)' }">
              <span class="inline-flex shrink-0" :style="{ color: 'var(--accent)' }"><AppIcon name="folder" :size="13" /></span>
              <span class="truncate flex-1">{{ selectedDir.name }}</span>
              <button @click="closeDir" class="flex-none cursor-pointer hover:opacity-80 inline-flex items-center gap-1" :style="{ color: 'var(--accent)' }"><AppIcon name="x" :size="11" /> 关闭</button>
            </div>

            <!-- 目录备注编辑 -->
            <div v-if="noteEditing" class="px-4 py-3" :style="{ borderBottom: '1px solid var(--line)' }">
              <textarea
                v-model="noteDraft"
                rows="3"
                maxlength="2000"
                placeholder="写点备注，比如这个目录存放的内容、用途…"
                class="w-full p-2 rounded-lg outline-none text-sm resize-y"
                :style="{ background: 'var(--bg-subtle)', color: 'var(--text)', border: '1px solid var(--line)' }"
              ></textarea>
              <div class="flex gap-2 mt-2 justify-end">
                <button
                  @click="cancelEditNote"
                  class="px-2.5 py-1 text-xs rounded cursor-pointer"
                  :style="{ background: 'var(--hover)', color: 'var(--muted)' }"
                >取消</button>
                <button
                  @click="saveNote"
                  :disabled="noteSaving"
                  class="px-2.5 py-1 text-xs font-semibold rounded cursor-pointer"
                  :style="{ background: 'var(--accent)', color: '#fff', opacity: noteSaving ? 0.6 : 1 }"
                >{{ noteSaving ? '保存中…' : '保存' }}</button>
              </div>
            </div>
            <div v-else class="px-4 py-2.5 flex items-start gap-1.5" :style="{ borderBottom: '1px solid var(--line)' }">
              <span class="inline-flex mt-0.5 shrink-0" :style="{ color: selectedDir.note ? 'var(--accent2)' : 'var(--muted)' }"><AppIcon name="stickyNote" :size="12" /></span>
              <span class="text-xs font-semibold shrink-0" :style="{ color: 'var(--muted)' }">用户备注</span>
              <span v-if="selectedDir.note" class="text-xs whitespace-pre-wrap flex-1" :style="{ color: 'var(--text-secondary)' }">{{ selectedDir.note }}</span>
              <span v-else class="text-xs italic flex-1" :style="{ color: 'var(--muted)' }">添加备注，说明这个目录的作用…</span>
              <button
                @click="startEditNote"
                class="text-xs px-1.5 py-0.5 rounded cursor-pointer shrink-0"
                :style="{ color: 'var(--accent)' }"
                title="编辑备注"
              >编辑</button>
            </div>

            <div class="p-4 text-xs leading-relaxed" :style="{ color: 'var(--muted)' }">
              提示：子目录支持自定义备注；AI 描述可在文件夹列表页针对一级文件夹生成，文件可在左侧预览中点击“AI 解读”。
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

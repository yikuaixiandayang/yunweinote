<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import { getScripts, getScriptDetail, getScriptLocateUrl, getScriptDownloadUrl, agentDescribe, refreshAll, getRefreshProgress, saveScriptNote, deleteScriptNote } from '../api/index.js'

const router = useRouter()

const emit = defineEmits(['close'])

const scripts = ref([])
const loading = ref(true)
const error = ref('')
const selected = ref(null)       // 当前选中的脚本对象（含 content）
const searchQuery = ref('')

// AI 解读状态
const aiDoc = ref(null)
const aiLoading = ref(false)

// 一键更新描述进度
const refresh = ref({ running: false, total: 0, done: 0, failed: 0, stage: '', current: '', elapsed: 0, error: '' })
let progressTimer = null
const refreshPercent = computed(() => refresh.value.total ? Math.round((refresh.value.done / refresh.value.total) * 100) : 0)

// 复制状态
const copySuccess = ref(false)
let copyTimer = null

// 备注编辑状态（列表卡片 inline 编辑）
const noteEditing = ref(null)    // 当前正在编辑的 relPath
const noteDraft = ref('')
const noteSaving = ref(false)
// 详情页备注编辑
const detailNoteEditing = ref(false)
const detailNoteDraft = ref('')
const detailNoteSaving = ref(false)

// 按分类分组
const groupedScripts = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  const filtered = q
    ? scripts.value.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.purpose.toLowerCase().includes(q) ||
        s.category.toLowerCase().includes(q) ||
        (s.note || '').toLowerCase().includes(q))
    : scripts.value
  const m = {}
  filtered.forEach(s => {
    if (!m[s.category]) m[s.category] = []
    m[s.category].push(s)
  })
  return Object.entries(m).map(([cat, items]) => ({ cat, items }))
})

const categoryLabels = {
  ca: '证书管理',
  'system-init': '系统初始化',
  mysql: '数据库',
  windows: 'Windows 工具',
  sentinel: '熔断演示',
  'notes-tools': '知识库工具',
  app: '应用启动',
  misc: '杂项',
}

function catLabel(cat) {
  return categoryLabels[cat] || cat
}

async function loadScripts() {
  loading.value = true
  error.value = ''
  try {
    const data = await getScripts()
    scripts.value = data.scripts || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function openScript(s) {
  selected.value = { ...s, content: '加载中...' }
  aiDoc.value = null
  aiLoading.value = false
  detailNoteEditing.value = false
  detailNoteDraft.value = ''
  try {
    const detail = await getScriptDetail(s.relPath)
    selected.value = detail
  } catch (e) {
    selected.value = { ...s, content: `加载失败: ${e.message}` }
  }
}

// AI 解读当前脚本（后端有缓存，同一脚本只调一次 LLM）
async function runDescribe() {
  if (!selected.value || aiLoading.value) return
  aiLoading.value = true
  aiDoc.value = null
  try {
    aiDoc.value = await agentDescribe(selected.value.relPath, 'script')
  } catch (e) {
    aiDoc.value = { error: e.message }
  } finally {
    aiLoading.value = false
  }
}

function closeDetail() {
  selected.value = null
}

async function copyContent() {
  if (!selected.value?.content || selected.value.content === '加载中...') return
  try {
    await navigator.clipboard.writeText(selected.value.content)
    copySuccess.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copySuccess.value = false }, 2000)
  } catch {
    // fallback for non-HTTPS contexts
    const ta = document.createElement('textarea')
    ta.value = selected.value.content
    ta.style.cssText = 'position:fixed;left:-9999px'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copySuccess.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copySuccess.value = false }, 2000)
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function extIconName(ext) {
  const m = { '.sh': 'terminal', '.py': 'fileText', '.ps1': 'terminal', '.bat': 'terminal', '.conf': 'settings', '.yml': 'settings', '.yaml': 'settings' }
  return m[ext] || 'paper'
}

// 在资源管理器中定位脚本文件
async function locateScript(s) {
  try {
    const res = await fetch(getScriptLocateUrl(s.relPath))
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || '定位失败')
  } catch (e) {
    alert('定位失败: ' + e.message)
  }
}

// 下载脚本文件
function downloadScript(s) {
  const a = document.createElement('a')
  a.href = getScriptDownloadUrl(s.relPath)
  a.download = s.name
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// ── 自定义备注（列表卡片 inline 编辑） ──
function startEditNote(s, evt) {
  evt?.stopPropagation()
  noteEditing.value = s.relPath
  noteDraft.value = s.note || ''
}

function cancelEditNote() {
  noteEditing.value = null
  noteDraft.value = ''
}

async function saveNote(s) {
  if (noteSaving.value) return
  noteSaving.value = true
  const text = noteDraft.value.trim()
  try {
    if (text) {
      await saveScriptNote(s.relPath, text)
      s.note = text
    } else {
      await deleteScriptNote(s.relPath)
      s.note = ''
    }
    noteEditing.value = null
    noteDraft.value = ''
  } catch (e) {
    alert('保存备注失败: ' + e.message)
  } finally {
    noteSaving.value = false
  }
}

// ── 详情页备注编辑 ──
function startEditDetailNote() {
  detailNoteDraft.value = selected.value?.note || ''
  detailNoteEditing.value = true
}

function cancelEditDetailNote() {
  detailNoteEditing.value = false
  detailNoteDraft.value = ''
}

async function saveDetailNote() {
  if (detailNoteSaving.value || !selected.value) return
  detailNoteSaving.value = true
  const text = detailNoteDraft.value.trim()
  try {
    if (text) {
      await saveScriptNote(selected.value.relPath, text)
      selected.value.note = text
      // 同步更新列表中对应项
      const item = scripts.value.find(x => x.relPath === selected.value.relPath)
      if (item) item.note = text
    } else {
      await deleteScriptNote(selected.value.relPath)
      selected.value.note = ''
      const item = scripts.value.find(x => x.relPath === selected.value.relPath)
      if (item) item.note = ''
    }
    detailNoteEditing.value = false
    detailNoteDraft.value = ''
  } catch (e) {
    alert('保存备注失败: ' + e.message)
  } finally {
    detailNoteSaving.value = false
  }
}

onMounted(async () => {
  // 启动时若后台刷新任务在跑，接续轮询进度
  try {
    const p = await getRefreshProgress()
    if (p.running) {
      refresh.value = { ...refresh.value, ...p }
      pollProgress()
    }
  } catch {}
  loadScripts()
})

async function pollProgress() {
  try {
    const p = await getRefreshProgress()
    refresh.value = { ...refresh.value, ...p }
    if (p.running) {
      progressTimer = setTimeout(pollProgress, 2000)
    } else {
      progressTimer = null
      await loadScripts()  // 完成后刷新脚本列表
    }
  } catch {
    progressTimer = setTimeout(pollProgress, 3000)
  }
}

async function startRefresh(force = false) {
  if (refresh.value.running) return
  if (force && !confirm(`将强制重新生成全部 ${refresh.value.total || ''} 项描述（脚本+文件夹），会消耗较多 AI 额度，确认继续？`)) return
  try {
    const r = await refreshAll(force)
    if (!r.started) { alert(r.error || '启动失败'); return }
    refresh.value = { running: true, total: r.total, done: 0, failed: 0,
                      stage: '', current: '', elapsed: 0, error: '' }
    pollProgress()
  } catch (e) {
    alert('启动更新失败: ' + e.message)
  }
}
</script>

<template>
  <div class="min-h-screen pb-10" :style="{ background: 'var(--bg)' }">
    <!-- 共享顶栏 -->
    <AppHeader title="运维脚本库">
      <span class="text-sm" :style="{ color: 'var(--muted)' }">{{ scripts.length }} 个脚本</span>
      <div class="ml-auto" v-if="!selected">
        <input
          v-model="searchQuery"
          placeholder="搜索脚本..."
          class="surface-card px-3 py-1.5 text-sm rounded-lg w-48 outline-none"
          :style="{ color: 'var(--text)' }"
        />
      </div>
    </AppHeader>

    <div class="p-6 max-w-[1200px] mx-auto">

    <!-- 一键更新描述（仅列表视图显示） -->
    <div v-if="!selected" class="flex flex-wrap items-center gap-2 mb-5">
      <button
        @click="startRefresh(false)"
        :disabled="refresh.running"
        class="px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all inline-flex items-center gap-1.5"
        :style="{ background: 'var(--accent)', color: '#fff', opacity: refresh.running ? 0.6 : 1, border: '1px solid var(--accent)' }"
        title="AI 一键为所有脚本和文件夹生成/刷新描述（用途/用法/工作过程）"
      ><AppIcon :name="refresh.running ? 'refresh' : 'zap'" :size="12" /> {{ refresh.running ? '更新中…' : '一键更新所有描述' }}</button>
      <button
        v-if="!refresh.running"
        @click="startRefresh(true)"
        class="surface-card px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
        :style="{ color: 'var(--muted)' }"
        title="强制重新生成全部描述（命中缓存也重做，耗额度）"
      >强制全部重生成</button>
    </div>
    <div v-if="!selected && (refresh.running || refresh.done > 0)" class="mb-5 surface-card rounded-xl p-3" :style="{ border: '1px solid var(--line)' }">
      <div class="flex items-center gap-3 mb-2">
        <span class="text-xs font-semibold" :style="{ color: 'var(--accent)' }">{{ refresh.running ? '正在更新描述…' : '更新完成' }}</span>
        <span class="text-xs" :style="{ color: 'var(--muted)' }">
          {{ refresh.done }}/{{ refresh.total }}
          <span v-if="refresh.failed" :style="{ color: 'var(--danger)' }">· 失败 {{ refresh.failed }}</span>
          · {{ refresh.elapsed }}s
        </span>
        <span v-if="refresh.current" class="text-xs ml-auto truncate" :style="{ color: 'var(--text-secondary)', maxWidth: '50%' }">
          <AppIcon :name="refresh.stage === 'scripts' ? 'terminal' : 'folder'" :size="11" /> {{ refresh.current }}
        </span>
      </div>
      <div class="h-1.5 rounded-full overflow-hidden" :style="{ background: 'var(--hover)' }">
        <div class="h-full transition-all" :style="{ width: (refresh.total ? Math.round(refresh.done/refresh.total*100) : 0) + '%', background: 'var(--accent)' }"></div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="text-center py-20" :style="{ color: 'var(--muted)' }">
      加载中...
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="text-center py-20" :style="{ color: 'var(--danger)' }">
      {{ error }}
    </div>

    <!-- 详情视图 -->
    <div v-else-if="selected" class="max-w-[1200px] mx-auto">
      <div class="surface-card rounded-xl p-5 mb-4">
        <div class="flex items-center gap-2 mb-3">
          <span class="inline-flex" :style="{ color: 'var(--accent)' }"><AppIcon :name="extIconName(selected.ext)" :size="22" stroke-width="1.8" /></span>
          <h2 class="text-lg font-bold m-0" :style="{ color: 'var(--text)' }">{{ selected.name }}</h2>
          <span class="text-xs px-2 py-0.5 rounded" :style="{ background: 'var(--hover)', color: 'var(--muted)' }">
            {{ catLabel(selected.category) }}
          </span>
          <span class="text-xs" :style="{ color: 'var(--muted)' }">{{ formatSize(selected.size) }}</span>
        </div>
        <div class="text-sm space-y-1 mb-3" :style="{ color: 'var(--text-secondary)' }">
          <div v-if="selected.purpose"><b>用途：</b>{{ selected.purpose }}</div>
          <div v-if="selected.sourceNote"><b>来源笔记：</b>{{ selected.sourceNote }}</div>
          <div v-if="selected.update"><b>更新：</b>{{ selected.update }}</div>
          <div v-if="selected.usage"><b>用法：</b><pre class="mt-1 p-2 rounded text-xs overflow-x-auto" :style="{ background: 'var(--bg-subtle)', color: 'var(--text-secondary)' }">{{ selected.usage }}</pre></div>
        </div>
        <!-- 自定义备注 -->
        <div v-if="detailNoteEditing" class="mt-3 pt-3" :style="{ borderTop: '1px dashed var(--line)' }">
          <textarea
            v-model="detailNoteDraft"
            rows="3"
            maxlength="2000"
            placeholder="写点备注，比如使用心得、踩过的坑、待办…"
            class="w-full p-2 rounded-lg outline-none text-sm resize-y"
            :style="{ background: 'var(--bg-subtle)', color: 'var(--text)', border: '1px solid var(--line)' }"
          ></textarea>
          <div class="flex gap-2 mt-2 justify-end">
            <button
              @click="cancelEditDetailNote"
              class="px-2.5 py-1 text-xs rounded cursor-pointer"
              :style="{ background: 'var(--hover)', color: 'var(--muted)' }"
            >取消</button>
            <button
              @click="saveDetailNote"
              :disabled="detailNoteSaving"
              class="px-2.5 py-1 text-xs font-semibold rounded cursor-pointer"
              :style="{ background: 'var(--accent)', color: '#fff', opacity: detailNoteSaving ? 0.6 : 1 }"
            >{{ detailNoteSaving ? '保存中…' : '保存' }}</button>
          </div>
        </div>
        <div v-else class="mt-3 pt-3 flex items-start gap-1.5" :style="{ borderTop: '1px dashed var(--line)' }">
          <span class="inline-flex mt-0.5 shrink-0" :style="{ color: selected.note ? 'var(--accent2)' : 'var(--muted)' }"><AppIcon name="edit" :size="12" /></span>
          <span v-if="selected.note" class="text-sm whitespace-pre-wrap flex-1" :style="{ color: 'var(--text-secondary)' }">{{ selected.note }}</span>
          <span v-else class="text-sm italic flex-1" :style="{ color: 'var(--muted)' }">添加备注…</span>
          <button
            @click="startEditDetailNote"
            class="text-xs px-1.5 py-0.5 rounded cursor-pointer shrink-0"
            :style="{ color: 'var(--accent)' }"
            title="编辑备注"
          >编辑</button>
        </div>
        <!-- 操作按钮 -->
        <div class="flex gap-2 mt-3">
          <button
            @click="locateScript(selected)"
            class="px-3 py-1.5 text-sm font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
            :style="{ background: 'var(--hover)', border: '1px solid var(--line)', color: 'var(--accent)' }"
            title="在资源管理器中打开脚本所在文件夹"
          ><AppIcon name="folderOpen" :size="13" /> 定位文件</button>
          <button
            @click="downloadScript(selected)"
            class="px-3 py-1.5 text-sm font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
            :style="{ background: 'var(--hover)', border: '1px solid var(--line)', color: 'var(--accent)' }"
            title="下载脚本文件"
          ><AppIcon name="download" :size="13" /> 下载</button>
          <button
            @click="copyContent"
            class="px-3 py-1.5 text-sm font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
            :style="{ background: copySuccess ? 'var(--accent)' : 'var(--hover)', border: '1px solid var(--line)', color: copySuccess ? '#fff' : 'var(--accent)' }"
            title="复制脚本内容"
          ><AppIcon :name="copySuccess ? 'check' : 'copy'" :size="13" /> {{ copySuccess ? '已复制' : '复制' }}</button>
          <button
            @click="runDescribe"
            :disabled="aiLoading"
            class="px-3 py-1.5 text-sm font-semibold rounded-lg cursor-pointer transition-all inline-flex items-center gap-1.5"
            :style="{ background: 'var(--accent)', border: '1px solid var(--accent)', color: '#fff', opacity: aiLoading ? 0.6 : 1 }"
            title="AI 解读这个脚本：用途 / 用法 / 工作过程"
          ><AppIcon name="zap" :size="13" /> {{ aiLoading ? 'AI 解读中…' : (aiDoc && !aiDoc.error ? '重新解读' : 'AI 解读') }}</button>
        </div>

        <!-- AI 解读结果 -->
        <div v-if="aiLoading" class="mt-3 px-4 py-3 text-sm rounded-lg" :style="{ background: 'var(--hover)', color: 'var(--muted)' }">
          ⏳ AI 正在阅读脚本并生成解读（首次约需 10-30 秒，之后走缓存）…
        </div>
        <div v-else-if="aiDoc" class="mt-3 rounded-lg p-4" :style="{ background: 'color-mix(in srgb, var(--accent) 5%, var(--card))', border: '1px solid color-mix(in srgb, var(--accent) 22%, var(--line))' }">
          <div v-if="aiDoc.error" class="text-sm" :style="{ color: 'var(--danger)' }">{{ aiDoc.error }}</div>
          <template v-else>
            <div class="text-xs font-bold uppercase tracking-wider mb-2 inline-flex items-center gap-1.5" :style="{ color: 'var(--accent)' }">
              <AppIcon name="zap" :size="12" /> AI 解读
            </div>
            <div class="text-sm mb-2" :style="{ color: 'var(--text)' }"><b>用途：</b>{{ aiDoc.purpose }}</div>
            <div class="text-sm mb-2 whitespace-pre-wrap" :style="{ color: 'var(--text)' }" v-if="aiDoc.usage"><b>用法：</b>{{ aiDoc.usage }}</div>
            <div class="text-sm mb-2" v-if="aiDoc.workflow?.length">
              <b :style="{ color: 'var(--text)' }">工作过程：</b>
              <ol class="m-0 mt-1 pl-5 text-sm space-y-0.5" :style="{ color: 'var(--text-secondary)' }">
                <li v-for="(step, i) in aiDoc.workflow" :key="i">{{ step }}</li>
              </ol>
            </div>
            <div class="text-sm" :style="{ color: 'var(--text-secondary)' }" v-if="aiDoc.notes"><b>注意：</b>{{ aiDoc.notes }}</div>
          </template>
        </div>
      </div>
      <div class="rounded-xl overflow-hidden" :style="{ border: '1px solid var(--line)' }">
        <div class="px-4 py-2 text-xs font-semibold flex items-center justify-between" :style="{ background: 'var(--bg-subtle)', borderBottom: '1px solid var(--line)', color: 'var(--muted)' }">
          <span>源码</span>
          <button
            @click="closeDetail"
            class="cursor-pointer hover:opacity-80 inline-flex items-center gap-1"
            :style="{ color: 'var(--accent)' }"
          ><AppIcon name="arrowLeft" :size="12" /> 返回列表</button>
        </div>
        <pre class="p-4 text-xs overflow-auto m-0" :style="{ background: 'var(--card)', color: 'var(--text)', maxHeight: 'calc(100vh - 350px)' }"><code>{{ selected.content }}</code></pre>
      </div>
    </div>

    <!-- 列表视图 -->
    <div v-else class="max-w-[1200px] mx-auto">
      <div v-if="groupedScripts.length === 0" class="text-center py-20" :style="{ color: 'var(--muted)' }">
        没有匹配的脚本
      </div>
      <div v-for="g in groupedScripts" :key="g.cat" class="mb-6">
        <h3 class="text-sm font-semibold mb-2 pb-1" :style="{ color: 'var(--text-secondary)', borderBottom: '1px solid var(--line)' }">
          {{ catLabel(g.cat) }} <span :style="{ color: 'var(--muted)' }">({{ g.items.length }})</span>
        </h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
          <div
            v-for="s in g.items"
            :key="s.relPath"
            @click="openScript(s)"
            class="surface-card rounded-lg p-3 cursor-pointer transition-all hover:scale-[1.01] relative group"
          >
            <div class="flex items-center gap-2 mb-1">
              <span class="inline-flex" :style="{ color: 'var(--accent)' }"><AppIcon :name="extIconName(s.ext)" :size="16" stroke-width="1.8" /></span>
              <span class="font-semibold text-sm" :style="{ color: 'var(--text)' }">{{ s.name }}</span>
              <span class="text-xs ml-auto" :style="{ color: 'var(--muted)' }">{{ formatSize(s.size) }}</span>
            </div>
            <div class="text-xs" :style="{ color: 'var(--text-secondary)' }">
              {{ s.purpose || '（无描述）' }}
            </div>
            <div class="text-xs mt-1" v-if="s.sourceNote" :style="{ color: 'var(--muted)' }">
              <AppIcon name="paperclip" :size="11" /> {{ s.sourceNote }}
            </div>
            <!-- 自定义备注 -->
            <div v-if="noteEditing === s.relPath" class="mt-2" @click.stop @keydown.stop>
              <textarea
                v-model="noteDraft"
                rows="3"
                maxlength="2000"
                placeholder="写点备注…"
                class="w-full p-2 rounded-lg outline-none text-xs resize-y"
                :style="{ background: 'var(--bg-subtle)', color: 'var(--text)', border: '1px solid var(--line)' }"
              ></textarea>
              <div class="flex gap-2 mt-1 justify-end">
                <button
                  @click="cancelEditNote"
                  class="px-2 py-0.5 text-xs rounded cursor-pointer"
                  :style="{ background: 'var(--hover)', color: 'var(--muted)' }"
                >取消</button>
                <button
                  @click="saveNote(s)"
                  :disabled="noteSaving"
                  class="px-2 py-0.5 text-xs font-semibold rounded cursor-pointer"
                  :style="{ background: 'var(--accent)', color: '#fff', opacity: noteSaving ? 0.6 : 1 }"
                >{{ noteSaving ? '保存中…' : '保存' }}</button>
              </div>
            </div>
            <div v-else-if="s.note" class="text-xs mt-1 flex items-start gap-1" :style="{ color: 'var(--text-secondary)' }">
              <span class="inline-flex mt-0.5 shrink-0" :style="{ color: 'var(--accent2)' }"><AppIcon name="edit" :size="11" /></span>
              <span class="whitespace-pre-wrap flex-1 line-clamp-2">{{ s.note }}</span>
              <button
                @click="startEditNote(s, $event)"
                class="text-xs shrink-0"
                :style="{ color: 'var(--accent)' }"
                title="编辑备注"
              >编辑</button>
            </div>
            <!-- 悬停快捷按钮 -->
            <div class="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity" @click.stop>
              <button
                @click="startEditNote(s, $event)"
                class="px-2 py-1 text-xs rounded cursor-pointer inline-flex items-center"
                :style="{ background: 'var(--hover)', border: '1px solid var(--line)', color: 'var(--accent)' }"
                title="添加/编辑备注"
              ><AppIcon name="edit" :size="13" /></button>
              <button
                @click="locateScript(s)"
                class="px-2 py-1 text-xs rounded cursor-pointer inline-flex items-center"
                :style="{ background: 'var(--hover)', border: '1px solid var(--line)', color: 'var(--accent)' }"
                title="在资源管理器中定位"
              ><AppIcon name="folderOpen" :size="13" /></button>
              <button
                @click="downloadScript(s)"
                class="px-2 py-1 text-xs rounded cursor-pointer inline-flex items-center"
                :style="{ background: 'var(--hover)', border: '1px solid var(--line)', color: 'var(--accent)' }"
                title="下载"
              ><AppIcon name="download" :size="13" /></button>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

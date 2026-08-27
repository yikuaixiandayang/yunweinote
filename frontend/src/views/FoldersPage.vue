<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import { getFolders, refreshAll, getRefreshProgress, saveFolderNote, deleteFolderNote, agentDescribeFolder, agentDescribeFolderReadme } from '../api/index.js'

const router = useRouter()
const folders = ref([])
const loading = ref(true)
const error = ref('')
const lastSync = ref('')
const query = ref('')
const sortBy = ref('name')
const typeFilter = ref('all')

// 备注编辑状态
const noteEditing = ref(null)   // 当前正在编辑的文件夹名
const noteDraft = ref('')
const noteSaving = ref(false)

// 单个文件夹 AI 生成描述状态（仅用户点击按钮触发）
const aiGenName = ref('')       // 正在生成描述的文件夹名
// 单个文件夹 AI 生成 README 状态（仅在 README 缺失时显示入口）
const aiReadmeName = ref('')    // 正在生成 README 的文件夹名

// 拼接 AI 描述全文（用于卡片 tooltip）
function aiDocFull(f) {
  const d = f.aiDoc
  if (!d || d.error) return ''
  return [d.summary, d.purpose, d.usage, d.contents, d.notes].filter(Boolean).join('\n')
}

// 一键更新描述状态
const refresh = ref({
  running: false,
  total: 0,
  done: 0,
  failed: 0,
  stage: '',
  current: '',
  elapsed: 0,
  error: '',
})
let progressTimer = null

// 类型 → 图标名（自制 SVG 图标，继承主题色）
const typeIconMap = {
  '项目': 'package',
  '笔记文档': 'fileText',
  '脚本库': 'terminal',
  '资料库': 'paper',
  '图片素材': 'paper',
  '配置文件': 'settings',
  '数据/其他': 'database',
}

function typeIconName(t) {
  return typeIconMap[t] || 'folder'
}

const folderTypes = computed(() => [...new Set(folders.value.map(f => f.type))].sort())
const visibleFolders = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = folders.value.filter(f => {
    const matchesQuery = !q || `${f.name} ${f.type} ${f.readme?.excerpt || ''} ${f.note || ''}`.toLowerCase().includes(q)
    return matchesQuery && (typeFilter.value === 'all' || f.type === typeFilter.value)
  })
  return [...list].sort((a, b) => {
    if (sortBy.value === 'size') return (b.sizeBytes || 0) - (a.sizeBytes || 0)
    if (sortBy.value === 'files') return (b.fileCount || 0) - (a.fileCount || 0)
    if (sortBy.value === 'mtime') return String(b.mtime).localeCompare(String(a.mtime))
    return a.name.localeCompare(b.name, 'zh-CN')
  })
})

function topExtensions(f) {
  return Object.entries(f.extStats || {}).slice(0, 4)
}

function extWidth(f, count) {
  const total = Object.values(f.extStats || {}).reduce((sum, n) => sum + n, 0) || 1
  return `${Math.max(4, Math.round(count / total * 100))}%`
}

function fmtTs() {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

async function load(force = false) {
  try {
    const data = await getFolders(force)
    folders.value = data.folders || []
    lastSync.value = fmtTs()
    error.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openFolder(name) {
  router.push(`/folders/${encodeURIComponent(name)}`)
}

// 页面切回前台时刷新（走缓存，60s 内不重扫；超时则触发一次扫描）
function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    load(false)
  }
}

// ── 自定义备注 ──
function startEditNote(f, evt) {
  evt?.stopPropagation()
  noteEditing.value = f.name
  noteDraft.value = f.note || ''
}

function cancelEditNote() {
  noteEditing.value = null
  noteDraft.value = ''
}

async function saveNote(f) {
  if (noteSaving.value) return
  const text = noteDraft.value.trim()
  if (text.length > 2000) {
    alert('备注过长，请控制在 2000 字以内')
    return
  }
  noteSaving.value = true
  try {
    const r = text
      ? await saveFolderNote(f.name, text)
      : await deleteFolderNote(f.name)
    if (r && r.error) {
      alert('保存备注失败: ' + r.error)
      return
    }
    f.note = text
    noteEditing.value = null
    noteDraft.value = ''
  } catch (e) {
    alert('保存备注失败: ' + e.message)
  } finally {
    noteSaving.value = false
  }
}

// ── 单个文件夹 AI 生成描述（仅点击触发，失败不影响已有备注/AI 描述） ──
async function genFolderDoc(f) {
  if (aiGenName.value) return
  const hasDoc = f.aiDoc && !f.aiDoc.error && f.aiDoc.summary
  if (hasDoc && !confirm(`「${f.name}」已有 AI 描述，重新生成将覆盖旧描述（不影响用户备注），继续？`)) return
  aiGenName.value = f.name
  try {
    const r = await agentDescribeFolder(f.name, hasDoc)
    if (r && r.error) {
      alert(`AI 生成描述失败：${r.error}`)
    } else if (r) {
      f.aiDoc = r
    }
  } catch (e) {
    alert('AI 生成描述失败: ' + e.message)
  } finally {
    aiGenName.value = ''
  }
}

// ── 单个文件夹 AI 生成/更新 README（始终调 LLM：有则更新，无则创建） ──
async function genFolderReadme(f) {
  if (aiReadmeName.value) return
  const hasReadme = f.readme && f.readme.exists
  if (hasReadme && !confirm(`「${f.name}」已有 README，将用 LLM 重新生成（覆盖现有内容），继续？`)) return
  aiReadmeName.value = f.name
  try {
    const r = await agentDescribeFolderReadme(f.name, true)
    if (r && r.error) {
      alert(`AI 生成 README 失败：${r.error}`)
    } else if (r) {
      // 成功后刷新当前列表，让 f.readme 反映新状态
      await load()
    }
  } catch (e) {
    alert('AI 生成 README 失败: ' + e.message)
  } finally {
    aiReadmeName.value = ''
  }
}

// ── 一键更新描述 ──
const refreshPercent = computed(() => {
  if (!refresh.value.total) return 0
  return Math.round((refresh.value.done / refresh.value.total) * 100)
})

async function pollProgress() {
  try {
    const p = await getRefreshProgress()
    refresh.value = { ...refresh.value, ...p }
    if (p.running) {
      progressTimer = setTimeout(pollProgress, 2000)
    } else {
      progressTimer = null
      // 完成后刷新文件夹列表，展示新生成的 AI 描述
      await load()
    }
  } catch {
    progressTimer = setTimeout(pollProgress, 3000)
  }
}

async function startRefresh(force = false) {
  if (refresh.value.running) return
  if (force && !confirm(`将强制重新生成全部 ${refresh.value.total || ''} 项（脚本 + 文件夹描述 + README 全部让 LLM 重做，含覆盖已有 README）。会消耗较多 AI 额度，确认继续？`)) return
  try {
    const r = await refreshAll(force)
    if (!r.started) {
      alert(r.error || '启动失败')
      return
    }
    refresh.value = { running: true, total: r.total, done: 0, failed: 0,
                      stage: '', current: '', elapsed: 0, error: '' }
    pollProgress()
  } catch (e) {
    alert('启动更新失败: ' + e.message)
  }
}

onMounted(async () => {
  // 启动时若后台已有任务在跑，直接接续轮询进度
  try {
    const p = await getRefreshProgress()
    if (p.running) {
      refresh.value = { ...refresh.value, ...p }
      pollProgress()
    }
  } catch {}
  load()
  // 页面从后台切回前台时刷新（替代原来的 30s 定时器，避免后台标签页白白消耗）
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  if (progressTimer) clearTimeout(progressTimer)
})
</script>

<template>
  <div class="min-h-screen pb-10" :style="{ background: 'var(--bg)' }">
    <!-- 共享顶栏 -->
    <AppHeader title="项目文件夹总览">
      <span class="text-sm hidden md:inline" :style="{ color: 'var(--muted)' }">{{ folders.length }} 个文件夹 · 自动检测</span>
    </AppHeader>

    <div class="p-6 max-w-[1200px] mx-auto">
      <!-- 工具行 -->
      <div class="flex flex-wrap items-center gap-2 mb-5">
        <span v-if="lastSync" class="text-xs" :style="{ color: 'var(--muted)' }">上次同步 {{ lastSync }}</span>
        <button
          @click="load(true)"
          class="surface-card px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
          :style="{ color: 'var(--accent)' }"
        ><AppIcon name="refresh" :size="12" /> 立即刷新</button>
        <button
          @click="startRefresh(false)"
          :disabled="refresh.running"
          class="px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all inline-flex items-center gap-1.5"
          :style="{ background: 'var(--accent)', color: '#fff', opacity: refresh.running ? 0.6 : 1, border: '1px solid var(--accent)' }"
          :title="'AI 一键为所有脚本和文件夹生成/刷新描述，并同步更新 README（无则创建、有但文件变动则更新、没变则跳过省额度）'"
        ><AppIcon :name="refresh.running ? 'refresh' : 'zap'" :size="12" /> {{ refresh.running ? '更新中…' : '一键更新所有描述' }}</button>
        <button
          v-if="!refresh.running"
          @click="startRefresh(true)"
          class="surface-card px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition-all hover:opacity-80 inline-flex items-center gap-1.5"
          :style="{ color: 'var(--muted)' }"
          title="强制重新生成全部描述与 README（忽略缓存/文件变动，全部让 LLM 重做，含覆盖已有 README，耗额度）"
        >强制全部重生成</button>
      </div>

      <!-- 更新进度条 -->
      <div v-if="refresh.running || refresh.done > 0" class="mb-5 surface-card rounded-xl p-3" :style="{ border: '1px solid var(--line)' }">
        <div class="flex items-center gap-3 mb-2">
          <span class="text-xs font-semibold" :style="{ color: 'var(--accent)' }">
            {{ refresh.running ? '正在更新描述…' : '更新完成' }}
          </span>
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
          <div class="h-full transition-all" :style="{ width: refreshPercent + '%', background: 'var(--accent)' }"></div>
        </div>
        <div v-if="refresh.error" class="text-xs mt-2" :style="{ color: 'var(--danger)' }">{{ refresh.error }}</div>
      </div>

      <div v-if="!loading && !error" class="flex flex-wrap items-center gap-2 mb-5">
        <div class="relative flex-1 min-w-[220px]">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none inline-flex" :style="{ color: 'var(--muted)' }"><AppIcon name="search" :size="14" /></span>
          <input v-model="query" type="search" placeholder="搜索文件夹、类型或 README…" aria-label="搜索文件夹"
            class="w-full h-10 pl-9 pr-3 rounded-lg outline-none text-sm"
            :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }" />
        </div>
        <select v-model="typeFilter" aria-label="按类型筛选" class="h-10 px-3 rounded-lg text-sm"
          :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }">
          <option value="all">全部类型</option>
          <option v-for="type in folderTypes" :key="type" :value="type">{{ type }}</option>
        </select>
        <select v-model="sortBy" aria-label="文件夹排序" class="h-10 px-3 rounded-lg text-sm"
          :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }">
          <option value="name">按名称</option>
          <option value="mtime">最近修改</option>
          <option value="size">按大小</option>
          <option value="files">按文件数</option>
        </select>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="text-center py-20" :style="{ color: 'var(--muted)' }">
        加载中...
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="text-center py-20" :style="{ color: 'var(--danger)' }">
        加载失败: {{ error }}
      </div>

      <!-- 文件夹卡片网格 -->
      <div v-else-if="visibleFolders.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="f in visibleFolders"
          :key="f.name"
          @click="openFolder(f.name)"
          @keydown.enter="openFolder(f.name)"
          @keydown.space.prevent="openFolder(f.name)"
          tabindex="0" role="button" :aria-label="`打开文件夹 ${f.name}`"
          class="surface-card rounded-xl p-4 cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <div class="flex items-center gap-2 mb-2">
            <span class="inline-flex w-9 h-9 rounded-lg items-center justify-center" :style="{ background: 'var(--hover)', color: 'var(--accent)' }">
              <AppIcon :name="typeIconName(f.type)" :size="18" stroke-width="1.8" />
            </span>
            <span class="font-bold" :style="{ color: 'var(--text)' }">{{ f.name }}</span>
            <span v-if="!f.readme || !f.readme.exists"
                  class="text-[10px] px-1.5 py-0.5 rounded ml-auto"
                  :style="{ background: 'var(--hover)', color: 'var(--danger)', border: '1px solid var(--danger)' }"
                  title="此目录尚无 README.md，可点击下方『生成 README』一键补全">无 README</span>
            <span v-else class="text-xs px-2 py-0.5 rounded ml-auto" :style="{ background: 'var(--hover)', color: 'var(--muted)' }">
              {{ f.type }}
            </span>
          </div>
          <div v-if="topExtensions(f).length" class="flex h-1.5 rounded-full overflow-hidden mb-3" :style="{ background: 'var(--hover)' }" aria-label="文件类型分布">
            <span v-for="([ext, count], i) in topExtensions(f)" :key="ext" :title="`${ext}: ${count}`"
              :style="{ width: extWidth(f, count), background: ['var(--accent)', 'var(--accent2)', 'var(--purple)', 'var(--star)'][i] }"></span>
          </div>
          <div class="text-xs space-y-1 mb-3" :style="{ color: 'var(--text-secondary)' }">
            <!-- 描述展示：优先用户备注，其次 AI 描述，最后 README -->
            <template v-if="f.note">
              <div class="line-clamp-2" :title="f.note">
                <span class="font-semibold" :style="{ color: 'var(--accent2)' }">备注</span>
                <span :style="{ color: 'var(--text)' }"> {{ f.note }}</span>
              </div>
              <div v-if="f.aiDoc && !f.aiDoc.error && f.aiDoc.summary" class="line-clamp-2" :title="aiDocFull(f)">
                <span class="inline-flex items-center gap-0.5 align-middle font-semibold" :style="{ color: 'var(--accent)' }"><AppIcon name="zap" :size="10" /> AI</span>
                {{ f.aiDoc.summary }}
              </div>
            </template>
            <template v-else-if="f.aiDoc && !f.aiDoc.error && f.aiDoc.summary">
              <div class="line-clamp-2" :title="aiDocFull(f)">
                <span class="inline-flex items-center gap-0.5 align-middle font-semibold" :style="{ color: 'var(--accent)' }"><AppIcon name="zap" :size="10" /> AI</span>
                <span :style="{ color: 'var(--text)' }"> {{ f.aiDoc.summary }}</span>
              </div>
              <div v-if="f.aiDoc.purpose" class="line-clamp-2" :title="aiDocFull(f)" :style="{ color: 'var(--text-secondary)' }">
                {{ f.aiDoc.purpose }}
              </div>
            </template>
            <template v-else>
              <div v-if="f.readme && f.readme.exists" class="line-clamp-2">
                {{ f.readme.excerpt || '（README 为空）' }}
              </div>
              <div v-else class="text-xs">
                {{ f.fileCount }} 个文件 · {{ f.dirCount }} 个子目录
              </div>
            </template>
          </div>
          <div class="flex items-center gap-3 text-xs" :style="{ color: 'var(--muted)' }">
            <span class="inline-flex items-center gap-1"><AppIcon name="hardDrive" :size="12" /> {{ f.size }}</span>
            <span class="inline-flex items-center gap-1"><AppIcon name="paper" :size="12" /> {{ f.fileCount }} 文件</span>
            <span class="ml-auto inline-flex items-center gap-1"><AppIcon name="clock" :size="12" /> {{ f.mtime }}</span>
          </div>
          <!-- 自定义备注 -->
          <div v-if="noteEditing === f.name" class="mt-3 pt-3" :style="{ borderTop: '1px dashed var(--line)' }" @click.stop @keydown.stop>
            <textarea
              v-model="noteDraft"
              rows="3"
              maxlength="2000"
              placeholder="写点备注，比如用途、注意事项、待办…"
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
                @click="saveNote(f)"
                :disabled="noteSaving"
                class="px-2.5 py-1 text-xs font-semibold rounded cursor-pointer"
                :style="{ background: 'var(--accent)', color: '#fff', opacity: noteSaving ? 0.6 : 1 }"
              >{{ noteSaving ? '保存中…' : '保存' }}</button>
            </div>
          </div>
          <div v-else class="mt-3 pt-3 flex items-center gap-1.5" :style="{ borderTop: '1px dashed var(--line)' }">
            <span class="inline-flex shrink-0" :style="{ color: f.note ? 'var(--accent2)' : 'var(--muted)' }"><AppIcon name="edit" :size="12" /></span>
            <span v-if="f.note" class="text-xs flex-1" :style="{ color: 'var(--muted)' }">已设置用户备注</span>
            <span v-else class="text-xs italic flex-1" :style="{ color: 'var(--muted)' }">添加备注…</span>
            <button
              @click="genFolderReadme(f)"
              :disabled="!!aiReadmeName"
              class="text-xs px-1.5 py-0.5 rounded cursor-pointer shrink-0 inline-flex items-center gap-0.5"
              :style="{ color: 'var(--accent)', opacity: aiReadmeName ? 0.6 : 1 }"
              :title="'AI 生成或更新本目录 README.md（有则覆盖，无则创建）'"
            ><AppIcon :name="aiReadmeName === f.name ? 'refresh' : 'paper'" :size="11" /> {{ aiReadmeName === f.name ? '生成中…' : '生成/更新 README' }}</button>
            <button
              @click="genFolderDoc(f)"
              :disabled="!!aiGenName"
              class="text-xs px-1.5 py-0.5 rounded cursor-pointer shrink-0 inline-flex items-center gap-0.5"
              :style="{ color: 'var(--accent)', opacity: aiGenName ? 0.6 : 1 }"
              :title="'AI 根据文件夹内容生成/更新描述（用途/用法/注意事项）'"
            ><AppIcon :name="aiGenName === f.name ? 'refresh' : 'zap'" :size="11" /> {{ aiGenName === f.name ? '生成中…' : 'AI 生成描述' }}</button>
            <button
              @click="startEditNote(f, $event)"
              class="text-xs px-1.5 py-0.5 rounded cursor-pointer shrink-0"
              :style="{ color: 'var(--accent)' }"
              title="编辑备注"
            >编辑</button>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && !error && visibleFolders.length === 0" class="text-center py-20" :style="{ color: 'var(--muted)' }">
        <div class="inline-flex mb-3" :style="{ color: 'var(--muted)' }"><AppIcon name="search" :size="36" stroke-width="1.5" /></div>
        <div class="font-semibold" :style="{ color: 'var(--text)' }">没有匹配的文件夹</div>
        <div class="text-sm mt-1">试试调整关键词或筛选条件</div>
      </div>
    </div>
  </div>
</template>

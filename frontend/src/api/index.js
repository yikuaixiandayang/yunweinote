const API_BASE = '/api'

async function fetchJSON(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  }
  return res.json()
}

export async function getData() {
  return fetchJSON(`${API_BASE}/data`)
}

export async function getNotes() {
  return fetchJSON(`${API_BASE}/note`)
}

export async function getNote(name) {
  return fetchJSON(`${API_BASE}/note/${encodeURIComponent(name)}`)
}

export async function getInsights() {
  return fetchJSON(`${API_BASE}/insights`)
}

export async function searchNotes(q, { cat, tag, sort, page, size } = {}) {
  const params = new URLSearchParams({ q })
  if (cat) params.set('cat', cat)
  if (tag) params.set('tag', tag)
  if (sort) params.set('sort', sort)
  if (page) params.set('page', page)
  if (size) params.set('size', size)
  return fetchJSON(`${API_BASE}/search?${params}`)
}

export async function saveUserData(data) {
  return fetch(`${API_BASE}/data/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function getAppearance() {
  return fetchJSON(`${API_BASE}/appearance`)
}

export async function saveAppearance(data) {
  return fetchJSON(`${API_BASE}/appearance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function rebuildIndex() {
  return fetch(`${API_BASE}/rebuild`, { method: 'POST' })
}

export function getFileUrl(path) {
  return `/files/${path}`
}

export async function getScripts() {
  return fetchJSON(`${API_BASE}/scripts`)
}

export async function getScriptDetail(path) {
  return fetchJSON(`${API_BASE}/script/${path}`)
}

export function getScriptLocateUrl(path) {
  return `${API_BASE}/script-locate/${path}`
}

export function getScriptDownloadUrl(path) {
  return `${API_BASE}/script-download/${path}`
}

export async function getFolders(force = false) {
  return fetchJSON(`${API_BASE}/folders${force ? '?force=true' : ''}`)
}

export async function getFolderTree(name, { depth = 3, limit = 200 } = {}) {
  return fetchJSON(`${API_BASE}/folder/${encodeURIComponent(name)}/tree?depth=${depth}&limit=${limit}`)
}

export async function getFolderFile(name, path) {
  return fetchJSON(`${API_BASE}/folder/${encodeURIComponent(name)}/file/${path.split('/').map(encodeURIComponent).join('/')}`)
}

export function getFolderAssetUrl(name, path) {
  return `${API_BASE}/folder/${encodeURIComponent(name)}/asset/${path.split('/').map(encodeURIComponent).join('/')}`
}

export function getFolderDownloadUrl(name, path) {
  return `${API_BASE}/folder/${encodeURIComponent(name)}/download/${path.split('/').map(encodeURIComponent).join('/')}`
}

export async function getFolderReadme(name) {
  return fetchJSON(`${API_BASE}/folder/${encodeURIComponent(name)}/readme`)
}

// ==================== 文件夹内文件自定义备注 ====================

export function getFolderFileNoteUrl(name, relPath) {
  return `${API_BASE}/folder-file-note/${encodeURIComponent(name)}/${relPath.split('/').map(encodeURIComponent).join('/')}`
}

export async function saveFolderFileNote(name, relPath, note) {
  const res = await fetch(getFolderFileNoteUrl(name, relPath), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  return res.json()
}

export async function deleteFolderFileNote(name, relPath) {
  const res = await fetch(getFolderFileNoteUrl(name, relPath), {
    method: 'DELETE',
  })
  return res.json()
}

// ==================== 自定义备注 ====================

export async function saveFolderNote(name, note) {
  const res = await fetch(`${API_BASE}/folder/${encodeURIComponent(name)}/note`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  return res.json()
}

export async function deleteFolderNote(name) {
  const res = await fetch(`${API_BASE}/folder/${encodeURIComponent(name)}/note`, {
    method: 'DELETE',
  })
  return res.json()
}

export async function saveScriptNote(relPath, note) {
  const res = await fetch(`${API_BASE}/script-note/${relPath.split('/').map(encodeURIComponent).join('/')}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  return res.json()
}

export async function deleteScriptNote(relPath) {
  const res = await fetch(`${API_BASE}/script-note/${relPath.split('/').map(encodeURIComponent).join('/')}`, {
    method: 'DELETE',
  })
  return res.json()
}

// ==================== AI Agent ====================

export async function getAgentConfig() {
  return fetchJSON(`${API_BASE}/agent/config`)
}

export async function setAgentConfig(cfg = {}) {
  const res = await fetch(`${API_BASE}/agent/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  return res.json()
}

export async function checkAgentHealth() {
  return fetchJSON(`${API_BASE}/agent/health`)
}

export async function agentSummarize(name) {
  const res = await fetch(`${API_BASE}/agent/summarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return res.json()
}

export async function agentOrganize(cat = '') {
  const res = await fetch(`${API_BASE}/agent/organize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cat }),
  })
  return res.json()
}

export async function agentRecommendPath(goal = '') {
  const res = await fetch(`${API_BASE}/agent/recommend-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal }),
  })
  return res.json()
}

export async function agentOptimizeAlgorithm() {
  const res = await fetch(`${API_BASE}/agent/optimize-algorithm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return res.json()
}

export async function agentChat(sessionId, message) {
  const res = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })
  return res.json()
}

/**
 * 流式对话（SSE）：逐 token 调用 onChunk(content)，
 * 结束/出错时调用 onDone({ error })。
 */
export async function agentChatStream(sessionId, message, onChunk, onDone) {
  let res
  try {
    res = await fetch(`${API_BASE}/agent/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    })
  } catch (e) {
    onDone({ error: `无法连接后端：${e.message}` })
    return
  }
  if (!res.ok || !res.body) {
    onDone({ error: `HTTP ${res.status}` })
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let doneInfo = {}

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // 保留未完成的行
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') { reader.cancel(); onDone(doneInfo); return }
        try {
          const parsed = JSON.parse(data)
          if (parsed.error) { doneInfo = { error: parsed.error }; continue }
          if (parsed.backend) { doneInfo = { ...doneInfo, backend: parsed.backend }; continue }
          if (parsed.content) onChunk(parsed.content)
        } catch { /* 忽略无法解析的行 */ }
      }
    }
    onDone(doneInfo)
  } catch (e) {
    onDone({ error: e.message })
  }
}

export async function getAgentSessions() {
  return fetchJSON(`${API_BASE}/agent/sessions`)
}

export async function getAgentSession(sid) {
  return fetchJSON(`${API_BASE}/agent/session/${encodeURIComponent(sid)}`)
}

export async function clearAgentSession(sid) {
  const res = await fetch(`${API_BASE}/agent/session/${encodeURIComponent(sid)}`, {
    method: 'DELETE',
  })
  return res.json()
}

// ==================== 文件 AI 解读 ====================

/** 获取缓存的解读（不触发 LLM） */
export async function getCachedDescribe(path, kind = 'script') {
  const params = new URLSearchParams({ path, kind })
  return fetchJSON(`${API_BASE}/agent/describe?${params}`)
}

/** AI 解读文件（首次调用 LLM，之后走缓存；force=true 强制重新生成） */
export async function agentDescribe(path, kind = 'script', force = false) {
  const res = await fetch(`${API_BASE}/agent/describe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, kind, force }),
  })
  return res.json()
}

/** 获取缓存的文件夹 AI 描述（不触发 LLM） */
export async function getCachedFolderDoc(name) {
  return fetchJSON(`${API_BASE}/agent/describe-folder?name=${encodeURIComponent(name)}`)
}

/** AI 生成/更新单个文件夹描述（仅用户点击按钮时调用；force=true 强制重新生成） */
export async function agentDescribeFolder(name, force = false) {
  const res = await fetch(`${API_BASE}/agent/describe-folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, force }),
  })
  return res.json()
}

/** AI 为单个目录生成 README.md 并落盘（已有则跳过；force=true 时覆盖） */
export async function agentDescribeFolderReadme(name, force = false) {
  const res = await fetch(`${API_BASE}/agent/describe-folder-readme`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, force }),
  })
  return res.json()
}

// ==================== 一键全量更新（脚本库 + 文件夹描述） ====================

/**
 * 一键更新所有描述：脚本库每个脚本的 AI 解读 + 项目根每个一级文件夹的 AI 描述。
 * 后台串行执行，立即返回；用 getRefreshProgress() 轮询进度。
 * @param {boolean} force true 强制重新生成（否则命中缓存跳过）
 */
export async function refreshAll(force = false) {
  const res = await fetch(`${API_BASE}/agent/refresh-all${force ? '?force=1' : ''}`, {
    method: 'POST',
  })
  return res.json()
}

/** 查询一键更新任务进度 */
export async function getRefreshProgress() {
  return fetchJSON(`${API_BASE}/agent/refresh-all/progress`)
}

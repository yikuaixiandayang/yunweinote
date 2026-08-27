<script setup>
/**
 * 笔记关系图谱 — Obsidian Graph View 风格
 *
 * 移植自 graph-preview.html 的视觉设计语言（dark-first 深空配色），
 * 适配项目数据接口：useNotesStore + CAT_COLORS/CAT_ICONS。
 *
 * 视觉特色：
 *  - 深空径向渐变背景 + 点阵网格 + 暗角
 *  - 每个分类独立径向渐变光晕（节点 halo 用渐变，非纯色）
 *  - 球体高光层（白色径向反光，立体质感）
 *  - 顶栏底部紫青渐变光线、底部状态栏带脉动指示
 *  - 自定义滑块、玻璃面板、聚焦信息卡
 *
 * 交互：滚轮缩放、拖拽平移、节点拖拽固定、单击聚焦、双击打开、
 *       悬停高亮邻域、缩放感知标签、回车搜索定位、键盘快捷键。
 */
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useNotesStore } from '../stores/notes'
import { useThemeStore } from '../stores/theme'
import { useAppearanceStore } from '../stores/appearance'
import { CAT_COLORS, CAT_ICONS, isMetaDoc } from '../constants'

const router = useRouter()
const notes = useNotesStore()
const theme = useThemeStore()
const appearance = useAppearanceStore()

// 壁纸启用时，SVG 内的不透明背景层（径向渐变底色/暗角）需淡化，让壁纸透出来
const wallpaperOn = computed(() => Boolean(appearance.bgEnabled && appearance.backgroundImage))

const svgRef = ref(null)
const containerRef = ref(null)
const loading = computed(() => notes.loading)
const error = computed(() => notes.error)

// ───────── 控制面板状态 ─────────
const showLabels = ref(true)
const showOrphans = ref(false)
const hoverId = ref(null)
const focusId = ref(null)
const selectedCat = ref('')
const searchQuery = ref('')
const simRunning = ref(true)
const panelOpen = ref(true)
const physicsOpen = ref(false)
const currentZoom = ref(1)

const tooltip = ref({ show: false, x: 0, y: 0, name: '', cat: '', degree: 0, tags: [], color: '', glow: '' })

// ───────── 力学参数 ─────────
const physics = ref({
  repel: -280,
  linkDistance: 95,
  linkStrength: 0.4,
  centerStrength: 0.35,
  collision: 16,
})

// ───────── d3 实例引用 ─────────
let simulation = null
let zoomBehavior = null
let svgSelect = null
let gSelect = null
let linkSelect = null
let nodeSelect = null
let haloSelect = null
let highlightSelect = null
let labelSelect = null
let d3ZoomIdentity = null
let d3Lib = null

// ═══════════════════════════════════════════════════════════
//  分类配色（带 glow 高亮色，用于光晕渐变和连线悬停着色）
// ═══════════════════════════════════════════════════════════
// 从 CAT_COLORS 派生 glow 色（提亮版本）
function lighten(hex, amt = 0.18) {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.min(255, ((n >> 16) & 0xff) + Math.round(255 * amt))
  const g = Math.min(255, ((n >> 8) & 0xff) + Math.round(255 * amt))
  const b = Math.min(255, (n & 0xff) + Math.round(255 * amt))
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')
}

const catConfig = computed(() => {
  const m = {}
  notes.catOrder.forEach(name => {
    const color = CAT_COLORS[name] || '#64748b'
    m[name] = { name, color, glow: lighten(color, 0.2), icon: CAT_ICONS[name] || '📄' }
  })
  return m
})

function cssSafe(name) { return String(name).replace(/[^a-zA-Z0-9]/g, '-') }

// ═══════════════════════════════════════════════════════════
//  数据构建
// ═══════════════════════════════════════════════════════════
// 元文档排除逻辑已抽到 constants.js 的 isMetaDoc()，与 /learning 共用，避免两页不一致。

const graphData = computed(() => {
  const allNotes = notes.items
  if (!allNotes.length) return { nodes: [], links: [] }
  const idSet = new Set(allNotes.map(n => n.id))
  // 元文档 id 集合：这些节点不产生连线
  const metaIds = new Set(
    allNotes.filter(n => isMetaDoc(n)).map(n => n.id)
  )
  const links = []
  const linkSet = new Set()
  for (const n of allNotes) {
    // 元文档跳过出向链接
    if (metaIds.has(n.id)) continue
    for (const tid of (n.wikilinks || [])) {
      if (!idSet.has(tid) || tid === n.id) continue
      // 也不连向元文档（避免其他笔记 -> 审计报告的入向边）
      if (metaIds.has(tid)) continue
      const key = n.id < tid ? `${n.id}|${tid}` : `${tid}|${n.id}`
      if (linkSet.has(key)) continue
      linkSet.add(key)
      links.push({ source: n.id, target: tid })
    }
  }
  const degree = {}
  for (const l of links) {
    degree[l.source] = (degree[l.source] || 0) + 1
    degree[l.target] = (degree[l.target] || 0) + 1
  }
  const cfg = catConfig.value
  const nodes = allNotes.map(n => {
    const c = cfg[n.cat] || { color: '#64748b', glow: '#94a3b8' }
    return {
      id: n.id,
      name: n.name.replace(/\.md$/, ''),
      cat: n.cat,
      type: n.type,
      tags: n.tags || [],
      degree: degree[n.id] || 0,
      color: c.color,
      glow: c.glow,
      icon: c.icon,
    }
  })
  return { nodes, links }
})

const filteredData = computed(() => {
  let { nodes, links } = graphData.value
  if (selectedCat.value) nodes = nodes.filter(n => n.cat === selectedCat.value)
  if (!showOrphans.value) {
    const conn = new Set()
    links.forEach(l => { conn.add(l.source); conn.add(l.target) })
    nodes = nodes.filter(n => conn.has(n.id))
  }
  const idSet = new Set(nodes.map(n => n.id))
  const fLinks = links.filter(l => {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    return idSet.has(s) && idSet.has(t)
  })
  return { nodes, links: fLinks, q: searchQuery.value.toLowerCase().trim() }
})

const categories = computed(() => {
  const m = {}
  notes.items.forEach(n => { m[n.cat] = (m[n.cat] || 0) + 1 })
  const cfg = catConfig.value
  return notes.catOrder.filter(c => m[c]).map(c => ({
    name: c, count: m[c], color: cfg[c]?.color || '#64748b',
    glow: cfg[c]?.glow || '#94a3b8', icon: cfg[c]?.icon || '📄',
  }))
})

const activeId = computed(() => hoverId.value || focusId.value)
const activeConnected = computed(() => {
  if (!activeId.value) return null
  const conn = new Set([activeId.value])
  for (const l of graphData.value.links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (s === activeId.value) conn.add(t)
    if (t === activeId.value) conn.add(s)
  }
  return conn
})

const focusNode = computed(() => {
  if (!focusId.value) return null
  return graphData.value.nodes.find(n => n.id === focusId.value) || null
})

// ───────── 尺寸 / 透明度 ─────────
function nodeRadius(n) { return 5 + Math.min(Math.sqrt(n.degree) * 2.6, 16) }

function nodeOpacity(n) {
  const q = filteredData.value.q
  if (q && !n.name.toLowerCase().includes(q)) return 0.06
  if (!activeConnected.value) return 1
  return activeConnected.value.has(n.id) ? 1 : 0.06
}

function haloOpacity(n) {
  const dim = theme.isDark ? 1 : 0.7  // 浅色下光晕减弱
  if (activeId.value && n.id === activeId.value) return 0.7 * dim
  if (!activeConnected.value) return 0.16 * dim
  return activeConnected.value.has(n.id) ? 0.34 * dim : 0.03
}

function highlightOpacity(n) {
  const base = theme.isDark ? 0.6 : 0.4
  if (!activeConnected.value) return base
  return activeConnected.value.has(n.id) ? base + 0.05 : 0.05
}

function linkOpacity(l) {
  const q = filteredData.value.q
  if (!activeConnected.value) return q ? 0.05 : 0.32
  const s = typeof l.source === 'object' ? l.source.id : l.source
  const t = typeof l.target === 'object' ? l.target.id : l.target
  if (activeId.value && (s === activeId.value || t === activeId.value)) return 0.9
  return 0.03
}

function linkWidth(l) {
  if (!activeConnected.value) return 1.2
  const s = typeof l.source === 'object' ? l.source.id : l.source
  const t = typeof l.target === 'object' ? l.target.id : l.target
  if (activeId.value && (s === activeId.value || t === activeId.value)) return 2.6
  return 0.9
}

function linkColor(l) {
  if (!activeConnected.value) return theme.isDark ? '#7a8db0' : '#94a3b8'
  const s = typeof l.source === 'object' ? l.source.id : l.source
  const t = typeof l.target === 'object' ? l.target.id : l.target
  if (activeId.value && (s === activeId.value || t === activeId.value)) {
    const node = graphData.value.nodes.find(n => n.id === activeId.value)
    return node ? node.glow : '#a78bfa'
  }
  return theme.isDark ? '#3a4663' : '#cbd5e1'
}

function labelOpacity(n) {
  const q = filteredData.value.q
  if (q && n.name.toLowerCase().includes(q)) return 1
  if (activeId.value) {
    if (n.id === activeId.value) return 1
    if (activeConnected.value && activeConnected.value.has(n.id)) return 0.95
    return 0.03
  }
  if (!showLabels.value) return 0
  const z = currentZoom.value
  const thr = z < 0.5 ? 8 : z < 0.8 ? 4 : z < 1.2 ? 2 : 0
  if (n.degree < thr) return 0
  return z < 0.5 ? 0.6 : 0.85
}

// ═══════════════════════════════════════════════════════════
//  初始化
// ═══════════════════════════════════════════════════════════
async function initGraph() {
  const svg = svgRef.value
  const container = containerRef.value
  if (!svg || !container) return
  const width = container.clientWidth
  const height = container.clientHeight

  const [d3Force, d3Zoom, d3Select, d3Drag, d3Transition] = await Promise.all([
    import('d3-force'), import('d3-zoom'), import('d3-selection'),
    import('d3-drag'), import('d3-transition'),
  ])
  d3Lib = { ...d3Force, ...d3Zoom, ...d3Select, ...d3Drag, ...d3Transition }
  d3ZoomIdentity = d3Zoom.zoomIdentity

  svg.innerHTML = ''
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`)
  svgSelect = d3Lib.select(svg)
  svgSelect.selectAll('*').remove()

  const defs = svgSelect.append('defs')

  // 背景径向渐变（明/暗双主题）
  const bg = defs.append('radialGradient').attr('id', 'g-bg-grad')
    .attr('cx', '50%').attr('cy', '45%').attr('r', '78%')
  if (theme.isDark) {
    bg.append('stop').attr('offset', '0%').attr('stop-color', '#1a2138')
    bg.append('stop').attr('offset', '45%').attr('stop-color', '#10162a')
    bg.append('stop').attr('offset', '100%').attr('stop-color', '#070a12')
  } else {
    bg.append('stop').attr('offset', '0%').attr('stop-color', '#ffffff')
    bg.append('stop').attr('offset', '45%').attr('stop-color', '#eef2f9')
    bg.append('stop').attr('offset', '100%').attr('stop-color', '#e2e8f1')
  }

  // 点阵网格
  const grid = defs.append('pattern').attr('id', 'g-grid-dots')
    .attr('width', '32').attr('height', '32').attr('patternUnits', 'userSpaceOnUse')
  grid.append('circle').attr('cx', '1').attr('cy', '1').attr('r', '0.9')
    .attr('fill', theme.isDark ? 'rgba(120,138,180,0.18)' : 'rgba(100,116,139,0.14)')

  // 暗角
  const vig = defs.append('radialGradient').attr('id', 'g-vignette')
    .attr('cx', '50%').attr('cy', '50%').attr('r', '72%')
  vig.append('stop').attr('offset', '55%').attr('stop-color', '#000').attr('stop-opacity', '0')
  vig.append('stop').attr('offset', '100%').attr('stop-color', '#000')
    .attr('stop-opacity', theme.isDark ? '0.55' : '0.06')

  // 每个分类独立光晕径向渐变
  categories.value.forEach(c => {
    const g = defs.append('radialGradient').attr('id', `g-halo-${cssSafe(c.name)}`)
      .attr('cx', '50%').attr('cy', '50%').attr('r', '50%')
    g.append('stop').attr('offset', '0%').attr('stop-color', c.glow).attr('stop-opacity', '0.85')
    g.append('stop').attr('offset', '45%').attr('stop-color', c.color).attr('stop-opacity', '0.4')
    g.append('stop').attr('offset', '100%').attr('stop-color', c.color).attr('stop-opacity', '0')
  })

  // 球体高光
  const sph = defs.append('radialGradient').attr('id', 'g-sphere-hl')
    .attr('cx', '35%').attr('cy', '28%').attr('r', '55%')
  sph.append('stop').attr('offset', '0%').attr('stop-color', '#fff').attr('stop-opacity', '0.9')
  sph.append('stop').attr('offset', '45%').attr('stop-color', '#fff').attr('stop-opacity', '0.25')
  sph.append('stop').attr('offset', '100%').attr('stop-color', '#fff').attr('stop-opacity', '0')

  // 发光滤镜
  const glow = defs.append('filter').attr('id', 'g-glow-soft')
    .attr('x', '-80%').attr('y', '-80%').attr('width', '260%').attr('height', '260%')
  glow.append('feGaussianBlur').attr('stdDeviation', '2.2').attr('result', 'b')
  const gm = glow.append('feMerge')
  gm.append('feMergeNode').attr('in', 'b')
  gm.append('feMergeNode').attr('in', 'SourceGraphic')

  const fglow = defs.append('filter').attr('id', 'g-glow-focus')
    .attr('x', '-120%').attr('y', '-120%').attr('width', '340%').attr('height', '340%')
  fglow.append('feGaussianBlur').attr('stdDeviation', '5').attr('result', 'b')
  const fm = fglow.append('feMerge')
  fm.append('feMergeNode').attr('in', 'b')
  fm.append('feMergeNode').attr('in', 'b')
  fm.append('feMergeNode').attr('in', 'SourceGraphic')

  // 背景层（壁纸启用时淡化，避免盖住全局壁纸）
  svgSelect.append('rect').attr('class', 'g-bg')
    .attr('width', width).attr('height', height).attr('fill', 'url(#g-bg-grad)')
    .attr('opacity', wallpaperOn.value ? 0.12 : 1)
  svgSelect.append('rect').attr('class', 'g-grid')
    .attr('width', width).attr('height', height).attr('fill', 'url(#g-grid-dots)').attr('opacity', 0.7)
  svgSelect.append('rect').attr('class', 'g-vig')
    .attr('width', width).attr('height', height).attr('fill', 'url(#g-vignette)').attr('pointer-events', 'none')
    .attr('opacity', wallpaperOn.value ? 0.4 : 1)

  // 缩放层
  gSelect = svgSelect.append('g').attr('class', 'g-zoom')

  zoomBehavior = d3Lib.zoom().scaleExtent([0.1, 12])
    .on('zoom', (event) => {
      gSelect.attr('transform', event.transform)
      currentZoom.value = event.transform.k
      updateLabelVisibility()
    })
  svgSelect.call(zoomBehavior)
  svgSelect.on('click', (event) => {
    if (event.target.tagName === 'svg' || event.target.classList.contains('g-bg') ||
        event.target.classList.contains('g-grid') || event.target.classList.contains('g-vig')) {
      focusId.value = null
      updateHighlight()
    }
  })

  const linkG = gSelect.append('g').attr('class', 'g-links')
  const haloG = gSelect.append('g').attr('class', 'g-halos')
  const nodeG = gSelect.append('g').attr('class', 'g-nodes')
  const hlG = gSelect.append('g').attr('class', 'g-highlights')
  const labelG = gSelect.append('g').attr('class', 'g-labels')

  buildSimulation(width, height, linkG, haloG, nodeG, hlG, labelG)
}

let currentNodes = []
let currentLinks = []
let layerHalo = null
let layerHl = null
let layerLabel = null

/** 热阶段隐藏昂贵图层（display:none 完全跳过 paint，比 opacity 便宜） */
function setHotLayers(hot) {
  if (layerHalo) layerHalo.style('display', hot ? 'none' : null)
  if (layerHl) layerHl.style('display', hot ? 'none' : null)
  if (layerLabel) layerLabel.style('display', hot ? 'none' : null)
}

function buildSimulation(width, height, linkG, haloG, nodeG, hlG, labelG) {
  const data = filteredData.value
  if (!data.nodes.length) { if (simulation) simulation.stop(); return }

  const prev = {}
  if (currentNodes.length) currentNodes.forEach(n => { prev[n.id] = { x: n.x, y: n.y } })
  currentNodes = data.nodes.map(n => {
    const base = { ...n }
    if (prev[n.id]) { base.x = prev[n.id].x; base.y = prev[n.id].y }
    return base
  })
  currentLinks = data.links.map(l => ({
    source: typeof l.source === 'object' ? l.source.id : l.source,
    target: typeof l.target === 'object' ? l.target.id : l.target,
  }))

  if (simulation) simulation.stop()

  const p = physics.value
  simulation = d3Lib.forceSimulation(currentNodes)
    .force('link', d3Lib.forceLink(currentLinks).id(d => d.id)
      .distance(p.linkDistance).strength(p.linkStrength))
    .force('charge', d3Lib.forceManyBody().strength(p.repel))
    .force('center', d3Lib.forceCenter(width / 2, height / 2).strength(p.centerStrength))
    .force('collision', d3Lib.forceCollide().radius(d => nodeRadius(d) + p.collision))
    .force('x', d3Lib.forceX(width / 2).strength(0.04))
    .force('y', d3Lib.forceY(height / 2).strength(0.04))
    // 收敛提速：默认 0.0228 要跑 300+ tick，这里约 80 tick 即冷却，
    // 配合热阶段分层渲染，打开页面时的卡顿大幅下降
    .alphaDecay(0.075)
    .velocityDecay(0.42)

  // 分层渲染：模拟"热"阶段（alpha 高，布局未定）只更新节点+连线，
  // 隐藏光晕/高光/标签层（渐变填充+文字描边是最贵的 paint）；
  // 冷却后恢复全部图层并做一次完整渲染
  layerHalo = haloG
  layerHl = hlG
  layerLabel = labelG
  let hotMode = true
  setHotLayers(true)

  simulation.on('tick', () => {
    const hot = simulation.alpha() > 0.06
    if (hot !== hotMode) { hotMode = hot; setHotLayers(hot) }
    // 节点 + 连线始终更新（廉价属性）
    linkSelect.attr('d', d => curvePath(d.source, d.target))
    nodeSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    if (!hot) {
      haloSelect.attr('cx', d => d.x).attr('cy', d => d.y)
      highlightSelect.attr('cx', d => d.x).attr('cy', d => d.y)
      labelSelect.attr('x', d => d.x).attr('y', d => d.y - nodeRadius(d) - 7)
    }
  })
  simulation.on('end', () => {
    setHotLayers(false)
    linkSelect.attr('d', d => curvePath(d.source, d.target))
    nodeSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    haloSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    highlightSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    labelSelect.attr('x', d => d.x).attr('y', d => d.y - nodeRadius(d) - 7)
  })

  // 边
  linkSelect = linkG.selectAll('path').data(currentLinks).join('path')
    .attr('class', 'g-edge')
    .attr('fill', 'none')
    .attr('stroke', d => linkColor(d))
    .attr('stroke-opacity', d => linkOpacity(d))
    .attr('stroke-width', d => linkWidth(d))
    .attr('stroke-linecap', 'round')

  // 外光晕（每分类独立渐变）
  haloSelect = haloG.selectAll('circle').data(currentNodes).join('circle')
    .attr('class', 'g-node-halo')
    .attr('r', d => nodeRadius(d) * 2.4)
    .attr('fill', d => `url(#g-halo-${cssSafe(d.cat)})`)
    .attr('opacity', d => haloOpacity(d))
    .attr('pointer-events', 'none')

  // 节点本体
  nodeSelect = nodeG.selectAll('circle').data(currentNodes).join('circle')
    .attr('class', 'g-node-core')
    .attr('r', d => nodeRadius(d))
    .attr('fill', d => d.color)
    .attr('stroke', d => {
      if (d.id === focusId.value) return theme.isDark ? '#fff' : 'var(--accent)'
      return theme.isDark ? 'rgba(255,255,255,0.75)' : 'rgba(255,255,255,0.9)'
    })
    .attr('stroke-width', d => d.id === focusId.value ? 2.5 : 1.6)
    .attr('opacity', d => nodeOpacity(d))
    .style('cursor', 'pointer')
    .on('mouseenter', (event, d) => { hoverId.value = d.id; showTooltip(event, d); updateHighlight() })
    .on('mousemove', (event) => moveTooltip(event))
    .on('mouseleave', () => { hoverId.value = null; hideTooltip(); updateHighlight() })
    .on('click', (event, d) => {
      event.stopPropagation()
      focusId.value = focusId.value === d.id ? null : d.id
      updateHighlight()
    })
    .on('dblclick', (event, d) => { event.stopPropagation(); openNote(d.id) })
    .call(d3Lib.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.25).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d._pinned = true })
    )

  // 球体高光
  highlightSelect = hlG.selectAll('circle').data(currentNodes).join('circle')
    .attr('class', 'g-node-highlight')
    .attr('r', d => nodeRadius(d))
    .attr('fill', 'url(#g-sphere-hl)')
    .attr('opacity', d => highlightOpacity(d))
    .attr('pointer-events', 'none')

  // 标签
  labelSelect = labelG.selectAll('text').data(currentNodes).join('text')
    .attr('class', 'g-node-label')
    .text(d => d.name.length > 22 ? d.name.slice(0, 20) + '…' : d.name)
    .attr('text-anchor', 'middle')
    .attr('font-size', d => Math.max(10, Math.min(13, nodeRadius(d) * 0.95)) + 'px')
    .attr('font-weight', d => (activeId.value && d.id === activeId.value) ? '700' : '500')
    .attr('fill', theme.isDark ? '#e8edf7' : '#334155')
    .attr('stroke', theme.isDark ? '#0b0e17' : '#ffffff')
    .attr('stroke-width', '3.2px')
    .attr('paint-order', 'stroke')
    .attr('stroke-linejoin', 'round')
    .attr('pointer-events', 'none')
    .style('opacity', d => labelOpacity(d))

  simRunning.value = true
  updateHighlight()
  updateLabelVisibility()
}

function curvePath(s, t) {
  const dx = t.x - s.x, dy = t.y - s.y
  const dr = Math.sqrt(dx * dx + dy * dy)
  if (dr < 1) return `M${s.x},${s.y}L${t.x},${t.y}`
  const sweep = Math.min(dr * 0.16, 36)
  const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
  const nx = -dy / dr, ny = dx / dr
  const cx = mx + nx * sweep * 0.4, cy = my + ny * sweep * 0.4
  return `M${s.x},${s.y}Q${cx},${cy} ${t.x},${t.y}`
}

// ═══════════════════════════════════════════════════════════
//  高亮更新
// ═══════════════════════════════════════════════════════════
function updateHighlight() {
  if (!nodeSelect) return
  const id = activeId.value
  nodeSelect
    .attr('opacity', d => nodeOpacity(d))
    .attr('stroke', d => {
      if (d.id === focusId.value) return theme.isDark ? '#fff' : '#7c3aed'
      return theme.isDark ? 'rgba(255,255,255,0.75)' : 'rgba(255,255,255,0.9)'
    })
    .attr('stroke-width', d => d.id === focusId.value ? 2.5 : 1.6)
    .attr('r', d => {
      const base = nodeRadius(d)
      return (id && d.id === id) ? base * 1.4 : base
    })
    // 发光滤镜只作用于激活节点：给几十个邻接节点同时挂 feGaussianBlur
    // 是 hover 卡顿的主因，邻接节点用光晕透明度表达即可
    .attr('filter', d => (id && d.id === id) ? 'url(#g-glow-focus)' : null)

  haloSelect
    .attr('opacity', d => haloOpacity(d))
    .attr('r', d => (id && d.id === id) ? nodeRadius(d) * 2.9 : nodeRadius(d) * 2.4)

  if (highlightSelect) {
    highlightSelect
      .attr('opacity', d => highlightOpacity(d))
      .attr('r', d => {
        const base = nodeRadius(d)
        return (id && d.id === id) ? base * 1.4 : base
      })
  }

  linkSelect
    .attr('stroke-opacity', d => linkOpacity(d))
    .attr('stroke-width', d => linkWidth(d))
    .attr('stroke', d => linkColor(d))

  labelSelect
    .style('opacity', d => labelOpacity(d))
    .attr('font-weight', d => (id && d.id === id) ? '700' : '500')
}

function updateLabelVisibility() {
  if (!labelSelect) return
  labelSelect.style('opacity', d => labelOpacity(d))
}

// ═══════════════════════════════════════════════════════════
//  浮动提示卡（含边界检测）
// ═══════════════════════════════════════════════════════════
function showTooltip(event, d) {
  tooltip.value = {
    show: true, x: 0, y: 0,
    name: d.name, cat: d.cat, degree: d.degree, tags: d.tags,
    color: d.color, glow: d.glow,
  }
  moveTooltip(event)
}
function moveTooltip(event) {
  if (!tooltip.value.show || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  let x = event.clientX - rect.left + 16
  let y = event.clientY - rect.top + 16
  // 边界检测（近似，tooltip 宽~260 高~120）
  if (x + 260 > rect.width - 8) x = event.clientX - rect.left - 260 - 16
  if (y + 120 > rect.height - 8) y = event.clientY - rect.top - 120 - 16
  tooltip.value.x = x
  tooltip.value.y = y
}
function hideTooltip() { tooltip.value.show = false }

// ═══════════════════════════════════════════════════════════
//  操作
// ═══════════════════════════════════════════════════════════
function openNote(id) {
  router.push('/')
  sessionStorage.setItem('graph_open_note', id)
}

function toggleSim() {
  if (!simulation) return
  if (simRunning.value) { simulation.stop(); simRunning.value = false }
  else { simulation.alpha(0.3).restart(); simRunning.value = true }
}

function recenter() {
  if (!svgSelect || !zoomBehavior || !d3ZoomIdentity) return
  svgSelect.transition().duration(600).call(zoomBehavior.transform, d3ZoomIdentity)
}
function zoomIn() { if (svgSelect && zoomBehavior) svgSelect.transition().duration(220).call(zoomBehavior.scaleBy, 1.4) }
function zoomOut() { if (svgSelect && zoomBehavior) svgSelect.transition().duration(220).call(zoomBehavior.scaleBy, 0.7) }

function resetView() {
  currentNodes = []
  currentLinks = []
  focusId.value = null
  hoverId.value = null
  if (simulation) simulation.stop()
  if (svgRef.value) initGraph()
}

function releasePinned() {
  if (!currentNodes.length) return
  currentNodes.forEach(d => { d.fx = null; d.fy = null; d._pinned = false })
  if (simulation) simulation.alpha(0.4).restart()
  simRunning.value = true
}

function searchSubmit() {
  const q = filteredData.value.q
  if (!q || !currentNodes.length) return
  const match = currentNodes.find(n => n.name.toLowerCase().includes(q))
  if (match && svgSelect && zoomBehavior && d3ZoomIdentity) {
    const c = containerRef.value
    const scale = 1.6
    const tx = c.clientWidth / 2 - match.x * scale
    const ty = c.clientHeight / 2 - match.y * scale
    svgSelect.transition().duration(650)
      .call(zoomBehavior.transform, d3ZoomIdentity.translate(tx, ty).scale(scale))
    focusId.value = match.id
    updateHighlight()
  }
}

function togglePanel() {
  panelOpen.value = !panelOpen.value
}

// 键盘快捷键
function onKeydown(e) {
  if (e.target.tagName === 'INPUT') return
  if (e.key === '+' || e.key === '=') zoomIn()
  else if (e.key === '-') zoomOut()
  else if (e.key === '0') recenter()
  else if (e.key === ' ') { e.preventDefault(); toggleSim() }
  else if (e.key === 'Escape') { focusId.value = null; updateHighlight() }
}

// 窗口 resize
function onResize() {
  if (simulation && containerRef.value) {
    const c = containerRef.value
    simulation
      .force('center', d3Lib.forceCenter(c.clientWidth / 2, c.clientHeight / 2).strength(physics.value.centerStrength))
      .force('x', d3Lib.forceX(c.clientWidth / 2).strength(0.04))
      .force('y', d3Lib.forceY(c.clientHeight / 2).strength(0.04))
      .alpha(0.3).restart()
  }
}

// ───────── watch ─────────
// 壁纸开关变化时实时调整 SVG 背景层透明度，无需重新初始化图谱
watch(wallpaperOn, (on) => {
  if (!svgRef.value || !d3Lib) return
  const svg = d3Lib.select(svgRef.value)
  svg.select('.g-bg').attr('opacity', on ? 0.12 : 1)
  svg.select('.g-vig').attr('opacity', on ? 0.4 : 1)
})

watch(physics, () => {
  if (!simulation) return
  const p = physics.value
  simulation
    .force('link', simulation.force('link').distance(p.linkDistance).strength(p.linkStrength))
    .force('charge', simulation.force('charge').strength(p.repel))
    .force('center', simulation.force('center').strength(p.centerStrength))
    .force('collision', d3Lib.forceCollide().radius(d => nodeRadius(d) + p.collision))
    .alpha(0.3).restart()
}, { deep: true })

watch([selectedCat, showOrphans], () => {
  if (!svgRef.value || !gSelect) return
  const c = containerRef.value
  if (!c) return
  const linkG = gSelect.select('.g-links')
  const haloG = gSelect.select('.g-halos')
  const nodeG = gSelect.select('.g-nodes')
  const hlG = gSelect.select('.g-highlights')
  const labelG = gSelect.select('.g-labels')
  buildSimulation(c.clientWidth, c.clientHeight, linkG, haloG, nodeG, hlG, labelG)
})

// 搜索：输入时清除聚焦/悬停，让搜索高亮优先
watch(searchQuery, (v) => {
  if (v.trim()) { focusId.value = null; hoverId.value = null }
  updateHighlight()
  updateLabelVisibility()
})

watch(showLabels, () => updateLabelVisibility())

// 主题切换 / 预设切换：重建图谱（SVG defs 背景渐变、标签颜色、连线颜色都需要重新生成）
watch([() => theme.isDark, () => theme.themeVersion], () => {
  if (svgRef.value) initGraph()
})

onMounted(async () => {
  if (!notes.items.length) await notes.load()
  await nextTick()
  initGraph()
  window.addEventListener('resize', onResize)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  if (simulation) simulation.stop()
  window.removeEventListener('resize', onResize)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="graph-page" :class="{ dark: theme.isDark }">
    <!-- ═══ 顶栏 ═══ -->
    <header class="topbar">
      <div class="topbar-title" role="button" tabindex="0" title="返回首页" @click="router.push('/')" @keydown.enter.prevent="router.push('/')">
        <span class="title-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v3M12 13l-5 4M12 13l5 4"/></svg>
        </span>
        <div>
          <h1>笔记图谱</h1>
          <div class="sub">关系网络 · Obsidian 风格</div>
        </div>
      </div>
      <span class="stats">
        <span class="stats-num">{{ filteredData.nodes.length }}</span> 节点
        <span class="stats-dot"></span>
        <span class="stats-num">{{ filteredData.links.length }}</span> 链接
      </span>

      <div class="topbar-controls">
        <div class="search-wrap">
          <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
          <input v-model="searchQuery" class="search" placeholder="搜索节点…" @keydown.enter="searchSubmit" />
        </div>
        <button @click="zoomIn" class="icon-btn" title="放大 (+)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        </button>
        <button @click="zoomOut" class="icon-btn" title="缩小 (-)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 12h14"/></svg>
        </button>
        <button @click="recenter" class="icon-btn" title="居中复位 (0)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>
        </button>
        <button @click="toggleSim" class="icon-btn" :class="{ active: simRunning }" :title="simRunning ? '暂停 (空格)' : '继续 (空格)'">
          <svg v-if="simRunning" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5l12 7-12 7z"/></svg>
        </button>
        <button @click="releasePinned" class="icon-btn" title="释放固定节点">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18M3 12l4-4M3 12l4 4"/></svg>
        </button>
        <button @click="resetView" class="icon-btn" title="重置图谱">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>
        </button>
        <button @click="togglePanel" class="icon-btn" :class="{ active: panelOpen }" title="切换面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
        </button>
      </div>
    </header>

    <div class="body">
      <!-- ═══ 浮层面板 ═══ -->
      <aside class="panel" :class="{ hidden: !panelOpen }">
        <div class="panel-section">
          <div class="panel-label">
            <span>分类过滤</span>
            <span class="count-badge">{{ categories.length }}</span>
          </div>
          <div class="cat-item" :class="{ active: !selectedCat }" @click="selectedCat = ''">
            <span class="cat-dot" style="background:linear-gradient(135deg,#a78bfa,#22d3ee)"></span>
            <span class="cat-name">全部</span>
            <span class="cat-count">{{ graphData.nodes.length }}</span>
          </div>
          <div
            v-for="c in categories" :key="c.name"
            class="cat-item" :class="{ active: selectedCat === c.name }"
            @click="selectedCat = selectedCat === c.name ? '' : c.name"
          >
            <span class="cat-dot" :style="{ background: c.color, boxShadow: `0 0 8px ${c.color}88` }"></span>
            <span class="cat-name">{{ c.icon }} {{ c.name }}</span>
            <span class="cat-count">{{ c.count }}</span>
          </div>
        </div>

        <div class="panel-section">
          <div class="panel-label">显示选项</div>
          <label class="toggle">
            <input type="checkbox" v-model="showLabels" />
            <span class="toggle-track"><span class="toggle-thumb"></span></span>
            <span class="toggle-label">显示标签</span>
          </label>
          <label class="toggle">
            <input type="checkbox" v-model="showOrphans" />
            <span class="toggle-track"><span class="toggle-thumb"></span></span>
            <span class="toggle-label">显示孤立节点</span>
          </label>
        </div>

        <div class="panel-section">
          <div class="panel-label collapsible" @click="physicsOpen = !physicsOpen">
            <span>力学参数</span>
            <svg class="chev" :class="{ open: physicsOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
          </div>
          <div v-if="physicsOpen" class="physics">
            <div class="slider-row">
              <span class="slider-name">排斥力</span>
              <input type="range" min="-800" max="-50" v-model.number="physics.repel" class="slider" />
              <span class="slider-val">{{ physics.repel }}</span>
            </div>
            <div class="slider-row">
              <span class="slider-name">链接距离</span>
              <input type="range" min="20" max="220" v-model.number="physics.linkDistance" class="slider" />
              <span class="slider-val">{{ physics.linkDistance }}</span>
            </div>
            <div class="slider-row">
              <span class="slider-name">链接强度</span>
              <input type="range" min="0" max="1" step="0.05" v-model.number="physics.linkStrength" class="slider" />
              <span class="slider-val">{{ physics.linkStrength.toFixed(2) }}</span>
            </div>
            <div class="slider-row">
              <span class="slider-name">向心力</span>
              <input type="range" min="0" max="1" step="0.05" v-model.number="physics.centerStrength" class="slider" />
              <span class="slider-val">{{ physics.centerStrength.toFixed(2) }}</span>
            </div>
          </div>
        </div>

        <div v-if="focusNode" class="panel-section">
          <div class="focus-info">
            <div class="focus-head">
              <span class="focus-dot" :style="{ background: focusNode.color, color: focusNode.glow }"></span>
              <span class="focus-name">{{ focusNode.name }}</span>
            </div>
            <div class="focus-meta">
              <span class="focus-cat">{{ focusNode.cat }}</span>
              <span class="focus-sep">·</span>
              <span>{{ focusNode.degree }} 条链接</span>
            </div>
            <div v-if="focusNode.tags.length" class="focus-tags">
              <span v-for="t in focusNode.tags.slice(0, 6)" :key="t" class="tag">#{{ t }}</span>
            </div>
            <button class="open-btn" @click="openNote(focusNode.id)">
              打开笔记
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8"/></svg>
            </button>
          </div>
        </div>

        <div class="panel-section">
          <div class="tips">
            <div class="tip"><kbd>滚轮</kbd> 缩放视图</div>
            <div class="tip"><kbd>拖拽空白</kbd> 平移画布</div>
            <div class="tip"><kbd>拖节点</kbd> 固定位置</div>
            <div class="tip"><kbd>单击</kbd> 聚焦 · <kbd>双击</kbd> 打开</div>
            <div class="tip"><kbd>悬停</kbd> 高亮邻域</div>
            <div class="tip"><kbd>空格</kbd> 暂停 · <kbd>Esc</kbd> 取消</div>
          </div>
        </div>
      </aside>

      <!-- ═══ 画布 ═══ -->
      <main ref="containerRef" class="canvas">
        <div v-if="loading" class="loading">
          <div class="spinner"></div>
          <span>加载图谱数据…</span>
        </div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <svg ref="svgRef" class="svg"></svg>

        <!-- 浮动提示卡 -->
        <div class="tooltip" :class="{ show: tooltip.show }" :style="{ transform: `translate(${tooltip.x}px, ${tooltip.y}px)` }">
          <div class="tooltip-head">
            <span class="tooltip-dot" :style="{ background: tooltip.color, color: tooltip.glow }"></span>
            <span class="tooltip-name">{{ tooltip.name }}</span>
          </div>
          <div class="tooltip-meta">
            <span class="tooltip-cat">{{ tooltip.cat }}</span>
            <span class="tooltip-sep">·</span>
            <span>{{ tooltip.degree }} 条链接</span>
          </div>
          <div v-if="tooltip.tags && tooltip.tags.length" class="tooltip-tags">
            <span v-for="t in tooltip.tags.slice(0, 5)" :key="t" class="tag">#{{ t }}</span>
          </div>
        </div>

        <div class="zoom-badge">{{ Math.round(currentZoom * 100) }}%</div>

        <!-- 图例（面板收起时显示） -->
        <div class="legend" :class="{ show: !panelOpen }">
          <div class="legend-title">分类</div>
          <div class="legend-item" :class="{ active: !selectedCat }" @click="selectedCat = ''">
            <span class="cat-dot" style="background:linear-gradient(135deg,#a78bfa,#22d3ee)"></span>全部
          </div>
          <div
            v-for="c in categories" :key="c.name"
            class="legend-item" :class="{ active: selectedCat === c.name }"
            @click="selectedCat = selectedCat === c.name ? '' : c.name"
          >
            <span class="cat-dot" :style="{ background: c.color, boxShadow: `0 0 8px ${c.color}88` }"></span>{{ c.name }}
          </div>
        </div>

        <!-- 状态栏 -->
        <div class="status-bar">
          <span class="status-dot"></span>
          <span>{{ simRunning ? '力导向布局运行中' : '力学布局已暂停' }}</span>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 设计令牌：浅色为默认，深色用 .dark 修饰（Obsidian-inspired） ═══ */
.graph-page {
  /* 浅色主题 */
  --bg-0: #f4f6fb;
  --bg-1: #eaeef6;
  --bg-2: #ffffff;
  --panel-bg: rgba(255, 255, 255, 0.82);
  --panel-border: rgba(100, 116, 139, 0.16);
  --panel-shadow: 0 12px 40px rgba(15, 23, 42, 0.10), 0 1px 0 rgba(255, 255, 255, 0.5) inset;
  --text: #1e293b;
  --text-2: #475569;
  --text-3: #94a3b8;
  --text-4: #cbd5e1;
  --accent: #7c3aed;
  --accent-2: #0891b2;
  --hover: rgba(100, 116, 139, 0.08);
  --active: rgba(124, 58, 237, 0.10);
  --line: rgba(100, 116, 139, 0.16);
  --status-dot: #10b981;
  --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;

  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  /* 用全局 --bg（壁纸启用时会被淡化半透明，保证壁纸全页面生效） */
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  -webkit-font-smoothing: antialiased;
}

/* ═══ 深色主题覆盖 ═══ */
.graph-page.dark {
  --bg-0: #0b0e17;
  --bg-1: #0f1422;
  --bg-2: #161c2e;
  --panel-bg: rgba(20, 26, 42, 0.72);
  --panel-border: rgba(120, 138, 180, 0.16);
  --panel-shadow: 0 12px 40px rgba(0, 0, 0, 0.55), 0 1px 0 rgba(255, 255, 255, 0.04) inset;
  --text: #e8edf7;
  --text-2: #aab4cc;
  --text-3: #6b7691;
  --text-4: #4a5269;
  --accent: #a78bfa;
  --accent-2: #22d3ee;
  --hover: rgba(120, 138, 180, 0.10);
  --active: rgba(167, 139, 250, 0.14);
  --line: rgba(120, 138, 180, 0.16);
}

/* ═══ 顶栏 ═══ */
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--panel-border);
  background: var(--panel-bg);
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  flex-shrink: 0;
  z-index: 30;
  position: relative;
}
.topbar::after {
  content: '';
  position: absolute;
  left: 0; right: 0; bottom: -1px; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(124, 58, 237, 0.3) 30%, rgba(8, 145, 178, 0.25) 70%, transparent);
  opacity: 0.6;
}
.graph-page.dark .topbar::after {
  background: linear-gradient(90deg, transparent, rgba(167, 139, 250, 0.35) 30%, rgba(34, 211, 238, 0.3) 70%, transparent);
  opacity: 0.5;
}

.topbar-title { display: flex; align-items: center; gap: 10px; cursor: pointer; border-radius: 9px; padding: 4px 8px; margin: -4px -8px; transition: background 0.18s; }
.topbar-title:hover { background: rgba(167, 139, 250, 0.08); }
.topbar-title:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.title-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 9px;
  background: linear-gradient(135deg, #a78bfa 0%, #22d3ee 100%);
  color: #fff;
  box-shadow: 0 4px 14px rgba(167, 139, 250, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}
.topbar-title h1 { font-size: 16px; font-weight: 700; color: var(--text); letter-spacing: -0.3px; margin: 0; }
.topbar-title .sub { font-size: 11px; color: var(--text-3); margin-top: 1px; letter-spacing: 0.2px; }

.stats {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-3);
  padding: 5px 11px; border-radius: 20px;
  background: rgba(120, 138, 180, 0.06);
  border: 1px solid var(--panel-border);
  font-variant-numeric: tabular-nums;
}
.stats-num { color: var(--text); font-weight: 700; }
.stats-dot { width: 3px; height: 3px; border-radius: 50%; background: var(--text-4); }

.topbar-controls { margin-left: auto; display: flex; align-items: center; gap: 7px; }

.search-wrap { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 11px; color: var(--text-3); pointer-events: none; }
.search {
  width: 180px; padding: 8px 12px 8px 32px;
  font-size: 13px; border-radius: 10px;
  border: 1px solid var(--panel-border);
  background: rgba(120, 138, 180, 0.05);
  color: var(--text); outline: none;
  transition: all 0.2s cubic-bezier(.4, 0, .2, 1);
  font-family: var(--font);
}
.search::placeholder { color: var(--text-4); }
.search:focus {
  border-color: rgba(167, 139, 250, 0.55);
  background: rgba(167, 139, 250, 0.06);
  box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.12);
  width: 220px;
}
.search-wrap:focus-within .search-icon { color: var(--accent); }

.icon-btn {
  width: 34px; height: 34px; border-radius: 10px;
  border: 1px solid var(--panel-border);
  background: rgba(120, 138, 180, 0.05);
  color: var(--text-2); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s cubic-bezier(.4, 0, .2, 1);
}
.icon-btn:hover {
  border-color: rgba(167, 139, 250, 0.5);
  color: var(--accent);
  background: rgba(167, 139, 250, 0.1);
  transform: translateY(-1px);
}
.icon-btn:active { transform: translateY(0) scale(0.94); }
.icon-btn.active {
  background: rgba(167, 139, 250, 0.16);
  border-color: rgba(167, 139, 250, 0.5);
  color: var(--accent);
}

/* ═══ 主体 ═══ */
.body { flex: 1; display: flex; position: relative; min-height: 0; }

/* ═══ 浮层面板 ═══ */
.panel {
  position: absolute; left: 16px; top: 16px;
  width: 244px; max-height: calc(100% - 64px);
  overflow-y: auto; padding: 16px;
  border-radius: 16px;
  background: var(--panel-bg);
  backdrop-filter: blur(24px) saturate(150%);
  -webkit-backdrop-filter: blur(24px) saturate(150%);
  border: 1px solid var(--panel-border);
  box-shadow: var(--panel-shadow);
  z-index: 20;
  transition: transform 0.32s cubic-bezier(.4, 0, .2, 1), opacity 0.32s;
}
.panel.hidden { transform: translateX(-280px); opacity: 0; pointer-events: none; }

.panel-section { margin-bottom: 18px; }
.panel-section:last-child { margin-bottom: 0; }

.panel-label {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 10.5px; font-weight: 700; color: var(--text-3);
  margin-bottom: 9px; text-transform: uppercase; letter-spacing: 0.8px;
}
.count-badge {
  font-size: 10px; color: var(--text-4);
  font-variant-numeric: tabular-nums;
  background: rgba(120, 138, 180, 0.08);
  padding: 1px 7px; border-radius: 8px; letter-spacing: 0;
}
.collapsible { cursor: pointer; user-select: none; }
.collapsible:hover { color: var(--accent); }
.chev { transition: transform 0.2s; opacity: 0.6; }
.chev.open { transform: rotate(90deg); }

.cat-item {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 9px; border-radius: 9px; cursor: pointer;
  font-size: 12.5px; color: var(--text-2);
  transition: all 0.15s; margin-bottom: 2px; position: relative;
}
.cat-item:hover { background: var(--hover); color: var(--text); }
.cat-item.active { background: var(--active); color: var(--text); }
.cat-item.active::before {
  content: ''; position: absolute; left: 0; top: 50%;
  transform: translateY(-50%); width: 3px; height: 16px;
  border-radius: 0 3px 3px 0; background: var(--accent);
}
.cat-dot {
  width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.2);
}
.cat-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.cat-count {
  font-size: 11px; color: var(--text-3);
  font-variant-numeric: tabular-nums;
  background: rgba(120, 138, 180, 0.08);
  padding: 1px 7px; border-radius: 8px;
  min-width: 22px; text-align: center;
}
.cat-item.active .cat-count { background: rgba(167, 139, 250, 0.22); color: var(--accent); }

.toggle {
  display: flex; align-items: center; gap: 10px;
  font-size: 12.5px; color: var(--text-2); cursor: pointer;
  padding: 5px 9px; border-radius: 8px; transition: background 0.15s;
}
.toggle:hover { background: var(--hover); color: var(--text); }
.toggle input { display: none; }
.toggle-track {
  width: 34px; height: 19px; border-radius: 11px;
  background: rgba(120, 138, 180, 0.2); position: relative;
  transition: background 0.22s; flex-shrink: 0;
}
.toggle-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 15px; height: 15px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  transition: transform 0.22s cubic-bezier(.4, 0, .2, 1);
}
.toggle input:checked + .toggle-track { background: linear-gradient(135deg, #a78bfa, #22d3ee); }
.toggle input:checked + .toggle-track .toggle-thumb { transform: translateX(15px); }
.toggle-label { flex: 1; }

.physics { margin-top: 4px; }
.slider-row { display: flex; align-items: center; gap: 9px; margin-bottom: 10px; }
.slider-row:last-child { margin-bottom: 0; }
.slider-name { font-size: 11px; color: var(--text-3); width: 62px; flex-shrink: 0; }
.slider {
  flex: 1; height: 4px; cursor: pointer;
  -webkit-appearance: none; appearance: none;
  background: rgba(120, 138, 180, 0.2); border-radius: 2px; outline: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); cursor: pointer;
  box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.18); transition: box-shadow 0.15s;
}
.slider::-webkit-slider-thumb:hover { box-shadow: 0 0 0 5px rgba(167, 139, 250, 0.25); }
.slider::-moz-range-thumb {
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); cursor: pointer; border: none;
}
.slider-val {
  font-size: 11px; color: var(--text); width: 38px; text-align: right;
  font-variant-numeric: tabular-nums; flex-shrink: 0; font-family: var(--mono);
}

.focus-info {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.1), rgba(34, 211, 238, 0.06));
  border-radius: 12px; padding: 13px;
  border: 1px solid rgba(167, 139, 250, 0.2);
  animation: focusIn 0.3s cubic-bezier(.4, 0, .2, 1);
}
@keyframes focusIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
.focus-head { display: flex; align-items: center; gap: 9px; margin-bottom: 7px; }
.focus-dot {
  width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.15), 0 0 12px currentColor;
}
.focus-name {
  font-size: 13.5px; font-weight: 700; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.focus-meta { font-size: 11px; color: var(--text-3); margin-bottom: 9px; display: flex; align-items: center; gap: 5px; }
.focus-cat { color: var(--accent); font-weight: 600; }
.focus-sep { opacity: 0.4; }
.focus-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 11px; }
.tag {
  font-size: 10.5px; color: var(--accent-2);
  background: rgba(34, 211, 238, 0.1);
  border: 1px solid rgba(34, 211, 238, 0.2);
  padding: 1px 7px; border-radius: 8px; font-weight: 500;
}
.open-btn {
  width: 100%; padding: 8px; font-size: 12px; font-weight: 600;
  border-radius: 8px; border: none; cursor: pointer;
  background: linear-gradient(135deg, #a78bfa, #22d3ee); color: #fff;
  transition: all 0.18s; font-family: var(--font);
  display: flex; align-items: center; justify-content: center; gap: 5px;
  box-shadow: 0 4px 12px rgba(167, 139, 250, 0.3);
}
.open-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(167, 139, 250, 0.4); }

.tips { font-size: 11px; color: var(--text-3); line-height: 2; border-top: 1px solid var(--panel-border); padding-top: 12px; }
.tip { display: flex; align-items: center; gap: 7px; }
kbd {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 5px;
  background: rgba(120, 138, 180, 0.1);
  border: 1px solid var(--panel-border);
  color: var(--text-2); box-shadow: 0 1px 0 rgba(0, 0, 0, 0.3);
  min-width: 18px; text-align: center;
}

/* ═══ 画布 ═══ */
.canvas { flex: 1; position: relative; overflow: hidden; background: transparent; }
.svg { width: 100%; height: 100%; display: block; cursor: grab; }
.svg:active { cursor: grabbing; }

.loading {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  font-size: 13px; color: var(--text-3); z-index: 5;
}
.spinner {
  width: 28px; height: 28px; border: 2.5px solid var(--panel-border);
  border-top-color: var(--accent); border-radius: 50%;
  animation: gspin 0.7s linear infinite;
}
@keyframes gspin { to { transform: rotate(360deg); } }
.error { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #f87171; z-index: 5; }

/* 浮动提示卡 */
.tooltip {
  position: absolute; top: 0; left: 0; pointer-events: none; z-index: 25;
  min-width: 160px; max-width: 260px; padding: 11px 13px; border-radius: 11px;
  background: var(--panel-bg);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--panel-border);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.04) inset;
  opacity: 0; transition: opacity 0.15s;
}
.tooltip.show { opacity: 1; }
.tooltip-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.tooltip-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.12), 0 0 10px currentColor;
}
.tooltip-name { font-size: 13.5px; font-weight: 700; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tooltip-meta { font-size: 11px; color: var(--text-3); margin-bottom: 7px; display: flex; align-items: center; gap: 5px; }
.tooltip-cat { color: var(--accent); font-weight: 600; }
.tooltip-sep { opacity: 0.4; }
.tooltip-tags { display: flex; flex-wrap: wrap; gap: 4px; }

.zoom-badge {
  position: absolute; right: 16px; bottom: 16px;
  padding: 5px 11px; font-size: 11px; font-weight: 700;
  color: var(--text); font-variant-numeric: tabular-nums; border-radius: 9px;
  background: var(--panel-bg);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--panel-border);
  pointer-events: none; z-index: 12;
  font-family: var(--mono); letter-spacing: 0.3px;
}

.legend {
  position: absolute; left: 16px; top: 16px;
  padding: 13px; border-radius: 13px;
  background: var(--panel-bg);
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  box-shadow: var(--panel-shadow); z-index: 12;
  opacity: 0; transform: translateX(-20px);
  transition: all 0.32s cubic-bezier(.4, 0, .2, 1);
  pointer-events: none; max-height: calc(100% - 64px); overflow-y: auto;
}
.legend.show { opacity: 1; transform: translateX(0); pointer-events: auto; }
.legend-title { font-size: 10px; font-weight: 700; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 9px; }
.legend-item {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 7px; border-radius: 7px; cursor: pointer;
  font-size: 12px; color: var(--text-2); transition: background 0.15s;
}
.legend-item:hover { background: var(--hover); }
.legend-item.active { background: var(--active); color: var(--text); }

.status-bar {
  position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%);
  display: flex; align-items: center; gap: 10px;
  padding: 6px 14px; border-radius: 20px;
  background: var(--panel-bg);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--panel-border);
  font-size: 11px; color: var(--text-3); z-index: 12; pointer-events: none;
}
.status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #10b981; box-shadow: 0 0 8px #10b981;
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

/* 滚动条 */
.panel::-webkit-scrollbar, .legend::-webkit-scrollbar { width: 7px; }
.panel::-webkit-scrollbar-thumb, .legend::-webkit-scrollbar-thumb { background: rgba(120, 138, 180, 0.22); border-radius: 4px; }
.panel::-webkit-scrollbar-thumb:hover, .legend::-webkit-scrollbar-thumb:hover { background: rgba(120, 138, 180, 0.4); }
</style>

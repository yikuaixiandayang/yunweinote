<script setup>
/**
 * 学习路径 DAG 依赖图谱视图组件
 *
 * 从原 LearningPathPage.vue 提取的 d3 渲染层：
 * - d3-force 力导向 / 线性布局
 * - SVG 渲染：径向渐变背景 + 点阵网格 + 暗角 + 三层球体节点 + 有向贝塞尔曲线边
 * - 交互：滚轮缩放、拖拽平移、节点拖拽固定、单击聚焦、双击打开笔记、悬停高亮上下游
 * - 缩放感知标签显隐
 *
 * 数据来自 useLearningPath composable，主题来自 useThemeStore。
 * 双击节点时向父组件 emit('open-note', noteId)。
 */
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useLearningPath } from '../../composables/useLearningPath'
import { useThemeStore } from '../../stores/theme'
import { useNotesStore } from '../../stores/notes'
import { useUserDataStore } from '../../stores/userData'

const emit = defineEmits(['open-note'])
const props = defineProps({
  visible: { type: Boolean, default: true },
})

const {
  graphData, filteredData, categories,
  focusId, hoverId, activeId, upstreamSet, downstreamSet,
  isRead, isFav, topoOrder,
} = useLearningPath()

const theme = useThemeStore()
const notes = useNotesStore()
const userData = useUserDataStore()
const isDark = computed(() => theme.isDark)

const svgRef = ref(null)
const containerRef = ref(null)
const loading = computed(() => notes.loading)
const error = computed(() => notes.error)

// ───────── 本地控制状态 ─────────
const showLabels = ref(true)
const layoutMode = ref('force')
const simRunning = ref(true)
const currentZoom = ref(1)
const themeTransitioning = ref(false)

const tooltip = ref({ show: false, x: 0, y: 0, name: '', cat: '', inDeg: 0, outDeg: 0, tags: [], color: '', glow: '' })

// ───────── d3 实例引用 ─────────
let simulation = null
let zoomBehavior = null
let svgSelect = null
let gSelect = null
let linkSelect = null
let haloSelect = null
let nodeSelect = null
let highlightSelect = null
let labelSelect = null
let markSelect = null
let d3ZoomIdentity = null
let d3Lib = null

let currentNodes = []
let currentLinks = []

// ═══════════════════════════════════════════════════════════
//  主题感知的 SVG 颜色
// ═══════════════════════════════════════════════════════════
const bgStops = computed(() => isDark.value
  ? ['#1a2138', '#10162a', '#070a12']
  : ['#fbfcfe', '#eef2f8', '#e2e8f1'])
const gridColor = computed(() => isDark.value
  ? 'rgba(120,138,180,0.18)'
  : 'rgba(100,116,139,0.14)')
const vignetteStops = computed(() => isDark.value
  ? [{ o: '55%', c: '#000', op: 0 }, { o: '100%', c: '#000', op: 0.55 }]
  : [{ o: '60%', c: '#0f172a', op: 0 }, { o: '100%', c: '#0f172a', op: 0.12 }])
const labelFill = computed(() => isDark.value ? '#e8edf7' : '#334155')
const labelStroke = computed(() => isDark.value ? '#0b0e17' : '#ffffff')
const linkDefaultColor = computed(() => isDark.value ? '#7a8db0' : '#94a3b8')
const linkDimColor = computed(() => isDark.value ? '#3a4663' : '#cbd5e1')

// 上游蓝 / 下游橙（与主题无关，固定鲜明色）
const UP_COLOR = '#3b82f6'
const UP_GLOW = '#60a5fa'
const DOWN_COLOR = '#f59e0b'
const DOWN_GLOW = '#fbbf24'

function cssSafe(name) { return String(name).replace(/[^a-zA-Z0-9]/g, '-') }

// ═══════════════════════════════════════════════════════════
//  尺寸 / 透明度 / 状态计算
// ═══════════════════════════════════════════════════════════
function nodeRadius(n) { return 5 + Math.min(Math.sqrt(n.inDeg + n.outDeg) * 2.6, 16) }

function nodeState(n) {
  const q = filteredData.value.q
  if (q && !n.name.toLowerCase().includes(q)) return 'dim'
  if (!activeId.value) return 'normal'
  if (n.id === activeId.value) return 'active'
  if (upstreamSet.value.has(n.id)) return 'up'
  if (downstreamSet.value.has(n.id)) return 'down'
  return 'dim'
}

function nodeOpacity(n) {
  const s = nodeState(n)
  if (s === 'dim') return 0.06
  if (!isRead(n)) return 0.5
  return 1
}
function nodeStroke(n) {
  if (isFav(n)) return '#fbbf24'
  const s = nodeState(n)
  if (s === 'active') return '#fff'
  if (s === 'up') return UP_GLOW
  if (s === 'down') return DOWN_GLOW
  return 'rgba(255,255,255,0.75)'
}
function nodeStrokeWidth(n) {
  if (isFav(n)) return 2.5
  const s = nodeState(n)
  if (s === 'active') return 2.6
  if (s === 'up' || s === 'down') return 2.2
  return 1.6
}
function haloOpacity(n) {
  if (!isRead(n)) return 0
  const s = nodeState(n)
  if (s === 'active') return 0.7
  if (s === 'up' || s === 'down') return 0.45
  if (s === 'dim') return 0.03
  return 0.16
}
function highlightOpacity(n) {
  const s = nodeState(n)
  if (s === 'dim') return 0.05
  return 0.6
}

function linkState(l) {
  const q = filteredData.value.q
  const s = typeof l.source === 'object' ? l.source.id : l.source
  const t = typeof l.target === 'object' ? l.target.id : l.target
  if (q) {
    const sNode = graphData.value.nodes.find(n => n.id === s)
    const tNode = graphData.value.nodes.find(n => n.id === t)
    const sMatch = sNode && sNode.name.toLowerCase().includes(q)
    const tMatch = tNode && tNode.name.toLowerCase().includes(q)
    if (!sMatch && !tMatch && !activeId.value) return 'dim'
  }
  if (!activeId.value) return 'default'
  const X = activeId.value
  const up = upstreamSet.value
  const dn = downstreamSet.value
  if (t === X && up.has(s)) return 'up-direct'
  if (s === X && dn.has(t)) return 'down-direct'
  if (up.has(s) && up.has(t)) return 'up-sub'
  if (dn.has(s) && dn.has(t)) return 'down-sub'
  return 'dim'
}

function linkColor(l) {
  const st = linkState(l)
  if (st === 'up-direct' || st === 'up-sub') return UP_COLOR
  if (st === 'down-direct' || st === 'down-sub') return DOWN_COLOR
  if (st === 'dim') return linkDimColor.value
  return linkDefaultColor.value
}
function linkOpacity(l) {
  const st = linkState(l)
  if (st === 'up-direct' || st === 'down-direct') return 0.95
  if (st === 'up-sub' || st === 'down-sub') return 0.55
  if (st === 'dim') return 0.05
  return filteredData.value.q ? 0.13 : 0.22
}
function linkWidth(l) {
  const st = linkState(l)
  if (st === 'up-direct' || st === 'down-direct') return 2.6
  if (st === 'up-sub' || st === 'down-sub') return 1.8
  if (st === 'dim') return 0.6
  return 1.1
}
function linkMarker(l) {
  const st = linkState(l)
  if (st === 'up-direct' || st === 'up-sub') return 'url(#lp-arrow-up)'
  if (st === 'down-direct' || st === 'down-sub') return 'url(#lp-arrow-down)'
  if (st === 'dim') return null
  return 'url(#lp-arrow-default)'
}

function labelOpacity(n) {
  const q = filteredData.value.q
  if (q && n.name.toLowerCase().includes(q)) return 1
  const s = nodeState(n)
  if (s === 'active') return 1
  if (s === 'up' || s === 'down') return 0.95
  if (s === 'dim') {
    if (activeId.value) return 0.03
    if (q) return 0.03
  }
  if (!showLabels.value) return 0
  const z = currentZoom.value
  const deg = n.inDeg + n.outDeg
  const thr = z < 0.5 ? 8 : z < 0.8 ? 4 : z < 1.2 ? 2 : 0
  if (deg < thr) return 0
  return z < 0.5 ? 0.6 : 0.85
}

// ═══════════════════════════════════════════════════════════
//  线性布局：按 topoOrder 推荐学习顺序从上到下垂直排列
// ═══════════════════════════════════════════════════════════
function assignLinearPositions(nodes, width, height) {
  const order = topoOrder.value.items
  if (!order.length) return
  const idToOrder = new Map(order.map((n, i) => [n.id, i]))
  const topMargin = 60
  const bottomMargin = 60
  const usableH = height - topMargin - bottomMargin
  // 动态计算行高：根据节点数量自适应，最小35px，最大80px，确保所有节点都在容器内
  const rowCount = Math.max(1, order.length - 1)
  const idealRowH = usableH / rowCount
  const rowH = Math.max(35, Math.min(80, idealRowH))
  const rankGroups = {}
  nodes.forEach(n => {
    const idx = idToOrder.has(n.id) ? idToOrder.get(n.id) : order.length
    n._linearIdx = idx
    if (!rankGroups[idx]) rankGroups[idx] = []
    rankGroups[idx].push(n)
  })
  // 计算实际总高度，居中布局
  const totalHeight = Object.keys(rankGroups).length * rowH
  const startY = topMargin + (usableH - totalHeight) / 2
  Object.keys(rankGroups).forEach(idx => {
    const group = rankGroups[idx]
    const y = startY + idx * rowH
    const count = group.length
    const spread = count > 1 ? Math.min(width * 0.7, count * 75) : 0
    group.forEach((n, i) => {
      n._linearX = count > 1 ? width / 2 - spread / 2 + (i / (count - 1)) * spread : width / 2
      n._linearY = y
    })
  })
}

// ═══════════════════════════════════════════════════════════
//  分层布局：按 (outDeg - inDeg) 分 NLAYERS 层，赋 _layerY
// ═══════════════════════════════════════════════════════════
const NLAYERS = 6
function assignLayers(nodes, height) {
  const topMargin = 80
  const bottomMargin = 80
  const usableH = height - topMargin - bottomMargin
  const layerH = usableH / (NLAYERS - 1)
  const sorted = [...nodes].sort((a, b) =>
    (b.outDeg - b.inDeg) - (a.outDeg - a.inDeg))
  const perLayer = Math.max(1, Math.ceil(sorted.length / NLAYERS))
  sorted.forEach((n, i) => {
    const layerIdx = Math.min(NLAYERS - 1, Math.floor(i / perLayer))
    n._layer = layerIdx
    n._layerY = topMargin + layerIdx * layerH
  })
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
  if (width < 10 || height < 10) return

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

  // 背景径向渐变
  const bg = defs.append('radialGradient').attr('id', 'lp-bg-grad')
    .attr('cx', '50%').attr('cy', '45%').attr('r', '78%')
  const [bg0, bg1, bg2] = bgStops.value
  bg.append('stop').attr('offset', '0%').attr('stop-color', bg0)
  bg.append('stop').attr('offset', '45%').attr('stop-color', bg1)
  bg.append('stop').attr('offset', '100%').attr('stop-color', bg2)

  // 点阵网格
  const grid = defs.append('pattern').attr('id', 'lp-grid-dots')
    .attr('width', '32').attr('height', '32').attr('patternUnits', 'userSpaceOnUse')
  grid.append('circle').attr('cx', '1').attr('cy', '1').attr('r', '0.9')
    .attr('fill', gridColor.value)

  // 暗角
  const vig = defs.append('radialGradient').attr('id', 'lp-vignette')
    .attr('cx', '50%').attr('cy', '50%').attr('r', '72%')
  const [vig0, vig1] = vignetteStops.value
  vig.append('stop').attr('offset', vig0.o).attr('stop-color', vig0.c).attr('stop-opacity', vig0.op)
  vig.append('stop').attr('offset', vig1.o).attr('stop-color', vig1.c).attr('stop-opacity', vig1.op)

  // 每个分类独立光晕径向渐变
  categories.value.forEach(c => {
    const g = defs.append('radialGradient').attr('id', `lp-halo-${cssSafe(c.name)}`)
      .attr('cx', '50%').attr('cy', '50%').attr('r', '50%')
    g.append('stop').attr('offset', '0%').attr('stop-color', c.glow).attr('stop-opacity', '0.85')
    g.append('stop').attr('offset', '45%').attr('stop-color', c.color).attr('stop-opacity', '0.4')
    g.append('stop').attr('offset', '100%').attr('stop-color', c.color).attr('stop-opacity', '0')
  })

  // 球体高光
  const sph = defs.append('radialGradient').attr('id', 'lp-sphere-hl')
    .attr('cx', '35%').attr('cy', '28%').attr('r', '55%')
  sph.append('stop').attr('offset', '0%').attr('stop-color', '#fff').attr('stop-opacity', '0.9')
  sph.append('stop').attr('offset', '45%').attr('stop-color', '#fff').attr('stop-opacity', '0.25')
  sph.append('stop').attr('offset', '100%').attr('stop-color', '#fff').attr('stop-opacity', '0')

  // 发光滤镜
  const glow = defs.append('filter').attr('id', 'lp-glow-soft')
    .attr('x', '-80%').attr('y', '-80%').attr('width', '260%').attr('height', '260%')
  glow.append('feGaussianBlur').attr('stdDeviation', '2.2').attr('result', 'b')
  const gm = glow.append('feMerge')
  gm.append('feMergeNode').attr('in', 'b')
  gm.append('feMergeNode').attr('in', 'SourceGraphic')

  const fglow = defs.append('filter').attr('id', 'lp-glow-focus')
    .attr('x', '-120%').attr('y', '-120%').attr('width', '340%').attr('height', '340%')
  fglow.append('feGaussianBlur').attr('stdDeviation', '5').attr('result', 'b')
  const fm = fglow.append('feMerge')
  fm.append('feMergeNode').attr('in', 'b')
  fm.append('feMergeNode').attr('in', 'b')
  fm.append('feMergeNode').attr('in', 'SourceGraphic')

  // 箭头 markers
  const markerDefs = [
    { id: 'lp-arrow-default', color: linkDefaultColor.value },
    { id: 'lp-arrow-dim', color: linkDimColor.value },
    { id: 'lp-arrow-up', color: UP_COLOR },
    { id: 'lp-arrow-down', color: DOWN_COLOR },
  ]
  markerDefs.forEach(m => {
    const mk = defs.append('marker').attr('id', m.id)
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 8).attr('refY', 0)
      .attr('markerWidth', 7).attr('markerHeight', 7)
      .attr('orient', 'auto')
    mk.append('path').attr('d', 'M0,-4L8,0L0,4Z').attr('fill', m.color)
  })

  // 背景层
  svgSelect.append('rect').attr('class', 'lp-bg')
    .attr('width', width).attr('height', height).attr('fill', 'url(#lp-bg-grad)')
  svgSelect.append('rect').attr('class', 'lp-grid')
    .attr('width', width).attr('height', height).attr('fill', 'url(#lp-grid-dots)').attr('opacity', 0.7)
  svgSelect.append('rect').attr('class', 'lp-vig')
    .attr('width', width).attr('height', height).attr('fill', 'url(#lp-vignette)').attr('pointer-events', 'none')

  gSelect = svgSelect.append('g').attr('class', 'lp-zoom')

  zoomBehavior = d3Lib.zoom().scaleExtent([0.1, 12])
    .on('zoom', (event) => {
      gSelect.attr('transform', event.transform)
      currentZoom.value = event.transform.k
      updateLabelVisibility()
    })
  svgSelect.call(zoomBehavior)
  svgSelect.on('click', (event) => {
    if (event.target.tagName === 'svg' || event.target.classList.contains('lp-bg') ||
        event.target.classList.contains('lp-grid') || event.target.classList.contains('lp-vig')) {
      focusId.value = null
      updateHighlight()
    }
  })

  const linkG = gSelect.append('g').attr('class', 'lp-links')
  const haloG = gSelect.append('g').attr('class', 'lp-halos')
  const nodeG = gSelect.append('g').attr('class', 'lp-nodes')
  const hlG = gSelect.append('g').attr('class', 'lp-highlights')
  const labelG = gSelect.append('g').attr('class', 'lp-labels')

  buildSimulation(width, height, linkG, haloG, nodeG, hlG, labelG)
}

function buildSimulation(width, height, linkG, haloG, nodeG, hlG, labelG) {
  const data = filteredData.value
  if (!data.nodes.length) { if (simulation) simulation.stop(); return }

  if (layoutMode.value === 'linear') {
    assignLinearPositions(data.nodes, width, height)
  } else {
    assignLayers(data.nodes, height)
  }

  const prev = {}
  if (currentNodes.length) currentNodes.forEach(n => { prev[n.id] = { x: n.x, y: n.y } })
  currentNodes = data.nodes.map(n => {
    const base = { ...n }
    if (layoutMode.value === 'linear') {
      base.x = n._linearX || width / 2
      base.y = n._linearY || height / 2
    } else {
      base.x = width / 2 + (Math.random() - 0.5) * Math.min(width * 0.8, 600)
      base.y = n._layerY + (Math.random() - 0.5) * 20
    }
    if (prev[n.id] && layoutMode.value !== 'linear') { base.x = prev[n.id].x; base.y = prev[n.id].y }
    return base
  })
  currentLinks = data.links.map(l => ({
    source: typeof l.source === 'object' ? l.source.id : l.source,
    target: typeof l.target === 'object' ? l.target.id : l.target,
  }))

  if (simulation) simulation.stop()

  if (layoutMode.value === 'linear') {
    simulation = d3Lib.forceSimulation(currentNodes)
      .force('link', d3Lib.forceLink(currentLinks).id(d => d.id).distance(0).strength(0))
      .force('charge', d3Lib.forceManyBody().strength(0))
      .force('x', d3Lib.forceX(d => d._linearX).strength(1.2))
      .force('y', d3Lib.forceY(d => d._linearY).strength(1.2))
      .force('collision', d3Lib.forceCollide().radius(d => nodeRadius(d) + 8))
      .alphaDecay(0.1)
  } else {
    // force 模式：力导向网状布局。
    // 调优：Y 力从 0.55 降到 0.15（保留分层倾向但不压成竖条），
    //       charge 从 -380 增到 -450（增强排斥让节点横向散开），
    //       link.distance 从 120 升到 140（边更长，图更松散易读）。
    simulation = d3Lib.forceSimulation(currentNodes)
      .force('link', d3Lib.forceLink(currentLinks).id(d => d.id)
        .distance(140).strength(0.25))
      .force('charge', d3Lib.forceManyBody().strength(-450))
      .force('center', d3Lib.forceCenter(width / 2, height / 2).strength(0.04))
      .force('collision', d3Lib.forceCollide().radius(d => nodeRadius(d) + 14))
      .force('x', d3Lib.forceX(width / 2).strength(0.06))
      .force('y', d3Lib.forceY(d => d._layerY).strength(0.15))
      .alphaDecay(0.022)
  }

  simulation.on('tick', () => {
    linkSelect.attr('d', d => directedCurvePath(d.source, d.target))
    haloSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    nodeSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    highlightSelect.attr('cx', d => d.x).attr('cy', d => d.y)
    labelSelect.attr('x', d => d.x).attr('y', d => d.y - nodeRadius(d) - 7)
    if (markSelect) {
      markSelect.attr('transform', d => {
        const r = nodeRadius(d)
        return `translate(${d.x + r * 0.72}, ${d.y - r * 0.72})`
      })
    }
  })

  // 边：贝塞尔曲线 + 箭头
  linkSelect = linkG.selectAll('path').data(currentLinks).join('path')
    .attr('class', 'lp-edge')
    .attr('fill', 'none')
    .attr('stroke', d => linkColor(d))
    .attr('stroke-opacity', d => linkOpacity(d))
    .attr('stroke-width', d => linkWidth(d))
    .attr('stroke-linecap', 'round')
    .attr('marker-end', d => linkMarker(d))
    .attr('pointer-events', 'none')

  // 外光晕
  haloSelect = haloG.selectAll('circle').data(currentNodes).join('circle')
    .attr('class', 'lp-node-halo')
    .attr('r', d => nodeRadius(d) * 2.4)
    .attr('fill', d => `url(#lp-halo-${cssSafe(d.cat)})`)
    .attr('opacity', d => haloOpacity(d))
    .attr('pointer-events', 'none')

  // 节点本体
  nodeSelect = nodeG.selectAll('circle').data(currentNodes).join('circle')
    .attr('class', 'lp-node-core')
    .attr('r', d => nodeRadius(d))
    .attr('fill', d => d.color)
    .attr('stroke', d => nodeStroke(d))
    .attr('stroke-width', d => nodeStrokeWidth(d))
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

  // 球体高光层
  highlightSelect = hlG.selectAll('circle').data(currentNodes).join('circle')
    .attr('class', 'lp-node-highlight')
    .attr('r', d => nodeRadius(d))
    .attr('fill', 'url(#lp-sphere-hl)')
    .attr('opacity', d => highlightOpacity(d))
    .attr('pointer-events', 'none')

  // 标签
  labelSelect = labelG.selectAll('text').data(currentNodes).join('text')
    .attr('class', 'lp-node-label')
    .text(d => d.name.length > 22 ? d.name.slice(0, 20) + '…' : d.name)
    .attr('text-anchor', 'middle')
    .attr('font-size', d => Math.max(10, Math.min(13, nodeRadius(d) * 0.95)) + 'px')
    .attr('font-weight', d => (activeId.value && d.id === activeId.value) ? '700' : '500')
    .attr('fill', labelFill.value)
    .attr('stroke', labelStroke.value)
    .attr('stroke-width', '3.2px')
    .attr('paint-order', 'stroke')
    .attr('stroke-linejoin', 'round')
    .attr('pointer-events', 'none')
    .style('opacity', d => labelOpacity(d))

  simRunning.value = true
  updateHighlight()
  updateLabelVisibility()
  updateMarks()
}

/**
 * 已读节点的 ✓ 标记层（节点右上角小绿圆 + 勾）。
 */
function updateMarks() {
  if (!gSelect) { markSelect = null; return }
  let markG = gSelect.select('.lp-marks')
  if (markG.empty()) {
    markG = gSelect.append('g').attr('class', 'lp-marks')
  }
  markG.selectAll('g.lp-mark').remove()
  const readNodes = currentNodes.filter(n => isRead(n))
  if (!readNodes.length) { markSelect = null; return }
  markSelect = markG.selectAll('g.lp-mark').data(readNodes).enter().append('g')
    .attr('class', 'lp-mark')
    .attr('pointer-events', 'none')
  markSelect.append('circle')
    .attr('r', d => Math.max(4, nodeRadius(d) * 0.42))
    .attr('fill', '#22c55e')
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 1.3)
    .attr('stroke-opacity', 0.95)
  markSelect.append('text')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'central')
    .attr('font-size', d => Math.max(8, nodeRadius(d) * 0.62))
    .attr('font-weight', '700')
    .attr('fill', '#ffffff')
    .attr('font-family', 'system-ui, -apple-system, sans-serif')
    .text('✓')
  markSelect.attr('transform', d => {
    const r = nodeRadius(d)
    return `translate(${d.x + r * 0.72}, ${d.y - r * 0.72})`
  })
}

/**
 * 有向贝塞尔曲线路径：端点缩短到节点圆边缘外，控制点做轻微垂直偏移。
 */
function directedCurvePath(s, t) {
  const dx = t.x - s.x, dy = t.y - s.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  if (dist < 1) return ''
  const ux = dx / dist, uy = dy / dist
  const rS = nodeRadius(s) + 1
  const rT = nodeRadius(t) + 6
  const sx = s.x + ux * rS, sy = s.y + uy * rS
  const tx = t.x - ux * rT, ty = t.y - uy * rT
  const nx = -uy, ny = ux
  const offset = Math.min(dist * 0.12, 28)
  const mx = (sx + tx) / 2 + nx * offset * 0.4
  const my = (sy + ty) / 2 + ny * offset * 0.4
  return `M${sx},${sy}Q${mx},${my} ${tx},${ty}`
}

// ═══════════════════════════════════════════════════════════
//  高亮更新
// ═══════════════════════════════════════════════════════════
function updateHighlight() {
  if (!nodeSelect) return
  const id = activeId.value
  nodeSelect
    .attr('opacity', d => nodeOpacity(d))
    .attr('stroke', d => nodeStroke(d))
    .attr('stroke-width', d => nodeStrokeWidth(d))
    .attr('r', d => {
      const base = nodeRadius(d)
      return (id && d.id === id) ? base * 1.4 : base
    })
    .attr('filter', d => {
      if (!id) return null
      if (d.id === id) return 'url(#lp-glow-focus)'
      const st = nodeState(d)
      if (st === 'up' || st === 'down') return 'url(#lp-glow-soft)'
      return null
    })

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
    .attr('marker-end', d => linkMarker(d))

  labelSelect
    .style('opacity', d => labelOpacity(d))
    .attr('font-weight', d => (id && d.id === id) ? '700' : '500')
}

function updateLabelVisibility() {
  if (!labelSelect) return
  labelSelect.style('opacity', d => labelOpacity(d))
}

// ═══════════════════════════════════════════════════════════
//  浮动提示卡
// ═══════════════════════════════════════════════════════════
function showTooltip(event, d) {
  tooltip.value = {
    show: true, x: 0, y: 0,
    name: d.name, cat: d.cat, inDeg: d.inDeg, outDeg: d.outDeg, tags: d.tags,
    color: d.color, glow: d.glow,
  }
  moveTooltip(event)
}
function moveTooltip(event) {
  if (!tooltip.value.show || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  let x = event.clientX - rect.left + 16
  let y = event.clientY - rect.top + 16
  if (x + 260 > rect.width - 8) x = event.clientX - rect.left - 260 - 16
  if (y + 140 > rect.height - 8) y = event.clientY - rect.top - 140 - 16
  tooltip.value.x = x
  tooltip.value.y = y
}
function hideTooltip() { tooltip.value.show = false }

// ═══════════════════════════════════════════════════════════
//  操作
// ═══════════════════════════════════════════════════════════
function openNote(id) {
  emit('open-note', id)
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

/**
 * 自动计算所有节点的边界框，缩放平移以适应视口
 */
function fitToView(padding = 50) {
  if (!svgSelect || !zoomBehavior || !d3ZoomIdentity || !currentNodes.length) return
  const container = containerRef.value
  if (!container) return
  const cw = container.clientWidth
  const ch = container.clientHeight

  // 计算所有节点的边界
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  currentNodes.forEach(n => {
    const r = nodeRadius(n)
    minX = Math.min(minX, n.x - r)
    minY = Math.min(minY, n.y - r)
    maxX = Math.max(maxX, n.x + r)
    maxY = Math.max(maxY, n.y + r)
  })

  const bw = maxX - minX
  const bh = maxY - minY
  if (bw < 1 || bh < 1) {
    recenter()
    return
  }

  // 计算缩放比例
  const scaleX = (cw - padding * 2) / bw
  const scaleY = (ch - padding * 2) / bh
  const scale = Math.min(scaleX, scaleY, 2.5) // 最大放大2.5倍

  // 计算居中偏移
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const tx = cw / 2 - cx * scale
  const ty = ch / 2 - cy * scale

  svgSelect.transition().duration(600)
    .call(zoomBehavior.transform, d3ZoomIdentity.translate(tx, ty).scale(scale))
}

function zoomIn() { if (svgSelect && zoomBehavior) svgSelect.transition().duration(220).call(zoomBehavior.scaleBy, 1.4) }
function zoomOut() { if (svgSelect && zoomBehavior) svgSelect.transition().duration(220).call(zoomBehavior.scaleBy, 0.7) }

function resetView() {
  currentNodes = []
  currentLinks = []
  focusId.value = null
  hoverId.value = null
  if (simulation) simulation.stop()
  if (svgRef.value) {
    initGraph()
    // 等待模拟稳定后自动适配视图
    setTimeout(() => fitToView(), layoutMode.value === 'linear' ? 100 : 800)
  }
}

function releasePinned() {
  if (!currentNodes.length) return
  currentNodes.forEach(d => { d.fx = null; d.fy = null; d._pinned = false })
  if (simulation) simulation.alpha(0.4).restart()
  simRunning.value = true
}

function setLayout(mode) {
  if (layoutMode.value === mode) return
  layoutMode.value = mode
  resetView()
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

function focusOnNode(id) {
  if (!id) return
  focusId.value = id
  const n = currentNodes.find(x => x.id === id)
  if (n && svgSelect && zoomBehavior && d3ZoomIdentity && containerRef.value) {
    const c = containerRef.value
    const scale = 1.6
    const tx = c.clientWidth / 2 - n.x * scale
    const ty = c.clientHeight / 2 - n.y * scale
    svgSelect.transition().duration(550)
      .call(zoomBehavior.transform, d3ZoomIdentity.translate(tx, ty).scale(scale))
  }
  updateHighlight()
}

function onResize() {
  if (!containerRef.value || !svgRef.value) return
  const c = containerRef.value
  const w = c.clientWidth
  const h = c.clientHeight
  if (w < 10 || h < 10) return

  // 更新SVG viewBox
  svgRef.value.setAttribute('viewBox', `0 0 ${w} ${h}`)

  // 更新背景矩形尺寸
  if (svgSelect) {
    svgSelect.select('.lp-bg').attr('width', w).attr('height', h)
    svgSelect.select('.lp-grid').attr('width', w).attr('height', h)
    svgSelect.select('.lp-vig').attr('width', w).attr('height', h)
  }

  if (simulation) {
    assignLayers(currentNodes, h)
    simulation
      .force('center', d3Lib.forceCenter(w / 2, h / 2).strength(0.04))
      .force('x', d3Lib.forceX(w / 2).strength(0.06))
      .force('y', d3Lib.forceY(d => d._layerY).strength(0.15))
      .alpha(0.3).restart()
  }
}

// ───────── watch ─────────
// 搜索查询变化：仅更新高亮（不重建 simulation）
watch(() => filteredData.value.q, (q) => {
  if (q) { focusId.value = null; hoverId.value = null }
  updateHighlight()
  updateLabelVisibility()
})

// 过滤后的节点集变化（selectedCat / showOrphans / showUnreadOnly 改变）时重建 simulation
const filteredNodeIds = computed(() => filteredData.value.nodes.map(n => n.id).join(','))
watch(filteredNodeIds, () => {
  if (!svgRef.value || !gSelect) return
  const c = containerRef.value
  if (!c) return
  const linkG = gSelect.select('.lp-links')
  const haloG = gSelect.select('.lp-halos')
  const nodeG = gSelect.select('.lp-nodes')
  const hlG = gSelect.select('.lp-highlights')
  const labelG = gSelect.select('.lp-labels')
  buildSimulation(c.clientWidth, c.clientHeight, linkG, haloG, nodeG, hlG, labelG)
})

watch(() => userData.readSet, () => {
  updateHighlight()
  updateMarks()
}, { deep: true })

watch(() => userData.favs, () => {
  updateHighlight()
}, { deep: true })

watch(showLabels, () => updateLabelVisibility())

// 主题切换：淡出 → 重建 → 淡入
watch([() => theme.isDark, () => theme.themeVersion], () => {
  if (!svgRef.value) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    currentNodes = []
    currentLinks = []
    focusId.value = null
    hoverId.value = null
    if (simulation) simulation.stop()
    nextTick(() => initGraph())
    return
  }
  themeTransitioning.value = true
  setTimeout(() => {
    currentNodes = []
    currentLinks = []
    focusId.value = null
    hoverId.value = null
    if (simulation) simulation.stop()
    nextTick(() => {
      initGraph()
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          themeTransitioning.value = false
        })
      })
    })
  }, 300)
})

// 标记是否已初始化过（避免重复 init）
let initialized = false

onMounted(async () => {
  if (!notes.items.length) await notes.load()
  await nextTick()
  if (props.visible) {
    initGraph()
    initialized = true
    // 等待模拟稳定后自动适配视图
    setTimeout(() => fitToView(), layoutMode.value === 'linear' ? 100 : 800)
  }
  window.addEventListener('resize', onResize)
})

// 当组件从隐藏变为可见时，首次初始化图谱
// 需要双帧等待：v-show 切换后浏览器需要两帧才能完成布局计算
watch(() => props.visible, async (val) => {
  if (val && !initialized) {
    await nextTick()
    requestAnimationFrame(() => {
      requestAnimationFrame(async () => {
        await initGraph()
        initialized = true
        // 等待模拟稳定后自动适配视图
        setTimeout(() => fitToView(), layoutMode.value === 'linear' ? 100 : 800)
      })
    })
  }
})

onUnmounted(() => {
  if (simulation) simulation.stop()
  window.removeEventListener('resize', onResize)
})

defineExpose({ focusOnNode, searchSubmit, resetView, fitToView })
</script>

<template>
  <div ref="containerRef" class="dg-canvas">
    <div v-if="loading" class="dg-loading">
      <div class="dg-spinner"></div>
      <span>加载学习路径数据…</span>
    </div>
    <div v-else-if="error" class="dg-error">{{ error }}</div>

    <svg ref="svgRef" class="dg-svg" :class="{ 'theme-transitioning': themeTransitioning }"></svg>

    <!-- 层级轴（左侧垂直，标示进阶/基础方向） -->
    <div class="dg-layer-axis">
      <div class="dg-layer-label top">
        <span class="dg-layer-arrow">▲</span>
        <span>进阶 / 综合</span>
      </div>
      <div class="dg-layer-bar"></div>
      <div class="dg-layer-label bottom">
        <span>基础 / 前置</span>
        <span class="dg-layer-arrow">▼</span>
      </div>
    </div>

    <!-- 浮动控制按钮（右上角） -->
    <div class="dg-controls">
      <div class="dg-layout-switch">
        <button
          :class="{ active: layoutMode === 'linear' }"
          @click="setLayout('linear')"
          title="线性排列：按推荐学习顺序从上到下"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="4" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="20" r="2"/><path d="M12 6v4M12 14v4"/></svg>
          线性
        </button>
        <button
          :class="{ active: layoutMode === 'force' }"
          @click="setLayout('force')"
          title="力导向：节点自由分布"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="14" r="2"/><circle cx="6" cy="20" r="2"/><circle cx="18" cy="20" r="2"/><path d="M8 6h8M7 8l4 4M17 8l-4 4M8 20h8"/></svg>
          力导向
        </button>
      </div>
      <button class="dg-ctrl-btn" @click="zoomIn" title="放大">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
      </button>
      <button class="dg-ctrl-btn" @click="zoomOut" title="缩小">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 12h14"/></svg>
      </button>
      <button class="dg-ctrl-btn" @click="fitToView" title="适应窗口">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
      </button>
      <button class="dg-ctrl-btn" :class="{ active: simRunning }" @click="toggleSim" :title="simRunning ? '暂停' : '继续'">
        <svg v-if="simRunning" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5l12 7-12 7z"/></svg>
      </button>
      <button class="dg-ctrl-btn" @click="releasePinned" title="释放固定节点">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18M3 12l4-4M3 12l4 4"/></svg>
      </button>
      <button class="dg-ctrl-btn" @click="resetView" title="重置布局">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>
      </button>
    </div>

    <!-- 浮动提示卡 -->
    <div class="dg-tooltip" :class="{ show: tooltip.show }" :style="{ transform: `translate(${tooltip.x}px, ${tooltip.y}px)` }">
      <div class="dg-tooltip-head">
        <span class="dg-tooltip-dot" :style="{ background: tooltip.color, color: tooltip.glow }"></span>
        <span class="dg-tooltip-name">{{ tooltip.name }}</span>
      </div>
      <div class="dg-tooltip-meta">
        <span class="dg-tooltip-cat">{{ tooltip.cat }}</span>
        <span class="dg-tooltip-sep">·</span>
        <span>入 {{ tooltip.inDeg }} / 出 {{ tooltip.outDeg }}</span>
      </div>
    </div>

    <div class="dg-zoom-badge">{{ Math.round(currentZoom * 100) }}%</div>

    <!-- 状态栏 -->
    <div class="dg-status-bar">
      <span class="dg-status-dot"></span>
      <span>{{ simRunning ? '布局运行中' : '布局已暂停' }}</span>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 画布容器 ═══ */
.dg-canvas {
  --up: #3b82f6;
  --up-glow: #60a5fa;
  --down: #f59e0b;
  --down-glow: #fbbf24;

  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--bg);
}

.dg-svg {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
  transition: opacity 0.3s ease;
}
.dg-svg:active { cursor: grabbing; }
.dg-svg.theme-transitioning { opacity: 0; }

/* ═══ 层级轴（左侧垂直） ═══ */
.dg-layer-axis {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  z-index: 8;
  pointer-events: none;
  opacity: 0.5;
  transition: opacity 0.3s;
}
.dg-layer-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  writing-mode: vertical-rl;
  text-orientation: mixed;
}
.dg-layer-label.top { color: var(--down); }
.dg-layer-label.bottom { color: var(--up); }
.dg-layer-arrow {
  writing-mode: horizontal-tb;
  font-size: 11px;
  line-height: 1;
}
.dg-layer-bar {
  width: 2px;
  height: 80px;
  border-radius: 1px;
  background: linear-gradient(180deg, var(--down), var(--up));
  opacity: 0.5;
}

/* ═══ 加载 / 错误 ═══ */
.dg-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 13px;
  color: var(--muted);
  z-index: 5;
}
.dg-spinner {
  width: 28px;
  height: 28px;
  border: 2.5px solid var(--line);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: dg-spin 0.7s linear infinite;
}
@keyframes dg-spin { to { transform: rotate(360deg); } }
.dg-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--danger);
  z-index: 5;
}

/* ═══ 浮动控制按钮（右上角） ═══ */
.dg-controls {
  position: absolute;
  right: 16px;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 15;
  padding: 8px;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--card) 72%, transparent);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
}

.dg-layout-switch {
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--hover);
  margin-bottom: 4px;
}
.dg-layout-switch button {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  font-family: inherit;
  background: transparent;
  color: var(--muted);
  transition: color 0.15s, background 0.15s;
}
.dg-layout-switch button:hover {
  color: var(--text);
  background: var(--hover);
}
.dg-layout-switch button.active {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--accent);
}

.dg-ctrl-btn {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.15s, color 0.15s, background 0.15s, transform 0.15s;
}
.dg-ctrl-btn:hover {
  border-color: color-mix(in srgb, var(--accent) 50%, transparent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  transform: translateY(-1px);
}
.dg-ctrl-btn:active { transform: translateY(0) scale(0.94); }
.dg-ctrl-btn.active {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  border-color: color-mix(in srgb, var(--accent) 50%, transparent);
  color: var(--accent);
}

/* ═══ 浮动提示卡 ═══ */
.dg-tooltip {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  z-index: 25;
  min-width: 160px;
  max-width: 260px;
  padding: 11px 13px;
  border-radius: 11px;
  background: color-mix(in srgb, var(--card) 92%, transparent);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-lg);
  opacity: 0;
  transition: opacity 0.15s;
}
.dg-tooltip.show { opacity: 1; }
.dg-tooltip-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.dg-tooltip-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.12), 0 0 10px currentColor;
}
.dg-tooltip-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dg-tooltip-meta {
  font-size: 11px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 5px;
}
.dg-tooltip-cat { color: var(--accent); font-weight: 600; }
.dg-tooltip-sep { opacity: 0.4; }

/* ═══ 缩放徽标 ═══ */
.dg-zoom-badge {
  position: absolute;
  right: 16px;
  bottom: 16px;
  padding: 5px 11px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--card) 78%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--line);
  pointer-events: none;
  z-index: 12;
  font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
  letter-spacing: 0.3px;
}

/* ═══ 状态栏 ═══ */
.dg-status-bar {
  position: absolute;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  border-radius: 20px;
  background: color-mix(in srgb, var(--card) 78%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--line);
  font-size: 11px;
  color: var(--muted);
  z-index: 12;
  pointer-events: none;
}
.dg-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: dg-pulse 2s ease-in-out infinite;
}
@keyframes dg-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>

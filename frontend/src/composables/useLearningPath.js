/**
 * 学习路径共享逻辑 composable
 *
 * 从 LearningPathPage.vue 提取的纯逻辑层：
 * - 有向图构建（graphData）
 * - 环检测（detectCyclicEdges）
 * - 最长路径（computeLongestPath）
 * - 拓扑排序（topoOrder）
 * - 掌握度统计（mastery）
 * - 数据过滤（filteredData）
 * - 上下游 BFS（upstreamSet / downstreamSet / directPredecessors / directSuccessors）
 *
 * 不包含 d3 依赖或 UI 渲染操作（exportLearningOrder 中的锚点下载除外）。
 */
import { computed, ref } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { useStudyPlanStore } from '../stores/studyPlan'
import { CAT_COLORS, CAT_GLOW, CAT_ICONS, isMetaDoc } from '../constants'

// ───────── 模块级共享过滤状态 ─────────
// 多个组件（容器、PathTimeline、DependencyGraph）共享同一份状态
const selectedCat = ref('')
const searchQuery = ref('')
const showOrphans = ref(false)
const showUnreadOnly = ref(false)
const focusId = ref(null)
const hoverId = ref(null)
// P3 续：路径时间线默认只看 recommendPath 内的节点（避免 89 篇噪音淹没 10 步路径）。
// 图谱视图不受此开关影响（图谱看全库依赖关系，探索用）。
// 无 recommendPath 时 pathOrderMap 为空 → pathOnly 自动失效，退回全库（无回归）。
const pathOnly = ref(true)

export function useLearningPath() {
  const notes = useNotesStore()
  const userData = useUserDataStore()
  const studyPlan = useStudyPlanStore()

  // ───────── 分类配置 ─────────
  const catConfig = computed(() => {
    const m = {}
    notes.catOrder.forEach(name => {
      const color = CAT_COLORS[name] || '#64748b'
      const glow = CAT_GLOW[name] || color
      m[name] = { name, color, glow, icon: CAT_ICONS[name] || '📄' }
    })
    return m
  })

  // ═══════════════════════════════════════════════════════════
  //  有向图构建：A.wikilinks 包含 B → A→B（A 引用 B）
  // ═══════════════════════════════════════════════════════════
  const graphData = computed(() => {
    const allNotes = notes.items
    if (!allNotes.length) return { nodes: [], links: [], cyclicCount: 0, longestPath: 0, cyclicEdges: new Set() }

    const idSet = new Set(allNotes.map(n => n.id))
    // 元文档 id 集合：这些节点不产生连线（避免超级枢纽），与 /graph 行为一致
    const metaIds = new Set(allNotes.filter(n => isMetaDoc(n)).map(n => n.id))
    const links = []
    const linkSet = new Set()
    for (const n of allNotes) {
      // 元文档跳过出向链接
      if (metaIds.has(n.id)) continue
      for (const tid of (n.wikilinks || [])) {
        if (!idSet.has(tid) || tid === n.id) continue
        // 也不连向元文档（避免其他笔记 -> 审计报告的入向边）
        if (metaIds.has(tid)) continue
        const key = `${n.id}|${tid}`
        if (linkSet.has(key)) continue
        linkSet.add(key)
        links.push({ source: n.id, target: tid })
      }
    }

    const inDeg = {}, outDeg = {}
    for (const l of links) {
      outDeg[l.source] = (outDeg[l.source] || 0) + 1
      inDeg[l.target] = (inDeg[l.target] || 0) + 1
    }

    const cyclicEdges = detectCyclicEdges(links)
    const cyclicCount = cyclicEdges.size
    const longestPath = computeLongestPath(links, cyclicEdges)

    const cfg = catConfig.value
    const nodes = allNotes.map(n => {
      const c = cfg[n.cat] || { color: '#64748b', glow: '#94a3b8' }
      return {
        id: n.id,
        name: n.name.replace(/\.md$/, ''),
        cat: n.cat,
        type: n.type,
        tags: n.tags || [],
        inDeg: inDeg[n.id] || 0,
        outDeg: outDeg[n.id] || 0,
        color: c.color,
        glow: c.glow,
        icon: c.icon,
      }
    })

    return { nodes, links, cyclicCount, longestPath, cyclicEdges }
  })

  // ═══════════════════════════════════════════════════════════
  //  环检测：DFS 三色标记法
  // ═══════════════════════════════════════════════════════════
  function detectCyclicEdges(links) {
    const adj = {}
    for (const l of links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (!adj[s]) adj[s] = []
      adj[s].push(t)
    }
    const WHITE = 0, GRAY = 1, BLACK = 2
    const color = {}
    const cyclic = new Set()
    function dfs(start) {
      const stack = [{ u: start, iter: 0 }]
      color[start] = GRAY
      while (stack.length) {
        const top = stack[stack.length - 1]
        const neighbors = adj[top.u] || []
        let advanced = false
        while (top.iter < neighbors.length) {
          const v = neighbors[top.iter++]
          if (color[v] === GRAY) {
            cyclic.add(`${top.u}|${v}`)
          } else if (color[v] === WHITE) {
            color[v] = GRAY
            stack.push({ u: v, iter: 0 })
            advanced = true
            break
          }
        }
        if (!advanced) {
          color[top.u] = BLACK
          stack.pop()
        }
      }
    }
    for (const u in adj) {
      if (color[u] === undefined) dfs(u)
    }
    return cyclic
  }

  // ═══════════════════════════════════════════════════════════
  //  最长路径（DAG 上）：Kahn 拓扑排序 + DP
  // ═══════════════════════════════════════════════════════════
  function computeLongestPath(links, cyclicEdges) {
    const adj = {}
    const inDegLocal = {}
    const nodes = new Set()
    for (const l of links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (cyclicEdges.has(`${s}|${t}`)) continue
      if (!adj[s]) adj[s] = []
      adj[s].push(t)
      inDegLocal[t] = (inDegLocal[t] || 0) + 1
      nodes.add(s); nodes.add(t)
    }
    const dist = {}
    const queue = []
    for (const u of nodes) {
      if (!inDegLocal[u]) { queue.push(u); dist[u] = 0 }
    }
    let maxDist = 0
    while (queue.length) {
      const u = queue.shift()
      for (const v of (adj[u] || [])) {
        dist[v] = Math.max(dist[v] || 0, (dist[u] || 0) + 1)
        maxDist = Math.max(maxDist, dist[v])
        inDegLocal[v]--
        if (inDegLocal[v] === 0) queue.push(v)
      }
    }
    return maxDist
  }

  // ═══════════════════════════════════════════════════════════
  //  掌握度统计
  // ═══════════════════════════════════════════════════════════
  const mastery = computed(() => {
    const nodes = graphData.value.nodes
    if (!nodes.length) return { read: 0, total: 0, pct: 0 }
    const read = nodes.filter(n => userData.readSet.has(n.id)).length
    const total = nodes.length
    return { read, total, pct: total ? Math.round(read / total * 100) : 0 }
  })

  // ═══════════════════════════════════════════════════════════
  //  数据过滤
  // ═══════════════════════════════════════════════════════════
  const filteredData = computed(() => {
    let { nodes, links } = graphData.value
    if (selectedCat.value) nodes = nodes.filter(n => n.cat === selectedCat.value)
    if (showUnreadOnly.value) {
      nodes = nodes.filter(n => !userData.readSet.has(n.id))
    }
    if (!showOrphans.value) {
      const conn = new Set()
      links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source
        const t = typeof l.target === 'object' ? l.target.id : l.target
        conn.add(s); conn.add(t)
      })
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

  // ═══════════════════════════════════════════════════════════
  //  分类列表
  // ═══════════════════════════════════════════════════════════
  const categories = computed(() => {
    const m = {}
    notes.items.forEach(n => { m[n.cat] = (m[n.cat] || 0) + 1 })
    const cfg = catConfig.value
    return notes.catOrder.filter(c => m[c]).map(c => ({
      name: c, count: m[c], color: cfg[c]?.color || '#64748b',
      glow: cfg[c]?.glow || '#94a3b8', icon: cfg[c]?.icon || '📄',
    }))
  })

  // ═══════════════════════════════════════════════════════════
  //  上下游可达集（BFS）
  // ═══════════════════════════════════════════════════════════
  const activeId = computed(() => hoverId.value || focusId.value)

  const adjForward = computed(() => {
    const m = {}
    for (const l of filteredData.value.links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (!m[s]) m[s] = []
      m[s].push(t)
    }
    return m
  })

  const adjReverse = computed(() => {
    const m = {}
    for (const l of filteredData.value.links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (!m[t]) m[t] = []
      m[t].push(s)
    }
    return m
  })

  const upstreamSet = computed(() => {
    if (!activeId.value) return new Set()
    const visited = new Set()
    const queue = [activeId.value]
    while (queue.length) {
      const u = queue.shift()
      for (const v of (adjReverse.value[u] || [])) {
        if (!visited.has(v) && v !== activeId.value) {
          visited.add(v)
          queue.push(v)
        }
      }
    }
    return visited
  })

  const downstreamSet = computed(() => {
    if (!activeId.value) return new Set()
    const visited = new Set()
    const queue = [activeId.value]
    while (queue.length) {
      const u = queue.shift()
      for (const v of (adjForward.value[u] || [])) {
        if (!visited.has(v) && v !== activeId.value) {
          visited.add(v)
          queue.push(v)
        }
      }
    }
    return visited
  })

  const focusNode = computed(() => {
    if (!focusId.value) return null
    return graphData.value.nodes.find(n => n.id === focusId.value) || null
  })

  const directPredecessors = computed(() => {
    if (!focusId.value) return []
    const ids = adjReverse.value[focusId.value] || []
    const idSet = new Set(ids)
    return graphData.value.nodes.filter(n => idSet.has(n.id))
  })

  const directSuccessors = computed(() => {
    if (!focusId.value) return []
    const ids = adjForward.value[focusId.value] || []
    const idSet = new Set(ids)
    return graphData.value.nodes.filter(n => idSet.has(n.id))
  })

  // ═══════════════════════════════════════════════════════════
  //  recommendPath → noteId 顺序映射（软锚定用）
  // ═══════════════════════════════════════════════════════════
  // 匹配键陷阱：recommendPath.steps[].id 是合成值 step-001（见后端 normalize_recommend_path），
  // 真实笔记 id 在 noteId 字段 → 必须按 { [s.noteId]: s.order } 建，不能用 s.id。
  // 无 recommendPath（用户没开过 /study-plan）时返回空对象 → 行为与现状完全一致，无回归。
  const pathOrderMap = computed(() => {
    const steps = studyPlan.path?.steps
    if (!steps || !steps.length) return {}
    const m = {}
    for (const s of steps) {
      if (s.noteId) m[s.noteId] = s.order
    }
    return m
  })

  // ═══════════════════════════════════════════════════════════
  //  推荐学习顺序（Kahn 拓扑排序 + recommendPath 软锚定）
  // ═══════════════════════════════════════════════════════════
  const topoOrder = computed(() => {
    const data = filteredData.value
    if (!data.nodes.length) return { items: [], cyclicCount: 0 }

    // P3 续：pathOnly 开启且存在 recommendPath 时，只保留路径内节点。
    // 图谱视图不受影响（它消费 filteredData，不消费 topoOrder）。
    const pmap = pathOrderMap.value
    const hasPath = Object.keys(pmap).length > 0
    let workNodes = data.nodes
    let workLinks = data.links
    if (pathOnly.value && hasPath) {
      const pathIds = new Set(Object.keys(pmap))
      workNodes = data.nodes.filter(n => pathIds.has(n.id))
      const idSet = new Set(workNodes.map(n => n.id))
      workLinks = data.links.filter(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source
        const t = typeof l.target === 'object' ? l.target.id : l.target
        return idSet.has(s) && idSet.has(t)
      })
    }

    const idSet = new Set(workNodes.map(n => n.id))
    const nodeMap = {}
    for (const n of workNodes) nodeMap[n.id] = n

    const cyclicEdges = detectCyclicEdges(workLinks)

    const adj = {}
    const inDeg = {}
    for (const n of workNodes) { adj[n.id] = []; inDeg[n.id] = 0 }
    for (const l of workLinks) {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (!idSet.has(s) || !idSet.has(t)) continue
      if (cyclicEdges.has(`${s}|${t}`)) continue
      adj[s].push(t)
      inDeg[t] = (inDeg[t] || 0) + 1
    }

    const work = { ...inDeg }
    const order = []
    const remaining = new Set(workNodes.map(n => n.id))

    while (remaining.size > 0) {
      const eligible = []
      for (const id of remaining) {
        if (work[id] === 0) eligible.push(id)
      }
      if (!eligible.length) {
        const rest = [...remaining].sort((a, b) =>
          (inDeg[a] || 0) - (inDeg[b] || 0) ||
          (nodeMap[a].name || '').localeCompare(nodeMap[b].name || ''))
        order.push(...rest)
        break
      }
      eligible.sort((a, b) => {
        const ia = inDeg[a] || 0
        const ib = inDeg[b] || 0
        if (ia !== ib) return ia - ib
        // 软锚定：拓扑层内（inDeg 相同）用 recommendPath 的 AI 顺序破平局，
        // 绝不覆盖依赖不变量（A 依赖 B → A 不可能在 B 之前被选中，由 Kahn 算法保证）。
        const pmap = pathOrderMap.value
        const pa = pmap[a], pb = pmap[b]
        if (pa !== undefined && pb !== undefined) return pa - pb
        if (pa !== undefined) return -1   // 有 AI 顺序的优先
        if (pb !== undefined) return 1
        return (nodeMap[a].name || '').localeCompare(nodeMap[b].name || '')
      })
      const pick = eligible[0]
      order.push(pick)
      remaining.delete(pick)
      work[pick] = -1
      for (const v of (adj[pick] || [])) {
        if (work[v] > 0) work[v]--
      }
    }

    const items = order.map((id, idx) => ({
      ...nodeMap[id],
      _idx: idx + 1,
    }))

    return { items, cyclicCount: cyclicEdges.size }
  })

  // ═══════════════════════════════════════════════════════════
  //  辅助方法
  // ═══════════════════════════════════════════════════════════
  function isRead(n) { return userData.readSet.has(n.id) }
  function isFav(n) { return userData.favs.has(n.id) }

  /**
   * 导出推荐学习顺序为 Markdown 清单
   */
  function exportLearningOrder() {
    const t = topoOrder.value
    if (!t.items.length) return
    const dateStr = new Date().toISOString().slice(0, 10)
    const lines = ['# 推荐学习顺序', '']
    lines.push(`> 共 ${t.items.length} 步 · DAG 拓扑排序生成（基础在前，进阶在后）`)
    if (t.cyclicCount > 0) {
      lines.push(`> ⚠️ 检测到 ${t.cyclicCount} 个环边，已自动剔除后排序`)
    }
    lines.push('')
    t.items.forEach(n => {
      lines.push(`## ${n._idx}. ${n.name}`)
      lines.push('')
      lines.push(`- 分类：${n.cat}`)
      lines.push(`- 前置：${n.inDeg} / 后续：${n.outDeg}`)
      if (n.tags && n.tags.length) {
        lines.push(`- 标签：${n.tags.map(t => '#' + t).join(' ')}`)
      }
      lines.push('')
    })
    lines.push('---')
    lines.push('')
    lines.push('_由「学习路径」页 · 拓扑排序导出 · ' + dateStr + '_')

    const md = lines.join('\n')
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `learning-order-${dateStr}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return {
    // 状态
    selectedCat, searchQuery, showOrphans, showUnreadOnly, focusId, hoverId, pathOnly,
    // 数据
    graphData, filteredData, categories, catConfig, topoOrder, pathOrderMap, mastery,
    // 上下游
    activeId, upstreamSet, downstreamSet, focusNode,
    directPredecessors, directSuccessors,
    adjForward, adjReverse,
    // 辅助
    isRead, isFav, exportLearningOrder,
    // 算法（供图谱视图使用）
    detectCyclicEdges, computeLongestPath,
  }
}

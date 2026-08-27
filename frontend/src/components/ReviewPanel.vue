<script setup>
import AppIcon from './AppIcon.vue'
import { ref, computed, onMounted } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useUserDataStore } from '../stores/userData'
import { getInsights } from '../api'

const notes = useNotesStore()
const userData = useUserDataStore()

const recommend = ref(null)
const loading = ref(true)
const favExpanded = ref(false)       // 我的收藏：默认只显示前 8 条，点击"展开"看全部
const histExpanded = ref(false)      // 最近浏览：默认只显示最近 15 条，点击"展开"看更多
const gapExpanded = ref(false)       // 搜索未覆盖：低频诊断项，默认折叠

// 本地复习逻辑（免 API 等待，即时显示）
const staleItems = computed(() => {
  const now = new Date()
  const d45 = new Date(now)
  d45.setDate(d45.getDate() - 45)
  return notes.items
    .filter(n => n.type === 'md' && new Date(n.mtime) < d45 && userData.readSet.has(n.id))
    .sort((a, b) => a.ts - b.ts)
    .slice(0, 8)
})

const unreadItems = computed(() => {
  return notes.items
    .filter(n => n.type === 'md' && !userData.readSet.has(n.id))
    .slice(0, 15)
})

/**
 * 我的收藏：把 favs 集合映射回笔记对象，过滤掉已不在索引中的脏 id（笔记被删/改名后
 * favs 仍可能保留旧 id）。展示标题、分类、首个章节标题（作摘要提示）、首个标签。
 */
const favItems = computed(() => {
  const out = []
  for (const id of userData.favs) {
    const n = notes.items.find(x => x.id === id)
    if (!n) continue
    out.push({
      id: n.id,
      name: n.name.replace(/\.md$/, ''),
      cat: n.cat,
      head: (n.heads && n.heads[0]) || '',
      tag: (n.tags && n.tags[0]) || '',
    })
  }
  return out
})

const favVisible = computed(() =>
  favExpanded.value ? favItems.value : favItems.value.slice(0, 8)
)

/**
 * 最近浏览记录：viewHist 已是倒序，但其中的 id 可能已经失效（笔记被删/改名），
 * 这里同时做一次过滤 + 反查笔记元信息。按"今天/昨天/前天/更早"分组保留原顺序。
 */
const recentGroups = computed(() => {
  const groups = []
  const labelMap = {}
  for (const v of userData.viewHist) {
    const n = notes.items.find(x => x.id === v.id)
    if (!n) continue
    const label = dayLabel(v.ts)
    if (!labelMap[label]) {
      labelMap[label] = { label, items: [] }
      groups.push(labelMap[label])
    }
    labelMap[label].items.push({
      id: n.id,
      name: n.name.replace(/\.md$/, ''),
      cat: n.cat,
      time: hhmm(v.ts),
    })
  }
  return groups
})

/** 展开时显示全部分组；折叠时只显示前 15 条（跨分组累计计数） */
const recentGroupsVisible = computed(() => {
  if (histExpanded.value) return recentGroups.value
  let quota = 15
  const out = []
  for (const g of recentGroups.value) {
    if (quota <= 0) break
    const take = g.items.slice(0, quota)
    out.push({ label: g.label, items: take, total: g.items.length })
    quota -= take.length
  }
  return out
})

const recentTotal = computed(() =>
  recentGroups.value.reduce((s, g) => s + g.items.length, 0)
)

function dayLabel(ts) {
  const d = new Date(ts)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const tsDay = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const oneDay = 86400000
  if (tsDay === today) return '今天'
  if (tsDay === today - oneDay) return '昨天'
  if (tsDay === today - 2 * oneDay) return '前天'
  // 同年内显示"X月X日"，跨年显示"YYYY/MM/DD"
  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getMonth() + 1}月${d.getDate()}日`
  }
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

function hhmm(ts) {
  const d = new Date(ts)
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

function scrollToNote(id) {
  // 与目录、看板保持一致：筛选中不静默跳转，统一提示用户先清除。
  const note = notes.items.find(n => n.id === id)
  if (note) {
    window.dispatchEvent(new CustomEvent('note-navigation-request', { detail: { id, cat: note.cat } }))
  }
}

/**
 * 删除一条"搜索未覆盖"记录：本质是从 searchHist 删掉对应关键词。
 * 后端 _uncovered() 会重新算 gap，所以删完重新拉一次 /api/insights 即可让列表即时更新。
 * 乐观更新：先从 recommend.gap 数组里本地剔除，避免等网络往返的视觉延迟。
 */
async function removeGap(kw) {
  userData.removeSearchHist(kw)
  // 本地立即剔除，UI 不闪烁
  if (recommend.value && Array.isArray(recommend.value.gap)) {
    recommend.value = {
      ...recommend.value,
      gap: recommend.value.gap.filter(g => g !== kw),
    }
  }
  // 后台重新拉一次，对齐服务端真实状态
  try {
    const res = await getInsights()
    recommend.value = res
  } catch { /* 本地已剔除，静默 */ }
}

// 从后端加载统一洞察数据
onMounted(async () => {
  try {
    const res = await getInsights()
    recommend.value = res
  } catch {
    recommend.value = null
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-3">
    <!-- ===== 分区一：我的 · 收藏与足迹 ===== -->
    <section class="rev-card">
      <div class="rev-card-head">
        <span class="inline-flex items-center gap-1.5"><AppIcon name="star" :size="13" /> 我的 · 收藏与足迹</span>
        <span class="rev-count" v-if="favItems.length">收藏 {{ favItems.length }}</span>
      </div>

      <!-- 收藏 -->
      <div v-if="favItems.length">
        <div
          v-for="n in favVisible" :key="n.id"
          @click="scrollToNote(n.id)"
          class="rev-row"
        >
          <div class="rev-row-title">{{ n.name.slice(0, 20) }}</div>
          <div class="rev-row-meta">
            <span>{{ n.cat }}</span>
            <span v-if="n.tag" class="rev-tag">#{{ n.tag }}</span>
            <span v-if="n.head" class="rev-head">§ {{ n.head.slice(0, 24) }}</span>
          </div>
        </div>
        <button
          v-if="favItems.length > 8"
          @click="favExpanded = !favExpanded"
          class="rev-more"
        >{{ favExpanded ? '收起 ▴' : `查看全部 ${favItems.length} 篇 ▾` }}</button>
      </div>
      <div v-else class="rev-empty">点击笔记卡上的星标即可收藏</div>

      <!-- 最近浏览 -->
      <template v-if="recentGroups.length">
        <div class="rev-subhead rev-subhead-muted">最近浏览</div>
        <div v-for="g in recentGroupsVisible" :key="g.label">
          <div class="rev-subhead">{{ g.label }}</div>
          <div
            v-for="n in g.items" :key="n.id + '_' + n.time"
            @click="scrollToNote(n.id)"
            class="rev-row rev-row-hist"
          >
            <span class="rev-time">{{ n.time }}</span>
            <span class="rev-row-title">{{ n.name.slice(0, 18) }}</span>
            <span class="rev-row-cat">{{ n.cat }}</span>
          </div>
        </div>
        <button
          v-if="recentTotal > 15"
          @click="histExpanded = !histExpanded"
          class="rev-more"
        >{{ histExpanded ? '收起 ▴' : `查看全部 ${recentTotal} 条 ▾` }}</button>
      </template>
      <div v-else class="rev-empty">打开过的笔记会按时间倒序记在这里，方便隔天接着读</div>
    </section>

    <!-- ===== 分区二：智能复习建议 ===== -->
    <section class="rev-card">
      <div class="rev-card-head">
        <span class="inline-flex items-center gap-1.5"><AppIcon name="clock" :size="13" /> 智能复习建议</span>
      </div>

      <div v-if="loading" class="rev-empty">加载推荐中…</div>
      <template v-else>
        <!-- 推荐继续学习 -->
        <div v-if="recommend && recommend.next && recommend.next.length">
          <div
            v-for="(item, i) in recommend.next.slice(0, 5)" :key="item.id"
            @click="scrollToNote(item.id)"
            class="rev-row"
            :style="i === 0 ? 'background: rgba(37,99,235,0.06)' : ''"
          >
            <div class="rev-row-title">
              <span v-if="i === 0" style="color:#f59e0b" class="mr-1">★</span>{{ item.name.replace(/\.md$/, '').slice(0, 16) }}
            </div>
            <div class="rev-row-meta"><span>{{ item.cat }}</span><span>分 {{ item.score }}</span></div>
          </div>
        </div>

        <!-- 超过45天建议复习 -->
        <div v-if="staleItems.length">
          <div
            v-for="n in staleItems" :key="n.id"
            @click="scrollToNote(n.id)"
            class="rev-row"
          >
            <div class="rev-row-title">{{ n.name.replace(/\.md$/, '').slice(0, 18) }}</div>
            <div class="rev-row-meta"><span>{{ n.mtime }}</span></div>
          </div>
        </div>
        <div v-else class="rev-empty">已读笔记近期都有回顾</div>

        <!-- 搜索未覆盖（低频诊断，默认折叠） -->
        <div v-if="recommend && recommend.gap && recommend.gap.length" class="rev-collapse">
          <button @click="gapExpanded = !gapExpanded" class="rev-collapse-head">
            <span>搜索未覆盖 ({{ recommend.gap.length }})</span>
            <span>{{ gapExpanded ? '▴' : '▾' }}</span>
          </button>
          <div v-if="gapExpanded">
            <div
              v-for="k in recommend.gap.slice(0, 5)" :key="k"
              class="rev-row rev-row-gap"
            >
              <div class="rev-row-title rev-italic">{{ k }}</div>
              <div class="rev-row-meta">搜过但没对应笔记</div>
              <button
                class="rev-row-del"
                title="从搜索历史删除（该缺口不再提示）"
                @click.stop="removeGap(k)"
              >×</button>
            </div>
          </div>
        </div>
      </template>
    </section>

    <!-- ===== 分区三：阅读进度 ===== -->
    <section class="rev-card">
      <div class="rev-card-head">
        <span class="inline-flex items-center gap-1.5"><AppIcon name="fileText" :size="13" /> 阅读进度</span>
      </div>
      <div v-if="unreadItems.length">
        <div
          v-for="n in unreadItems.slice(0, 10)" :key="n.id"
          @click="scrollToNote(n.id)"
          class="rev-row"
        >
          <div class="rev-row-title">{{ n.name.replace(/\.md$/, '').slice(0, 20) }}</div>
          <div class="rev-row-meta"><span>{{ n.cat }}</span></div>
        </div>
        <div v-if="unreadItems.length > 10" class="rev-empty">还有 {{ unreadItems.length - 10 }} 篇未读…</div>
      </div>
      <div v-else class="rev-empty">所有笔记都已读过！</div>
    </section>
  </div>
</template>

<style scoped>
.rev-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
}
.rev-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
  margin-bottom: 8px;
}
.rev-count {
  font-size: 12px;
  color: var(--muted);
  font-weight: 400;
}
/* 天分组标签（今天/昨天…）：accent 色 + 浅底 chip */
.rev-subhead {
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
  background: var(--hover);
  padding: 2px 8px;
  border-radius: 6px;
  margin: 10px 0 6px;
}
/* 区块内分隔标题（最近浏览）：muted 色，弱于天分组 */
.rev-subhead-muted {
  color: var(--muted);
  margin-top: 12px;
}
/* 列表行：去虚线，改用整行 padding + hover 高亮 */
.rev-row {
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.rev-row:hover {
  background: var(--hover);
}
.rev-row-title {
  font-weight: 500;
  color: var(--text);
}
.rev-row-meta {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  gap: 8px;
  margin-top: 2px;
  flex-wrap: wrap;
  align-items: center;
}
.rev-tag {
  background: var(--hover);
  color: var(--accent2);
  padding: 0 6px;
  border-radius: 999px;
}
.rev-head {
  font-style: italic;
}
.rev-italic {
  font-style: italic;
}
/* 最近浏览历史行：时间 | 标题 | 分类 三点式对齐 */
.rev-row-hist {
  display: flex;
  align-items: center;
  gap: 8px;
}
/* gap 行：标题/meta 在左，删除按钮在右 */
.rev-row-gap {
  position: relative;
  padding-right: 24px;
}
.rev-row-del {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  line-height: 16px;
  text-align: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 14px;
  padding: 0;
  transition: background 0.15s, color 0.15s;
}
.rev-row-del:hover {
  background: var(--color-danger, #fee2e2);
  color: #dc2626;
}
.rev-time {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--muted);
  flex: none;
  width: 38px;
}
.rev-row-cat {
  font-size: 12px;
  color: var(--muted);
  margin-left: auto;
  max-width: 70px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rev-more {
  margin-top: 6px;
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
}
.rev-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 6px 2px;
}
/* 搜索未覆盖折叠头 */
.rev-collapse {
  margin-top: 8px;
  border-top: 1px solid var(--line);
  padding-top: 6px;
}
.rev-collapse-head {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 2px;
}
</style>

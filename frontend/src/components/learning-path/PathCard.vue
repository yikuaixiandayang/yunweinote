<script setup>
import { computed } from 'vue'
import { escapeHtml } from '../../utils/safeHtml.js'

const props = defineProps({
  item: { type: Object, required: true },
  isRead: { type: Boolean, default: false },
  isFav: { type: Boolean, default: false },
  predecessors: { type: Array, default: () => [] },
  successors: { type: Array, default: () => [] },
  expanded: { type: Boolean, default: false },
  searchQuery: { type: String, default: '' },
})

const emit = defineEmits(['toggle', 'open-note', 'jump-to'])

// 序号圆显示的数字（composable 中 _idx 已从 1 起）
const indexLabel = computed(() => {
  const i = Number(props.item._idx)
  return Number.isFinite(i) ? i : 1
})

// 标题高亮：先 HTML 转义，再用 <mark> 包裹匹配项，最终通过 v-html 渲染
const highlightedName = computed(() => {
  const source = escapeHtml(props.item.name)
  const q = (props.searchQuery || '').trim()
  if (!q) return source
  const escapedQuery = escapeHtml(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return source.replace(new RegExp(`(${escapedQuery})`, 'gi'), '<mark>$1</mark>')
})

function onToggle() {
  emit('toggle')
}
function onOpenNote() {
  emit('open-note', props.item.id)
}
function onJump(noteId) {
  emit('jump-to', noteId)
}
</script>

<template>
  <div class="path-card" :class="{ 'is-expanded': expanded }">
    <!-- 折叠态：单行头部 -->
    <div
      class="path-card__header"
      role="button"
      tabindex="0"
      :aria-expanded="expanded"
      @click="onToggle"
      @keydown.enter.prevent="onToggle"
      @keydown.space.prevent="onToggle"
    >
      <span
        class="path-card__index"
        :style="{
          background: item.color,
          boxShadow: item.glow ? `0 0 6px ${item.glow}` : 'none',
        }"
      >{{ indexLabel }}</span>

      <span class="path-card__line" :style="{ background: item.color }"></span>

      <span class="path-card__title" v-html="highlightedName"></span>

      <span class="path-card__meta">
        <span v-if="isRead" class="path-card__badge path-card__badge--read" title="已读">✓</span>
        <span v-if="isFav" class="path-card__badge path-card__badge--fav" title="已收藏">★</span>
        <span class="path-card__deg" :title="`前置 ${item.inDeg} / 后续 ${item.outDeg}`">
          <span>前置{{ item.inDeg }}</span>
          <span class="path-card__deg-sep">·</span>
          <span>后续{{ item.outDeg }}</span>
        </span>
      </span>
    </div>

    <!-- 展开态：详情区域 -->
    <div class="path-card__detail">
      <div class="path-card__detail-inner">
        <div class="path-card__cols">
          <!-- 前置知识（蓝） -->
          <div class="path-card__col">
            <div class="path-card__col-title path-card__col-title--pre">
              <span class="path-card__col-dot"></span>
              <span>前置知识</span>
              <span class="path-card__col-count">{{ predecessors.length }}</span>
            </div>
            <ul class="path-card__dep-list">
              <li v-if="!predecessors.length" class="path-card__dep-empty">无前置依赖</li>
              <li
                v-for="p in predecessors"
                :key="p.id"
                class="path-card__dep"
                :style="{ '--dep-color': p.color || 'var(--accent)' }"
                @click="onJump(p.id)"
              >
                <span class="path-card__dep-dot"></span>
                <span class="path-card__dep-name">{{ p.name }}</span>
              </li>
            </ul>
          </div>

          <!-- 后续进阶（橙） -->
          <div class="path-card__col">
            <div class="path-card__col-title path-card__col-title--suc">
              <span class="path-card__col-dot"></span>
              <span>后续进阶</span>
              <span class="path-card__col-count">{{ successors.length }}</span>
            </div>
            <ul class="path-card__dep-list">
              <li v-if="!successors.length" class="path-card__dep-empty">无后续进阶</li>
              <li
                v-for="s in successors"
                :key="s.id"
                class="path-card__dep"
                :style="{ '--dep-color': s.color || 'var(--star)' }"
                @click="onJump(s.id)"
              >
                <span class="path-card__dep-dot"></span>
                <span class="path-card__dep-name">{{ s.name }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="path-card__footer">
          <div class="path-card__tags">
            <span
              v-for="t in (item.tags || [])"
              :key="t"
              class="path-card__tag"
            >{{ t }}</span>
            <span v-if="!(item.tags && item.tags.length)" class="path-card__tags-empty">无标签</span>
          </div>
          <button class="path-card__open" @click="onOpenNote">
            <span v-if="item.icon" class="path-card__open-icon">{{ item.icon }}</span>
            打开笔记
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.path-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.path-card:hover {
  border-color: color-mix(in srgb, var(--accent) 30%, var(--line));
}
.path-card.is-expanded {
  box-shadow: var(--shadow);
}

/* ===== 折叠态头部 ===== */
.path-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 0 12px 0 0;
  cursor: pointer;
  user-select: none;
  transition: background 0.18s;
}
.path-card__header:hover {
  background: var(--hover);
}

.path-card__index {
  flex: none;
  width: 28px;
  height: 28px;
  margin-left: 10px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.path-card__line {
  flex: none;
  width: 3px;
  align-self: stretch;
  margin: 8px 2px 8px 0;
  border-radius: 2px;
}

.path-card__title {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.path-card__meta {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.path-card__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 12px;
  line-height: 1;
}
.path-card__badge--read {
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 15%, transparent);
}
.path-card__badge--fav {
  color: var(--star);
  background: color-mix(in srgb, var(--star) 18%, transparent);
}

.path-card__deg {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-variant-numeric: tabular-nums;
}
.path-card__deg-sep {
  opacity: 0.5;
}

/* ===== 展开态详情 ===== */
.path-card__detail {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-height 0.28s ease, opacity 0.2s ease;
}
.path-card.is-expanded .path-card__detail {
  max-height: 640px;
  opacity: 1;
}

.path-card__detail-inner {
  padding: 4px 14px 14px;
  border-top: 1px dashed var(--line);
}

.path-card__cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin: 10px 0 12px;
}

.path-card__col-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 6px;
}
.path-card__col-title--pre {
  color: var(--accent);
}
.path-card__col-title--suc {
  color: var(--star);
}
.path-card__col-title--pre .path-card__col-dot {
  background: var(--accent);
}
.path-card__col-title--suc .path-card__col-dot {
  background: var(--star);
}
.path-card__col-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.path-card__col-count {
  margin-left: 2px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
  line-height: 16px;
  color: var(--muted);
  background: var(--hover);
  border-radius: 9px;
}

.path-card__dep-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.path-card__dep {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  margin: 0 -8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.path-card__dep:hover {
  background: var(--hover);
}
.path-card__dep-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--dep-color, var(--muted));
  transition: transform 0.15s;
}
.path-card__dep:hover .path-card__dep-dot {
  transform: scale(1.3);
}
.path-card__dep-name {
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.15s;
}
.path-card__dep:hover .path-card__dep-name {
  color: var(--accent);
}
.path-card__dep-empty {
  list-style: none;
  padding: 5px 8px;
  font-size: 12px;
  font-style: italic;
  color: var(--muted);
}

/* ===== 底部：标签 + 打开笔记 ===== */
.path-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}
.path-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-width: 0;
}
.path-card__tag {
  padding: 2px 8px;
  font-size: 11px;
  line-height: 16px;
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 9px;
}
.path-card__tags-empty {
  font-size: 12px;
  font-style: italic;
  color: var(--muted);
}
.path-card__open {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  color: #fff;
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: opacity 0.18s, transform 0.18s;
}
.path-card__open:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
.path-card__open-icon {
  font-size: 14px;
  line-height: 1;
}

/* ===== 搜索高亮（v-html 内的 <mark>） ===== */
.path-card__title :deep(mark) {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  color: inherit;
  border-radius: 3px;
  padding: 0 2px;
}
</style>

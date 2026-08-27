<script setup>
import { computed } from 'vue'

const props = defineProps({
  cat: { type: String, default: null },
  tags: { type: Set, default: () => new Set() },
  sort: { type: String, default: 'default' },
  favOnly: Boolean,
  q: String,
  resultCount: Number,
})

const emit = defineEmits(['home', 'clear', 'cat-clear'])

const crumbs = computed(() => {
  const parts = [{ label: '首页', action: 'home' }]
  if (props.cat) parts.push({ label: props.cat, action: 'cat' })
  if (props.tags.size) parts.push({ label: '标签：' + [...props.tags].join(' + '), action: null })
  if (props.sort !== 'default') parts.push({ label: props.sort === 'mtime' ? '最近更新' : '热门笔记', action: null })
  return parts
})
</script>

<template>
  <div
    class="flex items-center gap-2 text-xs flex-wrap px-3 py-2 rounded-lg"
    :style="{ color: 'var(--muted)', background: 'var(--card)', border: '1px solid var(--line)' }"
  >
    <template v-for="(c, i) in crumbs" :key="i">
      <span v-if="i > 0" class="opacity-40">›</span>
      <a
        v-if="c.action"
        @click="c.action === 'home' ? emit('home') : c.action === 'cat' ? emit('cat-clear') : null"
        class="cursor-pointer no-underline transition-colors hover:opacity-80"
        :style="{ color: 'var(--accent)' }"
      >{{ c.label }}</a>
      <span v-else :style="{ color: 'var(--text-secondary)' }">{{ c.label }}</span>
    </template>
    <span class="ml-auto font-medium" :style="{ color: 'var(--text-secondary)' }" v-if="resultCount !== undefined">{{ resultCount }} 条结果</span>
    <a
      v-if="cat || q || tags.size || favOnly"
      @click="emit('clear')"
      class="cursor-pointer no-underline ml-1.5 inline-flex items-center gap-0.5 transition-colors hover:opacity-80"
      :style="{ color: '#ef4444' }"
    >✕ 清除筛选</a>
  </div>
</template>

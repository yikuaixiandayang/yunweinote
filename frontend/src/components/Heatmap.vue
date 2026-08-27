<script setup>
import { computed } from 'vue'
import { useNotesStore } from '../stores/notes'
import { useThemeStore } from '../stores/theme'

const notes = useNotesStore()
const theme = useThemeStore()

// 浅色：GitHub 绿色系；深色：蓝色系（与 accent 配色一致）
const colors = computed(() =>
  theme.isDark
    ? ['#1a2332', '#1e3a5f', '#2563eb', '#3b82f6', '#60a5fa']
    : ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39']
)

const cells = computed(() => {
  const dm = {}
  notes.items.forEach(n => {
    const d = n.mtime
    if (d) dm[d] = (dm[d] || 0) + 1
  })
  const now = new Date()
  const result = []
  for (let i = 83; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const k = d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0')
    result.push({
      key: k,
      count: dm[k] || 0,
      day: d.getDay(),
      weekIdx: Math.floor(i / 7),
    })
  }
  return result
})

const maxCount = computed(() => Math.max(...cells.value.map(c => c.count), 1))

const svgView = computed(() => {
  if (!cells.value.length) return ''
  const cols = 13
  const cs = 9
  const gap = 2
  let svg = `<svg class="heatmap-svg" viewBox="0 0 ${cols * (cs + gap) + 20} 78">`
  ;['', '一', '', '三', '', '五', ''].forEach((l, i) => {
    if (l) svg += `<text x="0" y="${i * (cs + gap) + 8}" font-size="8" fill="var(--muted)">${l}</text>`
  })
  cells.value.forEach(c => {
    const lvl = c.count > 0 ? Math.floor((c.count / maxCount.value) * 4) + 1 : 0
    const x = c.weekIdx * (cs + gap) + 16
    const y = c.day * (cs + gap)
    svg += `<rect class="heatmap-day" x="${x}" y="${y}" width="${cs}" height="${cs}" fill="${colors.value[lvl]}" rx="2" ry="2"><title>${c.key}: ${c.count}篇修改</title></rect>`
  })
  svg += '</svg>'
  return svg
})
</script>

<template>
  <div class="heatmap-container pt-1">
    <div v-if="!cells.length" class="text-xs text-center py-2" :style="{ color: 'var(--muted)' }">暂无数据</div>
    <div v-else v-html="svgView"></div>
  </div>
</template>

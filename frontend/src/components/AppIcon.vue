<script setup>
/**
 * 自制 SVG 图标库 — 24×24 stroke 风格（Lucide 系审美，手工绘制路径）
 *
 * 特性：
 *  - stroke=currentColor：自动跟随文字颜色，深浅色主题无缝联动
 *  - 无依赖、无字体文件：直接内联 SVG，tree-shaking 友好
 *  - 统一 stroke-width / linecap / linejoin，视觉重量一致
 *
 * 用法：<AppIcon name="terminal" :size="16" />
 */
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  strokeWidth: { type: [Number, String], default: 2 },
})

/* 图标注册表：每个图标是若干 SVG path 的 d 字符串（圆用弧线命令编码） */
const REGISTRY = {
  // ───── 导航 ─────
  terminal: ['M4 17l6-6-6-6', 'M12 19h8'],
  folder: ['M3 8a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
  folderOpen: ['M3 8a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v2', 'M3 8v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-1.54', 'M3 12h15.11a1 1 0 0 1 .98 1.2l-1.24 6a1 1 0 0 1-.98.8H5'],
  graph: [
    'M15 5a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // 节点右上
    'M3 12a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // 节点左中
    'M15 19a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // 节点右下
    'M8.6 13.5l6.8 4',
    'M15.4 6.5l-6.8 4',
  ],
  route: [
    'M3 19a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // 起点圆
    'M15 5a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // 终点圆
    'M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15', // S 形路径
  ],
  bot: [
    'M6 8h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z', // 头
    'M12 8V5',   // 天线
    'M9 5h6',    // 天线横杆
    'M9 14h.01', // 左眼（圆点）
    'M15 14h.01', // 右眼
    'M2 14h2',   // 左耳
    'M20 14h2',  // 右耳
  ],
  message: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'],
  user: [
    'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2',
    'M8 7a4 4 0 1 0 8 0 4 4 0 1 0-8 0',
  ],
  home: ['M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z', 'M9 21v-8h6v8'],

  // ───── 操作 ─────
  settings: [
    'M4 21v-7', 'M4 10V3', 'M12 21v-9', 'M12 8V3', 'M20 21v-5', 'M20 12V3',
    'M1 14h6', 'M9 8h6', 'M17 16h6',
  ],
  sun: [
    'M8 12a4 4 0 1 0 8 0 4 4 0 1 0-8 0',
    'M12 2v2', 'M12 20v2', 'M2 12h2', 'M20 12h2',
    'M4.93 4.93l1.41 1.41', 'M17.66 17.66l1.41 1.41',
    'M6.34 17.66l-1.41 1.41', 'M19.07 4.93l-1.41 1.41',
  ],
  moon: ['M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  search: ['M3 11a8 8 0 1 0 16 0 8 8 0 1 0-16 0', 'M21 21l-4.35-4.35'],
  send: ['M22 2 11 13', 'M22 2 15 22l-4-9-9-4z'],
  star: ['M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z'],
  x: ['M18 6 6 18', 'M6 6l12 12'],
  check: ['M20 6 9 17l-5-5'],
  arrowLeft: ['M19 12H5', 'M12 19l-7-7 7-7'],
  arrowUp: ['M12 19V5', 'M5 12l7-7 7 7'],
  chevronDown: ['M6 9l6 6 6-6'],
  chevronRight: ['M9 18l6-6-6-6'],
  download: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'M7 10l5 5 5-5', 'M12 15V3'],
  trash: ['M3 6h18', 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', 'M10 11v6', 'M14 11v6'],
  refresh: ['M3 12a9 9 0 1 0 2.64-6.36L3 8', 'M3 3v5h5'],
  externalLink: ['M15 3h6v6', 'M10 14 21 3', 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6'],
  fullscreen: ['M8 3H5a2 2 0 0 0-2 2v3', 'M21 8V5a2 2 0 0 0-2-2h-3', 'M3 16v3a2 2 0 0 0 2 2h3', 'M16 21h3a2 2 0 0 0 2-2v-3'],

  // ───── 侧栏 / 状态 ─────
  panelLeft: ['M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 'M9 3v18'],
  barChart: ['M12 20V10', 'M18 20V4', 'M6 20v-6'],
  clock: ['M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0', 'M12 7v5l3 2'],
  calendar: ['M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 'M3 9h18', 'M8 3v4', 'M16 3v4', 'M8 14h.01', 'M12 14h.01', 'M16 14h.01'],
  list: ['M8 6h13', 'M8 12h13', 'M8 18h13', 'M3 6h.01', 'M3 12h.01', 'M3 18h.01'],
  zap: ['M13 2 3 14h9l-1 8 10-12h-9l1-8z'],
  key: [
    'M2 15.5a5.5 5.5 0 1 0 11 0 5.5 5.5 0 1 0-11 0',
    'M13.2 9.8 21 2',
    'M17 6l2.5 2.5',
  ],
  fileText: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z', 'M14 2v4a2 2 0 0 0 2 2h4', 'M16 13H8', 'M16 17H8'],
  paperclip: ['M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48'],
  paper: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z'],
  database: ['M4 6a8 3 0 0 1 16 0 8 3 0 0 1-16 0', 'M4 6v6a8 3 0 0 0 16 0V6', 'M4 12v6a8 3 0 0 0 16 0v-6'],
  package: ['M16.5 9.4 7.5 4.21', 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z', 'M3.27 6.96 12 12.01l8.73-5.05', 'M12 22.08V12'],
  hardDrive: ['M22 12H2', 'M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z', 'M6 16h.01', 'M10 16h.01'],
  copy: [
    'M16 4H2a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z',
    'M2 16h16a2 2 0 0 0 2-2V4',
  ],
  edit: [
    'M12 20h9',
    'M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z',
  ],
  stickyNote: [
    'M4 4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10l-6 6H6a2 2 0 0 1-2-2z',
    'M14 18v-4a2 2 0 0 1 2-2h4',
  ],
}

const paths = computed(() => REGISTRY[props.name] || [])
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="app-icon"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<style scoped>
.app-icon {
  flex: none;
  display: inline-block;
  vertical-align: -0.15em; /* 与文字基线对齐 */
}
</style>

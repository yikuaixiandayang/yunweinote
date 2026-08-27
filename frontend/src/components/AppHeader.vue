<script setup>
/**
 * 全站共享顶栏 — 统一导航 / 设置 / 主题切换。
 *
 * 所有标准页面（首页/脚本库/文件夹/Agent）共用此顶栏，
 * 图谱与学习路径等画布型页面可继续使用自己的集成工具栏。
 *
 * props:
 *   - title: 页面标题（默认"运维笔记总索引"）
 *   - showNav: 是否显示导航按钮（默认 true）
 * emits:
 *   - menu: 移动端汉堡按钮点击（父级控制侧栏抽屉）
 * slots:
 *   - default: 标题右侧的页面专属元素（如统计、状态徽章）
 *   - below: 顶栏下方的额外行（如元信息、提示条）
 */
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useThemeStore } from '../stores/theme'
import { useAppearanceStore } from '../stores/appearance'
import AppIcon from './AppIcon.vue'
import SettingsModal from './SettingsModal.vue'

const props = defineProps({
  title: { type: String, default: '运维笔记总索引' },
  showNav: { type: Boolean, default: true },
  showMenu: { type: Boolean, default: false },
})
const emit = defineEmits(['menu'])

// 外观设置弹窗由 AppHeader 统一持有：所有使用本顶栏的页面自动获得可用的设置入口，
// 无需各页面重复维护 showSettings 状态与 <SettingsModal> 挂载。
const showSettings = ref(false)

const router = useRouter()
const route = useRoute()
const theme = useThemeStore()
const appearance = useAppearanceStore()

const NAV = [
  { path: '/scripts', label: '脚本库', icon: 'terminal' },
  { path: '/folders', label: '项目文件夹', icon: 'folder' },
  { path: '/graph', label: '图谱', icon: 'graph' },
  { path: '/study-plan', label: '学习计划', icon: 'calendar' },
  { path: '/agent', label: 'AI 助手', icon: 'bot' },
]

function go(p) {
  router.push(p)
}

const isHome = computed(() => route.path === '/')

// 玻璃模式下顶栏毛玻璃：用 inline 样式注入。
// 不能写在 CSS 里：构建时 Lightning CSS 会把 backdrop-filter 声明从产物中删掉（实测规则变空）
const headerStyle = computed(() => {
  const base = { background: 'var(--header-bg)', borderBottom: '1px solid var(--header-line)' }
  if (appearance.glassEnabled) {
    base.backdropFilter = 'blur(18px) saturate(170%)'
    base.WebkitBackdropFilter = 'blur(18px) saturate(170%)'
  }
  return base
})
</script>

<template>
  <header
    class="app-header"
    :style="headerStyle"
  >
    <div class="app-header-main">
      <!-- 移动端菜单按钮 -->
      <button
        v-if="showMenu"
        class="nav-btn menu-btn"
        :aria-expanded="false"
        aria-label="打开侧边栏"
        @click="emit('menu')"
      ><AppIcon name="menu" :size="18" /></button>

      <!-- 品牌：图标 + 标题 -->
      <div class="brand" :class="{ clickable: !isHome }" :role="!isHome ? 'button' : undefined" @click="!isHome && go('/')">
        <span class="brand-mark" :style="{ background: 'var(--accent-gradient)' }">
          <AppIcon name="terminal" :size="15" stroke-width="2.4" />
        </span>
        <h1 class="brand-title">{{ title }}</h1>
      </div>

      <!-- 页面专属插槽 -->
      <slot />

      <!-- 导航 + 设置 + 主题 -->
      <div class="nav-group" v-if="showNav">
        <button
          v-for="item in NAV"
          :key="item.path"
          class="nav-btn"
          :class="{ active: route.path === item.path || (item.path !== '/' && route.path.startsWith(item.path)) }"
          :aria-label="`打开${item.label}`"
          @click="go(item.path)"
        >
          <AppIcon :name="item.icon" :size="14" />
          <span class="nav-label">{{ item.label }}</span>
        </button>
        <span class="nav-sep"></span>
        <button class="nav-btn" aria-label="外观设置" @click="showSettings = true">
          <AppIcon name="settings" :size="14" />
          <span class="nav-label">设置</span>
        </button>
        <button
          class="nav-btn icon-only"
          :aria-label="theme.isDark ? '切换到浅色主题' : '切换到深色主题'"
          @click="theme.toggle()"
        >
          <AppIcon :name="theme.isDark ? 'sun' : 'moon'" :size="15" />
        </button>
      </div>
    </div>

    <!-- 顶栏下方附加内容（首页的元信息/提示条） -->
    <slot name="below" />
  </header>

  <!-- 全站统一外观设置弹窗（Teleport 到 body） -->
  <SettingsModal v-model="showSettings" />
</template>

<style scoped>
.app-header {
  flex: none;
  position: sticky;
  top: 0;
  z-index: 20;
}
/* 玻璃模式下的顶栏模糊与字重加粗见 style.css 全局规则
   （scoped 中 :global(.glass) 后代选择器会被 Vue 编译压平，放这里不生效） */
.app-header-main {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  max-width: 1440px;
  margin: 0 auto;
  flex-wrap: wrap;
}

/* 品牌 */
.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.brand.clickable { cursor: pointer; }
.brand-mark {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex: none;
  box-shadow: var(--shadow-sm);
}
.brand-title {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.01em;
  color: var(--text);
  white-space: nowrap;
}

/* 导航组 */
.nav-group {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.nav-sep {
  width: 1px;
  height: 18px;
  background: var(--line);
  margin: 0 4px;
}

/* 导航按钮：hover 用底色变化而非缩放 */
.nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 11px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  white-space: nowrap;
}
.nav-btn:hover {
  background: var(--hover);
  color: var(--text);
}
.nav-btn.active {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 22%, transparent);
  font-weight: 600;
}
.nav-btn.icon-only { padding: 6px 8px; }

/* 移动端：隐藏文字标签只留图标 */
.menu-btn { display: none; }
@media (max-width: 640px) {
  .nav-label { display: none; }
  .nav-btn { padding: 7px 9px; }
  .menu-btn { display: inline-flex; }
  .app-header-main { padding: 10px 14px; gap: 6px; }
  .brand-title { font-size: 15px; }
}
</style>

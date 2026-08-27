<script setup>
import { useThemeStore } from './stores/theme'
import { useAppearanceStore } from './stores/appearance'
import { onMounted, computed, watch } from 'vue'

const theme = useThemeStore()
const appearance = useAppearanceStore()

// 壁纸全局生效：所有页面统一叠加自定义背景图
const showBgImage = computed(() => Boolean(appearance.bgEnabled && appearance.backgroundImage))

const bgStyle = computed(() => {
  if (!showBgImage.value) return {}
  return {
    backgroundImage: `url(${appearance.backgroundImage})`,
    backgroundSize: appearance.bgFit,
    backgroundPosition: 'center',
    opacity: appearance.bgOpacity,
    filter: `blur(${appearance.bgBlur}px) brightness(${appearance.bgBrightness})`,
  }
})

onMounted(async () => {
  theme.init()
  await appearance.init()
  // 持久化的外观覆盖（玻璃变量 / 壁纸底色淡化）需在 theme.init() 写入预设变量之后再覆盖
  appearance.reapplyOverrides()
})

// 主题切换（明暗/预设/自定义色）会重写 html 上的 inline 变量，需重新盖回外观覆盖
watch(() => theme.themeVersion, () => appearance.reapplyOverrides())
</script>

<template>
  <div :class="{ dark: theme.isDark, glass: appearance.glassEnabled }">
    <div class="min-h-screen relative" style="background: var(--bg)">
      <!-- 自定义背景图层（fixed 全屏，不随滚动；所有页面统一生效） -->
      <div
        v-if="showBgImage"
        class="fixed inset-0 z-0 pointer-events-none bg-cover bg-center"
        :style="bgStyle"
      ></div>
      <!-- 内容层在背景图之上 -->
      <div class="relative z-10">
        <router-view />
      </div>
    </div>
  </div>
</template>

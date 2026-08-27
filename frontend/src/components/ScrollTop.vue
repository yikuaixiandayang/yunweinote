<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const show = ref(false)

function onScroll(e) {
  const el = e.target
  if (el && el.nodeType === 1 && el.matches?.('.notes-scroll-window')) {
    show.value = el.scrollTop > 400
  }
}

function scrollTop() {
  const scrollWindow = document.querySelector('.notes-scroll-window')
  if (scrollWindow) scrollWindow.scrollTo({ top: 0, behavior: 'smooth' })
  else window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => document.addEventListener('scroll', onScroll, true))
onUnmounted(() => document.removeEventListener('scroll', onScroll, true))
</script>

<template>
  <Transition name="scrolltop-fade">
    <button
      v-show="show"
      @click="scrollTop"
      class="fixed right-6 bottom-8 w-12 h-12 rounded-full text-xl cursor-pointer z-20 flex items-center justify-center transition-all duration-300 hover:scale-110"
      :style="{
        background: 'var(--accent)',
        color: '#fff',
        border: 'none',
        boxShadow: '0 4px 14px color-mix(in srgb, var(--accent) 40%, transparent)',
      }"
      title="返回顶部"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 19V5M5 12l7-7 7 7"/>
      </svg>
    </button>
  </Transition>
</template>

<style scoped>
.scrolltop-fade-enter-active,
.scrolltop-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.scrolltop-fade-enter-from,
.scrolltop-fade-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.8);
}
</style>

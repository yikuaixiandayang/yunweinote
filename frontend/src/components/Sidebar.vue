<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

const activeTab = ref('tree')

const emit = defineEmits(['tab-change'])

const TABS = [
  { k: 'tree', l: '目录', icon: 'panelLeft' },
  { k: 'dashboard', l: '看板', icon: 'barChart' },
]

function setTab(tab) {
  activeTab.value = tab
  emit('tab-change', tab)
}
</script>

<template>
  <div
    class="w-[264px] flex-none rounded-xl border p-2.5 max-h-[calc(100vh-24px)] overflow-hidden flex flex-col"
    :style="{ background: 'var(--card)', borderColor: 'var(--line)' }"
  >
    <div class="flex gap-1 mb-2 pb-1.5 flex-none" :style="{ borderBottom: '1px solid var(--line)' }">
      <button
        v-for="tab in TABS"
        :key="tab.k"
        @click="setTab(tab.k)"
        class="flex-1 text-center text-xs font-semibold py-1.5 rounded-md cursor-pointer transition-all duration-200 inline-flex items-center justify-center gap-1.5"
        :class="activeTab === tab.k ? 'text-white' : ''"
        :style="activeTab === tab.k ? { background: 'var(--accent)' } : { color: 'var(--muted)', background: 'none', border: 'none' }"
      >
        <AppIcon :name="tab.icon" :size="13" />
        {{ tab.l }}
      </button>
    </div>

    <div class="overflow-y-auto flex-1 min-h-0">
      <slot name="tree" v-if="activeTab === 'tree'"></slot>
      <slot name="dashboard" v-if="activeTab === 'dashboard'"></slot>
    </div>
  </div>
</template>

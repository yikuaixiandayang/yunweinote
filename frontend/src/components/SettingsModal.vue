<script setup>
/**
 * 外观设置弹窗
 * 移植自参考实现，保留：主题预设 / 自定义配色 / 自定义背景图 / 玻璃风
 * 去掉：阅读设置（打卡） / 快捷键 / 标签 / 分享配色
 * 用简单的内联 toast 替代 notifications store
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useAppearanceStore } from '../stores/appearance'
import { useThemeStore } from '../stores/theme'
import { THEME_PRESETS } from '../constants/themes'
import { compressImage, validateImageFile } from '../utils/imageCompress'

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])

const appearance = useAppearanceStore()
const theme = useThemeStore()

const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

// 简易 toast
const toast = ref({ show: false, type: 'info', msg: '' })
let _toastTimer = null
function notify(type, msg) {
  toast.value = { show: true, type, msg }
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => { toast.value.show = false }, 2500)
}

// === 背景图上传 ===
const isDragging = ref(false)
const isCompressing = ref(false)
const errorMessage = ref('')
const warningMessage = ref('')
const fileInputRef = ref(null)

const OPACITY_MAX = 1
const opacityPercent = computed({ get: () => Math.round((appearance.bgOpacity / OPACITY_MAX) * 100), set: (v) => appearance.setBgOpacity((Number(v) / 100) * OPACITY_MAX) })
const OPACITY_PRESETS = [
  { v: 20, t: '淡雅' },
  { v: 45, t: '均衡' },
  { v: 80, t: '鲜明' },
]
const blurValue = computed({ get: () => appearance.bgBlur, set: (v) => appearance.setBgBlur(Number(v)) })
const BRIGHTNESS_MIN = 0.5
const brightnessPercent = computed({ get: () => Math.round(appearance.bgBrightness * 100), set: (v) => appearance.setBgBrightness(Math.max(BRIGHTNESS_MIN, Number(v) / 100)) })
const fitValue = computed({ get: () => appearance.bgFit, set: (v) => appearance.setBgFit(v) })
const enabled = computed({ get: () => appearance.bgEnabled, set: (v) => appearance.setEnabled(v) })
const hasImage = computed(() => Boolean(appearance.backgroundImage))

async function handleFile(file) {
  errorMessage.value = ''; warningMessage.value = ''
  if (!file) return
  const valid = validateImageFile(file)
  if (!valid.ok) { errorMessage.value = valid.reason || '文件不可用'; return }
  if (valid.warning) warningMessage.value = valid.warning
  isCompressing.value = true
  try {
    const dataUrl = await compressImage(file, 1920, 0.8)
    const res = appearance.setBackgroundImage(dataUrl)
    if (!res.ok) errorMessage.value = res.reason || '图片过大'
  } catch (e) { errorMessage.value = `处理失败：${e.message || e}` } finally { isCompressing.value = false }
}
function triggerFileInput() { if (fileInputRef.value) fileInputRef.value.click() }
function onFileChange(e) { const f = e.target.files && e.target.files[0]; if (f) handleFile(f); e.target.value = '' }
function onDragOver(e) { e.preventDefault(); isDragging.value = true }
function onDragLeave(e) { e.preventDefault(); isDragging.value = false }
function onDrop(e) { e.preventDefault(); isDragging.value = false; const f = e.dataTransfer.files && e.dataTransfer.files[0]; if (f) handleFile(f) }
function handleReset() { errorMessage.value = ''; warningMessage.value = ''; appearance.clearBackgroundImage() }
function handleClose() { visible.value = false }

// === 自定义配色 ===
const HEX_RE = /^#[0-9a-f]{6}$/i
const QUICK_COLORS = ['#2563eb', '#06b6d4', '#16a34a', '#ca8a04', '#ea580c', '#dc2626', '#9333ea', '#ec4899']
const presetAccent = computed(() => { const p = THEME_PRESETS[theme.preset] || THEME_PRESETS.default; return (theme.isDark ? p.dark : p.light)['--accent'] })
const presetAccent2 = computed(() => { const p = THEME_PRESETS[theme.preset] || THEME_PRESETS.default; return (theme.isDark ? p.dark : p.light)['--accent2'] })
const accentHexInput = ref('')
const accent2HexInput = ref('')
watch(() => theme.customColors.accent, (v) => { accentHexInput.value = v || '' }, { immediate: true })
watch(() => theme.customColors.accent2, (v) => { accent2HexInput.value = v || '' }, { immediate: true })
function commitAccentHex() { const v = accentHexInput.value.trim().toLowerCase(); if (v === '') theme.setCustomColor('accent', null); else if (HEX_RE.test(v)) theme.setCustomColor('accent', v); else accentHexInput.value = theme.customColors.accent || '' }
function commitAccent2Hex() { const v = accent2HexInput.value.trim().toLowerCase(); if (v === '') theme.setCustomColor('accent2', null); else if (HEX_RE.test(v)) theme.setCustomColor('accent2', v); else accent2HexInput.value = theme.customColors.accent2 || '' }
function onToggleCustom(v) { if (v) theme.enableCustom(); else theme.resetCustomColors() }

function onKeydown(e) { if (e.key === 'Escape' && visible.value) { e.preventDefault(); handleClose() } }
watch(visible, (v) => { if (v) { window.addEventListener('keydown', onKeydown); errorMessage.value = ''; warningMessage.value = '' } else window.removeEventListener('keydown', onKeydown) })
onUnmounted(() => { window.removeEventListener('keydown', onKeydown); clearTimeout(_toastTimer) })
</script>

<template>
  <Teleport to="body">
    <Transition name="settings-modal">
      <div v-if="visible" class="fixed inset-0 z-[200] flex items-center justify-center p-4" :class="{ glass: appearance.glassEnabled }" @click.self="handleClose">
        <div class="absolute inset-0" style="background: rgba(0,0,0,0.5); backdrop-filter: blur(4px);"></div>
        <div class="surface-card relative w-full max-w-[520px] max-h-[88vh] overflow-y-auto rounded-2xl shadow-2xl" :style="{ color: 'var(--text)', backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))', WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))' }" role="dialog" aria-modal="true">
          <div class="flex items-center justify-between px-5 py-4 sticky top-0 z-10" :style="{ background: 'var(--card)', borderBottom: '1px solid var(--line)' }">
            <h2 class="text-base font-bold m-0 flex items-center gap-2"><span>🎨</span><span>外观设置</span></h2>
            <button @click="handleClose" class="w-8 h-8 flex items-center justify-center rounded-lg cursor-pointer text-lg leading-none transition-all hover:scale-110" :style="{ background: 'transparent', color: 'var(--muted)', border: 'none' }">✕</button>
          </div>

          <div class="px-5 py-4 flex flex-col gap-5">
            <!-- 主题预设 -->
            <div class="flex flex-col gap-3">
              <div class="flex items-center gap-1.5 text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }"><span>🎨</span><span>主题预设</span></div>
              <div class="grid grid-cols-2 gap-2.5">
                <button v-for="(p, key) in THEME_PRESETS" :key="key" type="button" @click="theme.setPreset(key)" class="relative rounded-lg p-3 cursor-pointer transition-all text-left flex flex-col gap-2" :style="theme.preset === key ? { background: 'var(--card)', border: '2px solid var(--accent)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--card)', border: '2px solid var(--line)' }">
                  <div class="flex items-center justify-between gap-1">
                    <div class="flex items-center gap-1.5 min-w-0"><span class="text-base flex-none">{{ p.icon }}</span><span class="text-xs font-semibold truncate" :style="{ color: 'var(--text)' }">{{ p.name }}</span></div>
                    <span v-if="theme.preset === key" class="text-xs flex-none font-bold" :style="{ color: 'var(--accent)' }">✓</span>
                  </div>
                  <div class="flex gap-1">
                    <div class="h-4 flex-1 rounded-sm" :style="{ background: p.light['--accent'] }"></div>
                    <div class="h-4 flex-1 rounded-sm" :style="{ background: p.light['--accent2'] }"></div>
                    <div class="h-4 flex-1 rounded-sm" :style="{ background: p.light['--card'], border: '1px solid var(--line)' }"></div>
                  </div>
                </button>
              </div>
            </div>

            <!-- 自定义配色 -->
            <div class="flex flex-col gap-3">
              <div class="flex items-center gap-1.5 text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }"><span>🎨</span><span>自定义配色</span></div>
              <div class="flex items-center justify-between p-3 rounded-lg" :style="{ background: 'var(--hover)' }">
                <div class="flex flex-col"><span class="text-sm font-semibold">使用自定义配色</span><span class="text-xs" :style="{ color: 'var(--muted)' }">自由调整 accent / accent2 强调色</span></div>
                <button @click="onToggleCustom(!theme.customEnabled)" role="switch" :aria-checked="theme.customEnabled" class="relative w-11 h-6 rounded-full cursor-pointer transition-colors duration-200 border-none" :style="{ background: theme.customEnabled ? 'var(--accent)' : 'var(--line)' }">
                  <span class="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200" :style="{ transform: theme.customEnabled ? 'translateX(20px)' : 'translateX(0)' }"></span>
                </button>
              </div>
              <div v-if="theme.customEnabled" class="flex flex-col gap-3">
                <div class="flex flex-col gap-1.5">
                  <div class="flex items-center justify-between"><label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">主色 (accent)</label><span class="text-[10px] font-mono" :style="{ color: 'var(--muted)' }">{{ theme.customColors.accent || '预设' }}</span></div>
                  <div class="flex items-center gap-2">
                    <label class="relative w-7 h-7 rounded-full cursor-pointer flex-none overflow-hidden" :style="{ background: theme.customColors.accent || 'var(--accent)', border: '2px solid var(--card)', boxShadow: '0 0 0 1px var(--line)' }"><input type="color" :value="theme.customColors.accent || presetAccent" @input="theme.setCustomColor('accent', $event.target.value)" class="absolute inset-0 opacity-0 cursor-pointer" style="width:100%;height:100%"/></label>
                    <input v-model="accentHexInput" @change="commitAccentHex" @keydown.enter.prevent="commitAccentHex" type="text" placeholder="预设" maxlength="7" spellcheck="false" class="flex-1 px-2 py-1.5 text-xs font-mono rounded-md" :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"/>
                  </div>
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <button v-for="c in QUICK_COLORS" :key="c" type="button" @click="theme.setCustomColor('accent', c)" class="w-5 h-5 rounded-full cursor-pointer transition-transform hover:scale-110" :style="{ background: c, border: theme.customColors.accent === c ? '2px solid var(--text)' : '2px solid var(--card)', boxShadow: '0 0 0 1px var(--line)' }"></button>
                  </div>
                </div>
                <div class="flex flex-col gap-1.5">
                  <div class="flex items-center justify-between"><label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">辅色 (accent2)</label><span class="text-[10px] font-mono" :style="{ color: 'var(--muted)' }">{{ theme.customColors.accent2 || '预设' }}</span></div>
                  <div class="flex items-center gap-2">
                    <label class="relative w-7 h-7 rounded-full cursor-pointer flex-none overflow-hidden" :style="{ background: theme.customColors.accent2 || 'var(--accent2)', border: '2px solid var(--card)', boxShadow: '0 0 0 1px var(--line)' }"><input type="color" :value="theme.customColors.accent2 || presetAccent2" @input="theme.setCustomColor('accent2', $event.target.value)" class="absolute inset-0 opacity-0 cursor-pointer" style="width:100%;height:100%"/></label>
                    <input v-model="accent2HexInput" @change="commitAccent2Hex" @keydown.enter.prevent="commitAccent2Hex" type="text" placeholder="预设" maxlength="7" spellcheck="false" class="flex-1 px-2 py-1.5 text-xs font-mono rounded-md" :style="{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }"/>
                  </div>
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <button v-for="c in QUICK_COLORS" :key="c" type="button" @click="theme.setCustomColor('accent2', c)" class="w-5 h-5 rounded-full cursor-pointer transition-transform hover:scale-110" :style="{ background: c, border: theme.customColors.accent2 === c ? '2px solid var(--text)' : '2px solid var(--card)', boxShadow: '0 0 0 1px var(--line)' }"></button>
                  </div>
                </div>
                <div class="flex flex-col gap-1.5"><label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">渐变预览</label><div class="h-8 rounded-md border" :style="{ background: 'var(--accent-gradient)', borderColor: 'var(--line)' }"></div></div>
                <button @click="theme.resetCustomColors" class="text-xs px-3 py-2 rounded-md cursor-pointer transition-all hover:scale-[1.02] self-start" :style="{ background: 'transparent', color: 'var(--danger)', border: '1px solid var(--danger)' }">↺ 恢复预设色</button>
              </div>
            </div>

            <!-- 启用背景开关 -->
            <div class="flex items-center justify-between p-3 rounded-lg" :style="{ background: 'var(--hover)' }">
              <div class="flex flex-col"><span class="text-sm font-semibold">启用自定义背景</span><span class="text-xs" :style="{ color: 'var(--muted)' }">{{ hasImage ? '当前已设置背景图' : '尚未上传图片' }}</span></div>
              <button @click="enabled = !enabled" role="switch" :aria-checked="enabled" class="relative w-11 h-6 rounded-full cursor-pointer transition-colors duration-200 border-none" :style="{ background: enabled ? 'var(--accent)' : 'var(--line)' }" :disabled="!hasImage">
                <span class="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200" :style="{ transform: enabled ? 'translateX(20px)' : 'translateX(0)' }"></span>
              </button>
            </div>

            <!-- 玻璃风开关 -->
            <div class="flex items-center justify-between p-3 rounded-lg" :style="{ background: 'var(--hover)' }">
              <div class="flex flex-col"><span class="text-sm font-semibold">玻璃风效果</span><span class="text-xs" :style="{ color: 'var(--muted)' }">卡片与顶栏半透明毛玻璃，搭配背景图效果更佳</span></div>
              <button @click="appearance.setGlassEnabled(!appearance.glassEnabled)" role="switch" :aria-checked="appearance.glassEnabled" class="relative w-11 h-6 rounded-full cursor-pointer transition-colors duration-200 border-none" :style="{ background: appearance.glassEnabled ? 'var(--accent)' : 'var(--line)' }">
                <span class="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200" :style="{ transform: appearance.glassEnabled ? 'translateX(20px)' : 'translateX(0)' }"></span>
              </button>
            </div>

            <!-- 背景图上传 -->
            <div class="flex flex-col gap-2">
              <label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">背景图</label>
              <div v-if="hasImage" class="flex items-start gap-3">
                <div class="w-32 h-20 rounded-lg flex-none overflow-hidden relative border" :style="{ borderColor: 'var(--line)' }"><img :src="appearance.backgroundImage" alt="背景图预览" class="w-full h-full object-cover"/></div>
                <div class="flex-1 flex flex-col gap-2 min-w-0">
                  <button @click="triggerFileInput" :disabled="isCompressing" class="btn-glass text-xs rounded-md px-3 py-1.5 cursor-pointer transition-all hover:scale-[1.02]" :style="{ opacity: isCompressing ? 0.5 : 1 }">{{ isCompressing ? '处理中…' : '更换图片' }}</button>
                  <button @click="handleReset" :disabled="isCompressing" class="text-xs rounded-md px-3 py-1.5 cursor-pointer transition-all hover:scale-[1.02]" :style="{ background: 'transparent', color: 'var(--danger)', border: '1px solid var(--danger)' }">🗑 重置（清除图片）</button>
                </div>
              </div>
              <div v-else @click="triggerFileInput" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop" class="rounded-lg border-2 border-dashed p-6 flex flex-col items-center gap-2 cursor-pointer transition-all" :style="{ borderColor: isDragging ? 'var(--accent)' : 'var(--line)', background: isDragging ? 'var(--hover)' : 'transparent' }">
                <div class="text-3xl">📁</div>
                <div class="text-sm font-medium" :style="{ color: 'var(--text)' }">{{ isCompressing ? '正在压缩处理…' : '点击选择或拖拽图片到此处' }}</div>
                <div class="text-xs text-center" :style="{ color: 'var(--muted)' }">支持 JPG / PNG / WebP<br/>推荐尺寸 1920×1080 及以上，建议文件 &lt; 5MB</div>
              </div>
              <input ref="fileInputRef" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="onFileChange"/>
              <div v-if="errorMessage" class="text-xs px-3 py-2 rounded-md" :style="{ background: 'var(--danger-bg)', color: 'var(--danger-text)' }">⚠️ {{ errorMessage }}</div>
              <div v-if="warningMessage && !errorMessage" class="text-xs px-3 py-2 rounded-md" :style="{ background: 'var(--star-bg)', color: 'var(--star-text)' }">⚠️ {{ warningMessage }}</div>
              <div v-if="appearance.degraded" class="text-xs px-3 py-2 rounded-md" :style="{ background: 'var(--star-bg)', color: 'var(--star-text)' }">⚠️ 背景图暂未同步到程序数据目录；请确认本地服务正在运行后重试。</div>
            </div>

            <div v-if="hasImage" class="flex flex-col gap-4 pt-1 border-t" :style="{ borderColor: 'var(--line)' }">
              <div class="flex flex-col gap-1.5 pt-1">
                <label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">适配方式</label>
                <div class="flex gap-2">
                  <button v-for="opt in [{ v: 'cover', t: '铺满裁切' }, { v: 'contain', t: '完整显示' }]" :key="opt.v" @click="fitValue = opt.v" class="flex-1 px-3 py-2 rounded-md text-xs cursor-pointer transition-all" :style="fitValue === opt.v ? { background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' } : { background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }">{{ opt.t }}</button>
                </div>
              </div>
              <div class="flex flex-col gap-1.5">
                <div class="flex items-center justify-between"><label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">不透明度</label><span class="text-xs font-mono" :style="{ color: 'var(--accent)' }">{{ opacityPercent }}%</span></div>
                <input v-model.number="opacityPercent" type="range" min="0" max="100" step="1" class="settings-slider w-full"/>
                <div class="flex gap-2">
                  <button v-for="opt in OPACITY_PRESETS" :key="opt.v" @click="opacityPercent = opt.v" class="flex-1 px-3 py-1.5 rounded-md text-xs cursor-pointer transition-all" :style="opacityPercent === opt.v ? { background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' } : { background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)' }">{{ opt.t }} {{ opt.v }}%</button>
                </div>
                <div v-if="opacityPercent >= 50 && !appearance.glassEnabled" class="text-[10px] leading-snug" :style="{ color: 'var(--star-text)', background: 'var(--star-bg)', borderRadius: '6px', padding: '4px 8px' }">提示：不透明度较高时，建议同时开启上方「玻璃风效果」，否则不透明卡片会遮住大部分壁纸</div>
              </div>
              <div class="flex flex-col gap-1.5">
                <div class="flex items-center justify-between"><label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">模糊度</label><span class="text-xs font-mono" :style="{ color: 'var(--accent)' }">{{ blurValue }}px</span></div>
                <input v-model.number="blurValue" type="range" min="0" max="20" step="1" class="settings-slider w-full"/>
              </div>
              <div class="flex flex-col gap-1.5">
                <div class="flex items-center justify-between"><label class="text-xs font-semibold" :style="{ color: 'var(--text-secondary)' }">亮度</label><span class="text-xs font-mono" :style="{ color: 'var(--accent)' }">{{ brightnessPercent }}%</span></div>
                <input v-model.number="brightnessPercent" type="range" min="50" max="100" step="1" class="settings-slider w-full"/>
              </div>
            </div>

            <div class="flex justify-end gap-2 pt-2 border-t" :style="{ borderColor: 'var(--line)' }">
              <button @click="handleClose" class="btn-glass text-sm rounded-lg px-4 py-2 cursor-pointer">完成</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Toast -->
    <Transition name="nav-toast">
      <div v-if="toast.show" class="fixed top-6 left-1/2 z-[300] px-4 py-2 rounded-lg text-sm font-medium shadow-lg" :style="{ background: toast.type === 'success' ? 'var(--accent)' : toast.type === 'error' ? 'var(--danger)' : 'var(--card)', color: toast.type === 'success' || toast.type === 'error' ? '#fff' : 'var(--text)', border: '1px solid var(--line)', transform: 'translateX(-50%)' }">{{ toast.msg }}</div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.settings-slider { -webkit-appearance: none; appearance: none; height: 6px; border-radius: 3px; background: var(--line); outline: none; cursor: pointer; }
.settings-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 16px; height: 16px; border-radius: 50%; background: var(--accent); border: 2px solid var(--card); box-shadow: 0 1px 3px rgba(0,0,0,0.2); cursor: pointer; }
.settings-slider::-moz-range-thumb { width: 16px; height: 16px; border-radius: 50%; background: var(--accent); border: 2px solid var(--card); cursor: pointer; }
.settings-modal-enter-active, .settings-modal-leave-active { transition: opacity 0.2s ease; }
.settings-modal-enter-active > div:last-child, .settings-modal-leave-active > div:last-child { transition: transform 0.2s ease, opacity 0.2s ease; }
.settings-modal-enter-from, .settings-modal-leave-to { opacity: 0; }
.settings-modal-enter-from > div:last-child, .settings-modal-leave-to > div:last-child { transform: scale(0.96); opacity: 0; }
.nav-toast-enter-active, .nav-toast-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.nav-toast-enter-from, .nav-toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-8px); }
</style>

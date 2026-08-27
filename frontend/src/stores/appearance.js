import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAppearance, saveAppearance } from '../api'

const STORAGE_PREFIX = 'wbidx_'
const STORAGE_KEY = STORAGE_PREFIX + 'appearance'

// 玻璃风变量覆盖：浅色 / 深色两套
// 必须以 inline 方式写入 documentElement（theme store 的预设变量也是 inline 写在 html 上，
// 样式表里的类选择器无法覆盖 inline 变量）
// 设计取向：填充偏实（0.7+）保证文字可读性，玻璃感由 blur + 半透明光边提供；
// 同时加深/提亮文字色，避免鲜艳壁纸下内容发虚
const GLASS_VARS = {
  light: {
    '--card': 'rgba(255, 255, 255, 0.72)',
    '--line': 'rgba(255, 255, 255, 0.65)',
    '--hover': 'rgba(255, 255, 255, 0.6)',
    '--header-bg': 'rgba(255, 255, 255, 0.72)',
    '--header-line': 'rgba(255, 255, 255, 0.65)',
    '--text': '#0f172a',
    '--text-secondary': '#334155',
    '--muted': '#5b6b82',
    '--shadow-sm': '0 2px 8px rgba(31, 38, 135, 0.10)',
    '--shadow': '0 8px 24px rgba(31, 38, 135, 0.16)',
    '--shadow-lg': '0 12px 32px rgba(31, 38, 135, 0.20)',
    '--glass-bg': 'rgba(255, 255, 255, 0.75)',
    '--glass-line': 'rgba(255, 255, 255, 0.7)',
    '--glass-blur': '18px',
    '--glass-saturate': '170%',
  },
  dark: {
    '--card': 'rgba(18, 25, 42, 0.72)',
    '--line': 'rgba(255, 255, 255, 0.16)',
    '--hover': 'rgba(255, 255, 255, 0.13)',
    '--header-bg': 'rgba(18, 25, 42, 0.72)',
    '--header-line': 'rgba(255, 255, 255, 0.16)',
    '--text': '#f8fafc',
    '--text-secondary': '#e2e8f0',
    '--muted': '#aab8d4',
    '--shadow-sm': '0 2px 8px rgba(0, 0, 0, 0.3)',
    '--shadow': '0 8px 24px rgba(0, 0, 0, 0.45)',
    '--shadow-lg': '0 12px 32px rgba(0, 0, 0, 0.55)',
    '--glass-bg': 'rgba(18, 25, 42, 0.72)',
    '--glass-line': 'rgba(255, 255, 255, 0.16)',
    '--glass-blur': '18px',
    '--glass-saturate': '170%',
  },
}
const GLASS_VAR_KEYS = Object.keys(GLASS_VARS.light)

// 壁纸启用时的底色淡化：把不透明的 --bg/--card/--header-bg 换成带主题色调的半透明色，
// 让壁纸能透过所有页面的底色层与大卡片（否则各页面的不透明背景会把壁纸盖死）；
// 若同时开了玻璃风，玻璃变量会盖在这套之上（透明度更高 + 模糊）
const BG_TINT_VARS = {
  light: {
    '--bg': 'rgba(246, 248, 252, 0.28)',
    '--card': 'rgba(255, 255, 255, 0.82)',
    '--header-bg': 'rgba(255, 255, 255, 0.82)',
  },
  dark: {
    '--bg': 'rgba(11, 17, 32, 0.35)',
    '--card': 'rgba(26, 35, 55, 0.82)',
    '--header-bg': 'rgba(18, 25, 42, 0.82)',
  },
}

function loadFromStorage() {
  try { const v = localStorage.getItem(STORAGE_KEY); return v ? JSON.parse(v) : {} } catch { return {} }
}
function saveToStorage(data) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); return true } catch { return false }
}

export const useAppearanceStore = defineStore('appearance', () => {
  const backgroundImage = ref(null)
  const bgOpacity = ref(0.4)
  const bgBlur = ref(0)
  const bgBrightness = ref(1)
  const bgFit = ref('cover')
  const bgEnabled = ref(false)
  const glassEnabled = ref(false)
  const degraded = ref(false)

  function settingsPayload() {
    return { bgOpacity: bgOpacity.value, bgBlur: bgBlur.value, bgBrightness: bgBrightness.value, bgFit: bgFit.value, bgEnabled: bgEnabled.value, glassEnabled: glassEnabled.value }
  }

  function applySettings(settings) {
    if (typeof settings.bgOpacity === 'number') bgOpacity.value = settings.bgOpacity
    if (typeof settings.bgBlur === 'number') bgBlur.value = settings.bgBlur
    if (typeof settings.bgBrightness === 'number') bgBrightness.value = settings.bgBrightness
    if (typeof settings.bgFit === 'string') bgFit.value = settings.bgFit
    if (typeof settings.bgEnabled === 'boolean') bgEnabled.value = settings.bgEnabled
    if (typeof settings.glassEnabled === 'boolean') glassEnabled.value = settings.glassEnabled
  }

  async function init() {
    const s = loadFromStorage()
    const legacyImage = typeof s.backgroundImage === 'string' ? s.backgroundImage : null
    applySettings(s)
    try {
      const remote = await getAppearance()
      applySettings(remote.settings || {})
      backgroundImage.value = remote.imageUrl || null
      if (!backgroundImage.value && legacyImage) {
        try {
          const migrated = await saveAppearance({ settings: settingsPayload(), imageData: legacyImage })
          backgroundImage.value = migrated.imageUrl
          bgEnabled.value = true
        } catch {
          backgroundImage.value = legacyImage
          bgEnabled.value = s.bgEnabled !== false
          degraded.value = true
        }
      }
      if (!backgroundImage.value) bgEnabled.value = false
    } catch {
      degraded.value = true
    }
  }

  function persist() {
    saveToStorage(settingsPayload())
    saveAppearance({ settings: settingsPayload() }).catch(() => { degraded.value = true })
  }

  async function setBackgroundImage(dataUrl) {
    if (!dataUrl) return clearBackgroundImage()
    backgroundImage.value = dataUrl
    bgEnabled.value = true
    applyBgTint()
    try {
      const saved = await saveAppearance({ settings: settingsPayload(), imageData: dataUrl })
      backgroundImage.value = saved.imageUrl
      degraded.value = false
      saveToStorage(settingsPayload())
      return { ok: true }
    } catch (error) {
      degraded.value = true
      return { ok: false, reason: error.message || '背景图保存失败' }
    }
  }
  async function clearBackgroundImage() { backgroundImage.value = null; bgEnabled.value = false; removeBgTint(); saveToStorage(settingsPayload()); try { await saveAppearance({ settings: settingsPayload(), clearImage: true }); degraded.value = false; return { ok: true } } catch (error) { degraded.value = true; return { ok: false, reason: error.message || '背景图清除失败' } } }
  function setBgOpacity(v) { const n = Number(v); if (!Number.isNaN(n)) { bgOpacity.value = Math.max(0, Math.min(1, n)); persist() } }
  function setBgBlur(v) { const n = Number(v); if (!Number.isNaN(n)) { bgBlur.value = Math.max(0, Math.min(50, n)); persist() } }
  function setBgBrightness(v) { const n = Number(v); if (!Number.isNaN(n)) { bgBrightness.value = Math.max(0, Math.min(1, n)); persist() } }
  function setBgFit(v) { if (v === 'cover' || v === 'contain') { bgFit.value = v; persist() } }
  function setEnabled(v) { bgEnabled.value = Boolean(v) && Boolean(backgroundImage.value); if (bgEnabled.value) applyBgTint(); else removeBgTint(); persist() }

  // 玻璃风：把半透明变量以 inline 写入 html（与 theme store 的预设变量同层级竞争）
  function applyGlassVars() {
    if (!glassEnabled.value) return
    const vars = document.documentElement.classList.contains('dark') ? GLASS_VARS.dark : GLASS_VARS.light
    for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v)
  }
  function removeGlassVars() {
    for (const k of GLASS_VAR_KEYS) document.documentElement.style.removeProperty(k)
  }
  // 壁纸底色淡化：以 inline 写入 html（与 theme store 的预设变量同层级竞争）
  function applyBgTint() {
    if (!(bgEnabled.value && backgroundImage.value)) return
    const vars = document.documentElement.classList.contains('dark') ? BG_TINT_VARS.dark : BG_TINT_VARS.light
    for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v)
    // 若玻璃风同时开启，重新盖回玻璃变量（玻璃是更强的用户显式选择）
    applyGlassVars()
  }
  function removeBgTint() {
    for (const k of Object.keys(BG_TINT_VARS.light)) document.documentElement.style.removeProperty(k)
  }

  // 主题切换（明暗/预设）后由调用方重新应用：先壁纸淡化再玻璃覆盖，保证优先级正确
  function reapplyOverrides() { applyBgTint(); applyGlassVars() }
  function setGlassEnabled(v) {
    glassEnabled.value = Boolean(v)
    if (glassEnabled.value) {
      applyGlassVars()
    } else {
      removeGlassVars()
      applyBgTint() // 移除玻璃变量后恢复壁纸淡化值（若壁纸开启）
    }
    persist()
  }

  return { backgroundImage, bgOpacity, bgBlur, bgBrightness, bgFit, bgEnabled, glassEnabled, degraded, init, setBackgroundImage, clearBackgroundImage, setBgOpacity, setBgBlur, setBgBrightness, setBgFit, setEnabled, setGlassEnabled, reapplyOverrides }
})

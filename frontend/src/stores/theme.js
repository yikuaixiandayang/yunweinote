import { defineStore } from 'pinia'
import { ref } from 'vue'
import { THEME_PRESETS } from '../constants/themes'

const HEX_RE = /^#[0-9a-f]{6}$/i

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(false)
  const preset = ref(localStorage.getItem('wbidx_theme_preset') || 'default')
  const customColors = ref({ accent: null, accent2: null })
  const customEnabled = ref(false)
  const themeVersion = ref(0)

  function applyPresetVars() {
    const p = THEME_PRESETS[preset.value] || THEME_PRESETS.default
    const vars = isDark.value ? p.dark : p.light
    const root = document.documentElement
    for (const [k, v] of Object.entries(vars)) {
      root.style.setProperty(k, v)
    }
    // 自定义色覆盖（仅启用时）
    if (customEnabled.value) {
      if (customColors.value.accent) root.style.setProperty('--accent', customColors.value.accent)
      if (customColors.value.accent2) root.style.setProperty('--accent2', customColors.value.accent2)
      const a = customColors.value.accent || vars['--accent']
      const a2 = customColors.value.accent2 || vars['--accent2']
      root.style.setProperty('--accent-gradient', `linear-gradient(135deg, ${a}, ${a2})`)
    }
  }

  function apply() {
    document.documentElement.classList.toggle('dark', isDark.value)
    applyPresetVars()
    themeVersion.value++
  }

  function init() {
    const saved = localStorage.getItem('wbidx_theme')
    isDark.value = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
    // 恢复自定义色
    try {
      const cs = JSON.parse(localStorage.getItem('wbidx_theme_custom') || '{}')
      if (cs.accent && HEX_RE.test(cs.accent)) customColors.value.accent = cs.accent
      if (cs.accent2 && HEX_RE.test(cs.accent2)) customColors.value.accent2 = cs.accent2
      customEnabled.value = localStorage.getItem('wbidx_theme_custom_enabled') === '1'
    } catch {}
    apply()
  }

  function toggle() {
    isDark.value = !isDark.value
    localStorage.setItem('wbidx_theme', isDark.value ? 'dark' : 'light')
    apply()
  }

  function setPreset(key) {
    if (!THEME_PRESETS[key]) return
    preset.value = key
    localStorage.setItem('wbidx_theme_preset', key)
    // 切预设清空自定义色
    customColors.value = { accent: null, accent2: null }
    customEnabled.value = false
    localStorage.removeItem('wbidx_theme_custom')
    localStorage.removeItem('wbidx_theme_custom_enabled')
    apply()
  }

  function setCustomColor(key, val) {
    if (key !== 'accent' && key !== 'accent2') return
    if (val === null) {
      customColors.value = { ...customColors.value, [key]: null }
    } else if (typeof val === 'string' && HEX_RE.test(val)) {
      customColors.value = { ...customColors.value, [key]: val.toLowerCase() }
    } else return
    localStorage.setItem('wbidx_theme_custom', JSON.stringify(customColors.value))
    if (!customEnabled.value) { customEnabled.value = true; localStorage.setItem('wbidx_theme_custom_enabled', '1') }
    apply()
  }

  function enableCustom() {
    customEnabled.value = true
    // 用当前预设色填充作为起点
    const p = THEME_PRESETS[preset.value] || THEME_PRESETS.default
    const vars = isDark.value ? p.dark : p.light
    if (!customColors.value.accent) customColors.value.accent = vars['--accent']
    if (!customColors.value.accent2) customColors.value.accent2 = vars['--accent2']
    localStorage.setItem('wbidx_theme_custom', JSON.stringify(customColors.value))
    localStorage.setItem('wbidx_theme_custom_enabled', '1')
    apply()
  }

  function resetCustomColors() {
    customColors.value = { accent: null, accent2: null }
    customEnabled.value = false
    localStorage.removeItem('wbidx_theme_custom')
    localStorage.removeItem('wbidx_theme_custom_enabled')
    apply()
  }

  return { isDark, preset, customColors, customEnabled, themeVersion, init, toggle, apply, setPreset, setCustomColor, enableCustom, resetCustomColors }
})

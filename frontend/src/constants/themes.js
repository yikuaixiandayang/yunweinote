/**
 * 主题预设（4 套配色方案）
 * 每套仅改变 accent / accent2 / accent-gradient，中性灰阶所有预设共用。
 * theme store apply() 时按 isDark 选对应变量集写入 documentElement。
 */

// 中性灰阶（light）—— 对齐 style.css :root 默认值，仅改 accent 色调
const NEUTRAL_LIGHT = {
  '--bg': '#f6f8fc', '--bg-subtle': '#f1f4fa', '--card': '#ffffff',
  '--line': '#e5e9f0', '--text': '#1e293b', '--text-secondary': '#475569',
  '--muted': '#94a3b8', '--hover': '#f1f5f9',
}
// 中性灰阶（dark）—— 对齐 style.css .dark 默认值
const NEUTRAL_DARK = {
  '--bg': '#0b1120', '--bg-subtle': '#111827', '--card': '#1a2332',
  '--line': '#2d3a4f', '--text': '#e2e8f0', '--text-secondary': '#cbd5e1',
  '--muted': '#8b9dc3', '--hover': '#1f2a3f',
}

function makePreset(la, la2, da, da2) {
  return {
    light: { ...NEUTRAL_LIGHT, '--accent': la, '--accent2': la2, '--accent-gradient': `linear-gradient(135deg, ${la}, ${la2})` },
    dark: { ...NEUTRAL_DARK, '--accent': da, '--accent2': da2, '--accent-gradient': `linear-gradient(135deg, ${da}, ${da2})` },
  }
}

export const THEME_PRESETS = {
  default: { name: '默认蓝紫', icon: '🔵', ...makePreset('#2563eb', '#0ea5e9', '#60a5fa', '#38bdf8') },
  aurora:  { name: '极光',     icon: '🌌', ...makePreset('#0d9488', '#7c3aed', '#2dd4bf', '#a78bfa') },
  coral:   { name: '珊瑚',     icon: '🪸', ...makePreset('#e11d48', '#ea580c', '#fb7185', '#fb923c') },
  rose:    { name: '玫瑰金',   icon: '🌹', ...makePreset('#d1477e', '#b07d3a', '#f2a4c8', '#e0b475') },
  lavender:{ name: '薰衣草',   icon: '💜', ...makePreset('#7c3aed', '#c026d3', '#a78bfa', '#e879f9') },
  morandi: { name: '雾霾蓝',   icon: '🌫️', ...makePreset('#5c7fa3', '#8a7bb8', '#a3c0e0', '#bdaede') },
  mint:    { name: '青柠',     icon: '🍃', ...makePreset('#059669', '#65a30d', '#34d399', '#a3e635') },
  cyber:   { name: '赛博朋克', icon: '🤖', ...makePreset('#06b6d4', '#ec4899', '#22d3ee', '#f472b6') },
  forest:  { name: '森林',     icon: '🌲', ...makePreset('#16a34a', '#ca8a04', '#4ade80', '#fbbf24') },
  sunset:  { name: '暖阳',     icon: '🌅', ...makePreset('#ea580c', '#d97706', '#fb923c', '#fbbf24') },
}

export const THEME_PRESET_KEYS = Object.keys(THEME_PRESETS)

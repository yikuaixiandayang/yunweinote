// 公共 Markdown 渲染模块：详情面板与全屏阅读页共用同一套渲染链路，
// 确保标题锚点 id 一致（大纲点击定位依赖它）。
import { marked } from 'marked'
import { sanitizeHtml } from './safeHtml.js'

/**
 * Typora 风格标题 slug 化：与 marked 渲染出的标题锚点 id 保持一致。
 * 大纲点击时用同一函数生成 id，scrollIntoView 到对应标题。
 */
export function slugifyTitle(t) {
  const s = String(t || '').trim().toLowerCase().replace(/\s+/g, '-')
  return s.replace(/[^\p{L}\p{N}\-_]/gu, '').replace(/-+/g, '-') || 'sec'
}

function rendererText(tokens) {
  return (tokens || [])
    .map(t => (t.tokens ? rendererText(t.tokens) : (t.text ?? t.raw ?? '')))
    .join('')
}

// 为 h1/h2/h3 注入 id 锚点，供章节大纲点击定位。
// marked.use 是全局配置且幂等：多次调用按 key 合并/覆盖 renderer，行为一致。
marked.use({
  renderer: {
    heading({ tokens, depth }) {
      const text = rendererText(tokens)
      const id = slugifyTitle(text)
      return `<h${depth} id="${id}">${text}</h${depth}>`
    },
  },
})

/** Markdown 文本 → 安全 HTML（注入标题锚点 + 去除危险标签/事件属性） */
export function renderMarkdown(text) {
  return sanitizeHtml(marked.parse(text || ''))
}

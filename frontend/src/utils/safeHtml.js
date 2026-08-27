// Markdown and search data can come from files outside the application.
// Keep v-html constrained to a small, safe subset without requiring a runtime dependency.
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[ch])
}

export function highlightHtml(value, query) {
  const source = escapeHtml(value)
  if (!query) return source
  const escapedQuery = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return source.replace(new RegExp(`(${escapedQuery})`, 'gi'), '<mark>$1</mark>')
}

export function sanitizeHtml(html) {
  if (typeof DOMParser === 'undefined') return ''
  const doc = new DOMParser().parseFromString(String(html ?? ''), 'text/html')
  doc.querySelectorAll('script,style,iframe,object,embed,form,link,meta').forEach(node => node.remove())
  doc.querySelectorAll('*').forEach(node => {
    [...node.attributes].forEach(attr => {
      const name = attr.name.toLowerCase()
      const value = attr.value.trim().toLowerCase()
      if (name.startsWith('on') || (name === 'href' || name === 'src') && value.startsWith('javascript:')) {
        node.removeAttribute(attr.name)
      }
    })
  })
  return doc.body.innerHTML
}

const ACCEPTED_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
const ACCEPTED_EXTS = ['.jpg', '.jpeg', '.png', '.webp']
const WARN_SIZE = 5 * 1024 * 1024
const REJECT_SIZE = 10 * 1024 * 1024

export function validateImageFile(file) {
  if (!file) return { ok: false, reason: '未选择文件' }
  const mimeOk = ACCEPTED_TYPES.includes(file.type)
  const extOk = ACCEPTED_EXTS.some(ext => file.name.toLowerCase().endsWith(ext))
  if (!mimeOk && !extOk) return { ok: false, reason: '仅支持 JPG / PNG / WebP 格式' }
  if (file.size > REJECT_SIZE) return { ok: false, reason: `文件过大（${(file.size/1024/1024).toFixed(1)}MB），请使用小于 10MB 的图片` }
  if (file.size > WARN_SIZE) return { ok: true, warning: `图片较大（${(file.size/1024/1024).toFixed(1)}MB），压缩可能需要数秒` }
  return { ok: true }
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片加载失败')) }
    img.src = url
  })
}

export async function compressImage(file, maxW = 1920, quality = 0.8) {
  const img = await loadImage(file)
  let { width, height } = img
  if (width > maxW || height > maxW) {
    if (width >= height) { height = Math.round((height * maxW) / width); width = maxW }
    else { width = Math.round((width * maxW) / height); height = maxW }
  }
  const canvas = document.createElement('canvas')
  canvas.width = width; canvas.height = height
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, width, height)
  ctx.drawImage(img, 0, 0, width, height)
  return canvas.toDataURL('image/jpeg', quality)
}

export function estimateDataUrlSize(dataUrl) {
  if (!dataUrl) return 0
  const idx = dataUrl.indexOf(',')
  const base64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl
  return Math.floor(base64.length * 0.75)
}

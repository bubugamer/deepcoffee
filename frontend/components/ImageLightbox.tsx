'use client'
// 图片放大查看 + 下载弹窗。聊天里的缩略图点击后传入 src 即弹出大图；src 为 null 时不渲染。
// 跨域图片（Supabase Storage 公开 URL）的 download 属性会被浏览器忽略，所以下载统一走
// fetch → blob → 临时 <a download> 的方式，data URL（刚发送的图）同样适用。
import { useEffect } from 'react'
import { X, Download } from 'lucide-react'

function fileNameFor(src: string): string {
  // Supabase 形如 …/<uuid>.jpg：取末段且像文件名就用它
  const last = src.split('?')[0].split('/').pop() ?? ''
  if (last && /\.[a-z0-9]{2,4}$/i.test(last) && !last.startsWith('data:')) return last
  const mime = src.startsWith('data:') ? src.slice(5, src.indexOf(';')) : ''
  const ext = mime.includes('png') ? 'png' : mime.includes('webp') ? 'webp' : 'jpg'
  return `deepcoffee-image-${Date.now()}.${ext}`
}

async function downloadImage(src: string): Promise<void> {
  try {
    const res = await fetch(src)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileNameFor(src)
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    // 极少数 CORS 拦截 fetch 时兜底：新标签打开，用户可右键保存
    window.open(src, '_blank', 'noopener')
  }
}

export default function ImageLightbox({ src, onClose }: { src: string | null; onClose: () => void }) {
  useEffect(() => {
    if (!src) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [src, onClose])

  if (!src) return null

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <button
          onClick={(e) => { e.stopPropagation(); void downloadImage(src) }}
          aria-label="下载图片"
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
        >
          <Download size={18} />
        </button>
        <button
          onClick={onClose}
          aria-label="关闭"
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
        >
          <X size={18} />
        </button>
      </div>
      {/* 点图片本身不关闭，只点遮罩空白处才关 */}
      <img
        src={src}
        alt="图片大图"
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] max-w-[92vw] object-contain rounded-lg shadow-2xl"
      />
    </div>
  )
}

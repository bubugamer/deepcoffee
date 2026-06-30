import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'DeepCoffee · 精品咖啡 AI 助手',
  description: '用对话记录一杯咖啡，读懂一杯咖啡。Your AI assistant for coffee.',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: '/icon.png',
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#8a5a2b',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-dc-bg min-h-dvh font-sans antialiased">
        {children}
      </body>
    </html>
  )
}

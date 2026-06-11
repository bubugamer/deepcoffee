'use client'
import Link from 'next/link'
import { useState, useEffect } from 'react'
import { Menu, X } from 'lucide-react'
import { usePathname } from 'next/navigation'

const navLinks = [
  { href: '/#features', label: '功能' },
  { href: '/knowledge',  label: '知识库' },
  { href: '/#pricing',   label: '定价' },
]

export default function PublicNav({ transparent = false }: { transparent?: boolean }) {
  const [open, setOpen] = useState(false)
  const path = usePathname()

  useEffect(() => { setOpen(false) }, [path])

  return (
    <>
      <header className={`h-16 sticky top-0 z-50 border-b border-dc-border ${transparent ? 'bg-dc-bg/80 backdrop-blur-sm' : 'bg-dc-bg'}`}>
        <div className="max-w-6xl mx-auto h-full px-4 sm:px-6 flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5">
            <img src="/logo.png" alt="DeepCoffee" className="h-8 w-8 object-contain" />
            <span className="text-lg font-extrabold tracking-tight text-dc-text-1">DeepCoffee</span>
          </Link>

          {/* Desktop nav links */}
          <nav className="hidden md:flex items-center gap-6">
            {navLinks.map(({ href, label }) => (
              <Link key={href} href={href} className="text-sm text-dc-text-2 hover:text-dc-text-1 transition-colors">
                {label}
              </Link>
            ))}
          </nav>

          {/* Desktop actions */}
          <div className="hidden md:flex items-center gap-3">
            <Link href="/auth" className="text-sm text-dc-text-2 hover:text-dc-text-1 transition-colors">
              登录
            </Link>
            <Link href="/auth?tab=register" className="btn-primary text-sm px-4 py-2">
              免费注册
            </Link>
          </div>

          {/* Mobile: login + hamburger */}
          <div className="md:hidden flex items-center gap-2">
            <Link href="/auth" className="text-sm text-dc-text-2 px-3 py-1.5 rounded-lg hover:bg-dc-subtle transition-colors">
              登录
            </Link>
            <button
              onClick={() => setOpen(o => !o)}
              aria-label="菜单"
              className="p-2 text-dc-text-2 rounded-lg hover:bg-dc-subtle transition-colors"
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile dropdown menu */}
      {open && (
        <div className="md:hidden fixed top-16 left-0 right-0 z-40 bg-dc-bg border-b border-dc-border shadow-lg">
          <nav className="max-w-6xl mx-auto px-4 py-3 flex flex-col gap-1">
            {navLinks.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="text-sm text-dc-text-2 py-2.5 px-3 rounded-lg hover:bg-dc-subtle hover:text-dc-text-1 transition-colors"
              >
                {label}
              </Link>
            ))}
            <div className="pt-2 border-t border-dc-border mt-1">
              <Link
                href="/auth?tab=register"
                className="btn-primary text-sm w-full text-center py-2.5 block"
              >
                免费注册
              </Link>
            </div>
          </nav>
        </div>
      )}
    </>
  )
}

'use client'
import { useEffect, useState } from 'react'
import { Database, Info, Loader2 } from 'lucide-react'
import { getAdminStats, type AdminStats } from '@/lib/api/admin'

const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? '0.28.0'

export default function AdminAboutPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAdminStats()
      .then(setStats)
      .catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [])

  if (error) return <div className="text-sm text-dc-red">{error}</div>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-dc-text-1">关于</h2>
        <p className="text-sm text-dc-text-3 mt-1">DeepCoffee 当前线上信息。</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="dc-card p-5 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-dc-accent-light text-dc-accent flex items-center justify-center flex-shrink-0">
            <Info size={18} />
          </div>
          <div>
            <div className="text-xs text-dc-text-3 mb-1">版本号</div>
            <div className="text-2xl font-bold text-dc-text-1">{APP_VERSION}</div>
          </div>
        </div>

        <div className="dc-card p-5 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-dc-accent-light text-dc-accent flex items-center justify-center flex-shrink-0">
            <Database size={18} />
          </div>
          <div>
            <div className="text-xs text-dc-text-3 mb-1">公共实体库</div>
            {stats ? (
              <div className="text-base font-semibold text-dc-text-1">
                公共实体库现有 active 实体 {stats.active_entity_count} 个。
              </div>
            ) : (
              <div className="flex items-center text-dc-text-3 text-sm">
                <Loader2 size={15} className="animate-spin mr-2" />加载中…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

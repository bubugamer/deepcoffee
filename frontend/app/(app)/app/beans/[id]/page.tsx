'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { ArrowLeft, ClipboardList, MessageSquare } from 'lucide-react'
import { getBean } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'
import { recommendedParamRows } from '@/lib/beans'
import { RecommendParamsChat } from '@/components/RecommendParamsChat'
import type { Bean } from '@/types'

function Dots({ value, max = 5 }: { value?: number | null; max?: number }) {
  const safeMax = Math.max(1, Math.round(max))
  const safeValue = Math.max(0, Math.min(safeMax, Math.round(value ?? 0)))
  return (
    <div className="flex gap-1">
      {Array.from({ length: safeMax }, (_, index) => (
        <span
          key={index}
          className={`w-2 h-2 rounded-full border ${
            index < safeValue ? 'bg-dc-accent border-dc-accent' : 'border-dc-border'
          }`}
        />
      ))}
    </div>
  )
}

export default function BeanDetailPage() {
  const params = useParams()
  const id = typeof params.id === 'string' ? params.id : Array.isArray(params.id) ? params.id[0] : ''
  const [bean, setBean] = useState<Bean | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getBean(id, getToken())
      .then((item) => {
        if (!cancelled) setBean(item)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '豆卡加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [id])

  if (loading) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回豆仓
        </Link>
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载豆卡…</div>
      </div>
    )
  }

  if (error && !bean) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回豆仓
        </Link>
        <div className="dc-card p-6">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">豆卡暂时不可用</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      </div>
    )
  }

  if (!bean) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回豆仓
        </Link>
        <div className="dc-card p-8 text-center">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有找到这张豆卡</div>
          <p className="text-sm text-dc-text-3">它可能已被删除，或当前账户没有权限查看。</p>
        </div>
      </div>
    )
  }

  const rows: [string, string | null | undefined][] = [
    ['烘焙商', bean.roaster],
    ['烘焙商产品', bean.roaster_product],
    ['生产者/庄园/处理站', bean.coffee_source],
    ['生豆商/进口商', bean.green_bean_merchant],
    ['生豆商产品', bean.green_bean_product],
    ['产地', bean.origin],
    ['处理法', bean.process],
    ['品种', bean.varietal.join(' / ')],
  ]
  const paramRows = recommendedParamRows(bean.recommended_params)

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
        <ArrowLeft size={15} />
        返回豆仓
      </Link>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-dc-text-1 mb-2">{bean.name}</h1>
          <div className="flex flex-wrap gap-2">
            {bean.roaster && <span className="dc-tag">{bean.roaster}</span>}
            {bean.origin && <span className="dc-tag">{bean.origin}</span>}
            {bean.process && <span className="dc-tag">{bean.process}</span>}
          </div>
        </div>
        {bean.avg_score !== null && bean.avg_score !== undefined && (
          <div className="w-14 h-14 rounded-full bg-dc-accent-light flex items-center justify-center flex-shrink-0">
            <div className="text-center">
              <span className="text-xl font-extrabold text-dc-accent">{bean.avg_score}</span>
              <span className="text-xs text-dc-text-3 block leading-none">/5</span>
            </div>
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-[1fr_300px] gap-6">
        <div className="space-y-5">
          <div className="dc-card p-5">
            <h2 className="section-title mb-4">豆卡信息</h2>
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
              {rows.filter(([, value]) => value).map(([label, value]) => (
                <div key={label}>
                  <div className="text-xs text-dc-text-3 mb-0.5">{label}</div>
                  <div className="text-sm font-medium text-dc-text-1">{value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="dc-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="section-title">风味信息</h2>
              <span className="text-xs text-dc-text-3">
                {bean.flavor.source === 'roaster' ? '烘焙商维度' : bean.flavor.source === 'user' ? '用户维度' : '默认维度'}
              </span>
            </div>
            {bean.flavor.notes.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-4">
                {bean.flavor.notes.map((note) => (
                  <span key={note} className="dc-tag">{note}</span>
                ))}
              </div>
            )}
            {bean.flavor.axes.length > 0 ? (
              <div className="grid sm:grid-cols-2 gap-3">
                {bean.flavor.axes.map((axis) => (
                  <div key={axis.label} className="flex items-center justify-between gap-3">
                    <span className="text-sm text-dc-text-2">{axis.label}</span>
                    <Dots value={axis.value} max={bean.flavor.scale_max} />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-dc-text-3">暂未记录风味维度。</p>
            )}
          </div>

          {bean.private_notes && (
            <div className="dc-card p-5">
              <h2 className="section-title mb-3">私有备注</h2>
              <p className="text-sm text-dc-text-2 leading-relaxed">{bean.private_notes}</p>
            </div>
          )}
        </div>

        <div className="space-y-5">
          <div className="dc-card p-5">
            <h2 className="section-title mb-4">建议冲煮参数</h2>
            {paramRows.length > 0 ? (
              <div className="space-y-3">
                {paramRows.map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-3 text-sm">
                    <span className="text-dc-text-3">{label}</span>
                    <span className="font-medium text-dc-text-1 text-right">{value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-dc-text-3 leading-relaxed mb-4">
                暂无建议参数，可以由 Coffea 生成，或从一条冲煮记录设为建议值。
              </p>
            )}
            <div className="mt-4">
              <RecommendParamsChat
                beanId={bean.bean_id}
                hasParams={paramRows.length > 0}
                onCompleted={(params, recordId) =>
                  setBean((b) =>
                    b
                      ? { ...b, recommended_params: params, recommended_record_id: recordId, updated_at: new Date().toISOString() }
                      : b,
                  )
                }
              />
            </div>
          </div>

          <Link
            href={`/app/records?bean=${encodeURIComponent(bean.name)}`}
            className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block"
          >
            <div className="w-9 h-9 rounded-full bg-dc-accent-light flex-shrink-0 flex items-center justify-center">
              <ClipboardList size={16} className="text-dc-accent" strokeWidth={1.8} />
            </div>
            <div>
              <div className="text-sm font-medium text-dc-text-1">查看冲煮记录</div>
              <div className="text-xs text-dc-text-3">共 {bean.record_count} 条</div>
            </div>
          </Link>

          <Link
            href={`/app/chat?new=1&bean_id=${encodeURIComponent(bean.bean_id)}`}
            className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block"
          >
            <div className="w-9 h-9 rounded-full bg-dc-accent flex-shrink-0 flex items-center justify-center">
              <MessageSquare size={16} className="text-white" strokeWidth={1.8} />
            </div>
            <div>
              <div className="text-sm font-medium text-dc-text-1">记录一次冲煮</div>
              <div className="text-xs text-dc-text-3">自动关联到这张豆卡</div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  )
}

'use client'
import { useEffect, useRef, useState } from 'react'
import { Loader2, Send, Sparkles } from 'lucide-react'
import { recommendParamsTurn, recommendationToBeanParams } from '@/lib/api/beans'
import { isQuotaExceeded } from '@/lib/api/client'
import { QuotaNotice } from '@/components/QuotaNotice'
import { getToken } from '@/lib/auth'
import type { BeanRecommendedParams } from '@/types'

interface Turn {
  role: 'assistant' | 'user'
  text: string
}

/**
 * 多轮「生成建议参数」对话。
 * 首轮无 message，后端通常返回 needs_input 追问器具；用户补充后返回 completed/fallback。
 * 完成时通过 onCompleted 把建议参数回传给父组件展示与保存。
 */
export function RecommendParamsChat({
  beanId,
  hasParams,
  onCompleted,
}: {
  beanId: string
  hasParams: boolean
  onCompleted: (params: BeanRecommendedParams, recordId: string | null) => void
}) {
  const [active, setActive] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [quotaMsg, setQuotaMsg] = useState('')   // 402 ai_quota_exceeded：展示升级引导
  const [done, setDone] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, loading])

  async function runTurn(message?: string) {
    setLoading(true)
    setError('')
    setQuotaMsg('')
    try {
      const res = await recommendParamsTurn(beanId, { session_id: sessionId, message }, getToken())
      setSessionId(res.session_id)
      setTurns((cur) => [...cur, { role: 'assistant', text: res.assistant_message }])
      if (res.status === 'completed' || res.status === 'fallback') {
        if (res.recommendation) {
          onCompleted(
            recommendationToBeanParams(res.recommendation, res.recommended_record_id),
            res.recommended_record_id ?? null,
          )
        }
        setDone(true)
      }
    } catch (err) {
      if (isQuotaExceeded(err)) {
        setQuotaMsg(err.message)
      } else {
        setError(err instanceof Error ? err.message : '生成失败，请稍后重试。')
      }
    } finally {
      setLoading(false)
    }
  }

  async function start() {
    setActive(true)
    setDone(false)
    setTurns([])
    setSessionId(null)
    await runTurn()
  }

  async function send() {
    const t = input.trim()
    if (!t || loading) return
    setInput('')
    setTurns((cur) => [...cur, { role: 'user', text: t }])
    await runTurn(t)
  }

  if (!active) {
    return (
      <button
        onClick={start}
        className="btn-primary text-sm py-2 w-full flex items-center justify-center gap-1.5"
      >
        <Sparkles size={14} />
        {hasParams ? '重新生成建议参数' : '生成建议参数'}
      </button>
    )
  }

  return (
    <div className="rounded-xl border border-dc-border bg-dc-subtle/50 p-3">
      <div ref={scrollRef} className="max-h-56 overflow-y-auto space-y-2.5 mb-2">
        {turns.map((turn, i) => (
          <div key={i} className={`flex ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`text-sm leading-relaxed px-3 py-2 rounded-2xl max-w-[85%] ${
                turn.role === 'user'
                  ? 'bg-dc-accent text-white rounded-br-sm'
                  : 'bg-white border border-dc-border text-dc-text-1 rounded-tl-sm'
              }`}
            >
              {turn.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-dc-border rounded-2xl rounded-tl-sm px-3 py-2 flex gap-1 items-center">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-dc-text-3 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s`, animationDuration: '1.2s' }}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {error && <p className="text-xs text-dc-red mb-2">{error}</p>}
      {quotaMsg && <div className="mb-2"><QuotaNotice message={quotaMsg} /></div>}

      {done ? (
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-dc-green">已保存到豆卡</span>
          <button onClick={start} className="text-xs text-dc-text-3 hover:text-dc-accent">
            重新生成
          </button>
        </div>
      ) : (
        <div className="flex gap-2 items-end">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            disabled={loading}
            placeholder="例如：V60 + C40，漂白滤纸"
            className="dc-input text-sm flex-1 disabled:opacity-50"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="btn-primary p-2 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </div>
      )}
    </div>
  )
}

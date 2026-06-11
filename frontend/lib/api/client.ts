import { getToken } from '@/lib/auth'

// Server Components (SSR inside Docker) use the internal service name to reach
// the api container. Browsers always use the public-facing URL.
// API_INTERNAL_URL is only injected in Docker (e.g. http://api:8000).
// When not set it falls back to NEXT_PUBLIC_API_BASE_URL, preserving current behaviour.
const API_BASE =
  typeof window === 'undefined'
    ? (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? '')
    : (process.env.NEXT_PUBLIC_API_BASE_URL ?? '')

export const isApiEnabled = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL)

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// AI 接口（知识库问答、冲煮/豆袋解析、推荐参数、coffea 消息）用满额度时
// 返回 402 ai_quota_exceeded，应展示「升级 Pro」引导而非普通报错红条。
export function isQuotaExceeded(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 402 && err.code === 'ai_quota_exceeded'
}

export async function apiFetch<T>(path: string, init?: RequestInit & { token?: string | null }): Promise<T> {
  const { token: explicitToken, headers, ...requestInit } = init ?? {}
  const token = explicitToken ?? getToken()
  const res = await fetch(`${API_BASE}/v1${path}`, {
    ...requestInit,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = (body.error ?? body.detail ?? body) as Record<string, string>
    throw new ApiError(res.status, detail.code ?? 'api_error', detail.message ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

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

// 普通请求默认超时（毫秒）：防止网络卡住时界面永久挂起。
// 调用方传了自己的 signal（如聊天的停止/超时控制）则不再叠加默认超时。
const DEFAULT_TIMEOUT_MS = 45_000

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { token?: string | null; timeoutMs?: number },
): Promise<T> {
  const { token: explicitToken, headers, timeoutMs, signal: externalSignal, ...requestInit } = init ?? {}
  const token = explicitToken ?? getToken()

  // 没有外部 signal 时挂一个自动超时；有外部 signal 则交给调用方控制。
  let timer: ReturnType<typeof setTimeout> | undefined
  let signal = externalSignal
  if (!externalSignal) {
    const controller = new AbortController()
    signal = controller.signal
    timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), timeoutMs ?? DEFAULT_TIMEOUT_MS)
  }

  try {
    const res = await fetch(`${API_BASE}/v1${path}`, {
      ...requestInit,
      signal,
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
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      throw new ApiError(408, 'timeout', '请求超时，请检查网络后重试。')
    }
    throw err
  } finally {
    if (timer) clearTimeout(timer)
  }
}

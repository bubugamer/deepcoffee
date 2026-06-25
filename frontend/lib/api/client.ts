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

// 普通请求默认超时（毫秒）：移动网络抖动时「快速失败 + 自动重试」胜过干等。
// 仍 > 后端冷启动（约 7–8s），留足余量；调用方可用 timeoutMs 覆盖（如聊天用更长）。
const DEFAULT_TIMEOUT_MS = 15_000
// 读请求（GET/HEAD）默认自动重试次数：移动端偶发丢包/超时,一次重试通常即自愈。
const DEFAULT_GET_RETRIES = 1
// 重试退避基数（毫秒）：第 n 次重试前等 RETRY_BACKOFF_MS * n。
const RETRY_BACKOFF_MS = 600

function isRetryableMethod(method?: string): boolean {
  const m = (method ?? 'GET').toUpperCase()
  return m === 'GET' || m === 'HEAD'
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { token?: string | null; timeoutMs?: number; retry?: number },
): Promise<T> {
  const { token: explicitToken, headers, timeoutMs, retry, signal: externalSignal, ...requestInit } = init ?? {}
  const token = explicitToken ?? getToken()
  const mergedHeaders = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers ?? {}),
  }

  // 重试次数：调用方显式 retry 优先；否则读请求默认重试、写请求不重试（避免重复建卡/重复提交）。
  // 调用方自管中止（传了外部 signal，如聊天）时不重试,完全交给调用方控制。
  const maxAttempts =
    1 + (externalSignal ? 0 : retry ?? (isRetryableMethod(requestInit.method) ? DEFAULT_GET_RETRIES : 0))

  let lastErr: unknown
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    // 没有外部 signal 时挂自动超时；有则交给调用方控制。
    // 用 timedOut 标志（而非 err.name）判定超时：iOS/WebKit 不采纳 abort(reason)，fetch 会抛
    // 它自己的 AbortError（message="Fetch is aborted"），靠 name==='TimeoutError' 判会漏成英文原文。
    let timer: ReturnType<typeof setTimeout> | undefined
    let timedOut = false
    let signal = externalSignal ?? undefined
    if (!externalSignal) {
      const controller = new AbortController()
      signal = controller.signal
      timer = setTimeout(() => {
        timedOut = true
        controller.abort()
      }, timeoutMs ?? DEFAULT_TIMEOUT_MS)
    }

    try {
      const res = await fetch(`${API_BASE}/v1${path}`, {
        ...requestInit,
        signal,
        headers: mergedHeaders,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const detail = (body.error ?? body.detail ?? body) as Record<string, string>
        throw new ApiError(res.status, detail.code ?? 'api_error', detail.message ?? `HTTP ${res.status}`)
      }
      return (await res.json()) as T
    } catch (err) {
      // 我们自己的超时（含 iOS 路径）统一转成中文友好提示，与浏览器内核无关。
      const normalized = timedOut ? new ApiError(408, 'timeout', '请求超时，请检查网络后重试。') : err
      lastErr = normalized
      // 4xx 业务错误（401/403/404/422/402 等）重试无意义；仅超时 / 5xx / 网络层失败才重试。
      const isClientError =
        normalized instanceof ApiError &&
        normalized.status >= 400 &&
        normalized.status < 500 &&
        normalized.code !== 'timeout'
      if (isClientError || attempt >= maxAttempts) {
        throw normalized
      }
      await sleep(RETRY_BACKOFF_MS * attempt)
    } finally {
      if (timer) clearTimeout(timer)
    }
  }
  // 理论不可达（循环要么 return 要么 throw），保险起见。
  throw lastErr
}

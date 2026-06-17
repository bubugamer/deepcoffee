import { createClient } from '@supabase/supabase-js'

const supabaseUrl  = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

// 显式开启会话持久化与自动刷新：access_token 默认 1 小时过期，靠长效 refresh token 自动换新，
// 让登录态在移动端也能持久；过期判断以 supabase.auth.getSession() 为准（见 AppLayout 鉴权守卫）。
export const supabase = createClient(supabaseUrl, supabaseAnon, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
})

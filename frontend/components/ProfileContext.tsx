'use client'
// AppLayout 取到的账户信息通过 context 下发，避免子布局（如 /admin 守卫）重复请求 /me
// 造成「校验权限…」的二次等待。
import { createContext, useContext } from 'react'
import type { UserProfile } from '@/types'

interface ProfileContextValue {
  profile: UserProfile | null
  loading: boolean
}

export const ProfileContext = createContext<ProfileContextValue>({ profile: null, loading: true })

export function useProfile(): ProfileContextValue {
  return useContext(ProfileContext)
}

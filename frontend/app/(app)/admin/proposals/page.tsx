// 旧路由：审核已合并到 /admin/review（提案 | 候选事实 | 实体库 三个 tab）。
import { redirect } from 'next/navigation'

export default function LegacyProposalsPage() {
  redirect('/admin/review?tab=proposals')
}

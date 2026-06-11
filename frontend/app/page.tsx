import Link from 'next/link'
import PublicNav from '@/components/PublicNav'
import { Coffee, BookOpen, BarChart2, Check, ArrowRight, MessageSquare } from 'lucide-react'
import { getBillingPlans } from '@/lib/api/user'

// ── mock: feature cards ───────────────────────
const features = [
  {
    icon: MessageSquare,
    title: 'AI 对话录入',
    desc: '随便说说这次冲煮，AI 自动提取豆名、参数、感受，生成结构化记录，30 秒搞定。',
  },
  {
    icon: BookOpen,
    title: '精品咖啡知识库',
    desc: '产区、品种、处理法、器具，中文内容持续维护。问 AI，答案来自知识库，有据可查。',
  },
  {
    icon: BarChart2,
    title: '个人冲煮记录',
    desc: '历史记录可检索、可对比。同一支豆冲了 5 次，参数和风味一眼看出差在哪。',
  },
]

// /billing/plans 不可用时的兜底文案；正常情况下价格与权益一律读接口
const planFree = ['AI 问答 30 次 / 月', '知识库文章免费浏览', '冲煮记录不限条数', '基础冲煮对比']
const planPro  = ['AI 问答无限次', '知识库文章免费浏览', '冲煮记录不限条数', '多记录横向对比', '优先体验新功能']

// ── page ──────────────────────────────────────
export default async function LandingPage() {
  let freeFeatures = planFree
  let proFeatures = planPro
  let proPrice = 19
  try {
    const plans = await getBillingPlans()
    const basic = plans.find(p => p.id === 'basic')
    const pro = plans.find(p => p.id === 'pro')
    if (basic?.features?.length) freeFeatures = basic.features
    if (pro?.features?.length) proFeatures = pro.features
    if (pro) proPrice = pro.price
  } catch {
    // 后端不可达时保留兜底文案，不影响落地页打开
  }
  return (
    <div className="bg-dc-bg min-h-screen">
      <PublicNav />

      {/* ── Hero ─────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pt-20 pb-24 text-center">
        <div className="inline-flex items-center gap-2 bg-dc-accent-light text-dc-accent text-xs font-medium px-3 py-1.5 rounded-full mb-8 border border-dc-accent/20">
          <Coffee size={12} />
          Your AI assistant for coffee
        </div>

        <h1 className="text-4xl md:text-5xl font-extrabold text-dc-text-1 leading-tight tracking-tight mb-5">
          关于咖啡的旅程由此开始
        </h1>

        <p className="text-dc-text-2 text-lg max-w-xl mx-auto mb-10 leading-relaxed">
          用对话记录咖啡&nbsp;&nbsp;读懂咖啡
        </p>

        <div className="flex items-center justify-center gap-4 flex-wrap">
          <Link href="/auth?tab=register" className="btn-primary text-base px-6 py-3 flex items-center gap-2">
            免费开始使用
            <ArrowRight size={16} />
          </Link>
          <Link href="/knowledge" className="btn-secondary text-base px-6 py-3">
            浏览知识库
          </Link>
        </div>

        {/* Product preview */}
        <div className="mt-16 rounded-2xl border border-dc-border bg-white overflow-hidden shadow-sm max-w-3xl mx-auto">
          {/* Browser chrome */}
          <div className="h-10 bg-dc-subtle border-b border-dc-border flex items-center px-4 gap-2">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-dc-border" />
              <div className="w-3 h-3 rounded-full bg-dc-border" />
              <div className="w-3 h-3 rounded-full bg-dc-border" />
            </div>
            <div className="flex-1 mx-4 bg-dc-bg border border-dc-border rounded text-xs text-dc-text-3 px-3 py-1 text-center">
              deepcoffee.app/app/chat
            </div>
          </div>
          {/* Chat preview */}
          <div className="p-6 space-y-4 text-left">
            <div className="flex justify-end">
              <div className="bg-dc-accent text-white text-sm px-4 py-2.5 rounded-2xl rounded-br-sm max-w-sm">
                今天用 C40 #18 冲了千峰庄园帕卡马拉 CM 日晒，15g，225ml，92°C，感觉有点偏酸
              </div>
            </div>
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-full bg-dc-accent-light flex-shrink-0 overflow-hidden border border-dc-border"><img src="/logo.png" alt="DC" className="w-full h-full object-contain p-0.5" /></div>
              <div className="space-y-3 flex-1">
                <div className="bg-dc-subtle text-dc-text-2 text-sm px-4 py-2.5 rounded-2xl rounded-tl-sm">
                  好的，识别结果如下，请确认：
                </div>
                <div className="dc-card p-4 text-sm space-y-2 max-w-sm">
                  <div className="flex justify-between items-center pb-2 border-b border-dc-border">
                    <span className="font-semibold text-dc-text-1">冲煮草稿</span>
                    <span className="text-xs bg-dc-green-bg text-dc-green px-2 py-0.5 rounded-full font-medium">识别度 82%</span>
                  </div>
                  {[['豆子','千峰庄园 帕卡马拉 CM 日晒'],['器具','V60 ⚠️'],['豆重','15 g'],['水量','225 ml（1:15）'],['水温','92 °C']].map(([k,v]) => (
                    <div key={k} className="flex gap-3">
                      <span className="text-dc-text-3 w-10 flex-shrink-0">{k}</span>
                      <span className="text-dc-text-1 font-medium">{v}</span>
                    </div>
                  ))}
                  <div className="flex gap-2 pt-2 border-t border-dc-border">
                    <button className="btn-primary text-xs py-1.5 flex-1">确认保存</button>
                    <button className="btn-secondary text-xs py-1.5">重新描述</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────── */}
      <section id="features" className="border-t border-dc-border py-20">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-2xl font-bold text-dc-text-1 mb-3">核心功能</h2>
            <p className="text-dc-text-2 text-sm">为精品咖啡爱好者设计，从记录到理解。</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {features.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="dc-card p-6">
                <div className="w-10 h-10 rounded-xl bg-dc-accent-light flex items-center justify-center mb-4">
                  <Icon size={20} className="text-dc-accent" strokeWidth={1.8} />
                </div>
                <h3 className="font-semibold text-dc-text-1 mb-2">{title}</h3>
                <p className="text-sm text-dc-text-2 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ──────────────────────────── */}
      <section id="pricing" className="py-20">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-2xl font-bold text-dc-text-1 mb-3">定价</h2>
            <p className="text-dc-text-2 text-sm">免费开始，按需升级。</p>
          </div>
          <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            {/* Free */}
            <div className="dc-card p-6">
              <div className="text-sm font-medium text-dc-text-3 mb-1">免费版</div>
              <div className="text-3xl font-extrabold text-dc-text-1 mb-1">¥0</div>
              <div className="text-sm text-dc-text-3 mb-6">永久免费</div>
              <ul className="space-y-2.5 mb-6">
                {freeFeatures.map(f => (
                  <li key={f} className="flex items-center gap-2 text-sm text-dc-text-2">
                    <Check size={14} className="text-dc-green flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <Link href="/auth?tab=register" className="btn-secondary text-sm w-full text-center block py-2.5">
                免费注册
              </Link>
            </div>
            {/* Pro */}
            <div className="dc-card p-6 border-dc-accent ring-1 ring-dc-accent/20">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-dc-accent">会员版</span>
                <span className="text-xs bg-dc-accent-light text-dc-accent px-2 py-0.5 rounded-full">推荐</span>
              </div>
              <div className="text-3xl font-extrabold text-dc-text-1 mb-1">¥{proPrice}</div>
              <div className="text-sm text-dc-text-3 mb-6">/ 月，随时取消</div>
              <ul className="space-y-2.5 mb-6">
                {proFeatures.map(f => (
                  <li key={f} className="flex items-center gap-2 text-sm text-dc-text-2">
                    <Check size={14} className="text-dc-accent flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <Link href="/auth?tab=register" className="btn-primary text-sm w-full text-center block py-2.5">
                免费开始，随时升级
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────── */}
      <footer className="border-t border-dc-border py-10">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
          <div>
            <span className="font-extrabold text-dc-accent">Deep</span>
            <span className="font-extrabold text-dc-text-1">Coffee</span>
            <span className="text-dc-text-3 text-xs ml-3">Your Coffee Journey Begins</span>
          </div>
          <div className="flex items-center gap-5 text-sm text-dc-text-3">
            <Link href="/knowledge" className="hover:text-dc-text-2">知识库</Link>
            <span>隐私协议</span>
            <span>© 2026 DeepCoffee</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

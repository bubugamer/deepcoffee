// ── Brew Records ──────────────────────────────────────────────────────────
export interface BrewEvaluationItem {
  score?: number        // integer 1–5
  description?: string
}

export interface BrewEvaluation {
  overall?: BrewEvaluationItem
  aroma?: BrewEvaluationItem
  flavor?: BrewEvaluationItem
  aftertaste?: BrewEvaluationItem
  acidity?: BrewEvaluationItem
  body?: BrewEvaluationItem
  balance?: BrewEvaluationItem
}

export interface BrewStep {
  time_seconds: number
  action: string
  water_ml?: number
  note?: string
}

export interface BrewRecord {
  id: string
  user_id: string
  source_type: string
  bean_card_id?: string | null
  record_type?: string
  is_user_visible?: boolean
  bean_name?: string
  origin?: string
  roaster?: string
  process?: string
  varietal?: string
  brew_method?: string
  device?: string
  grinder?: string
  grind_setting?: string
  filter_media?: string
  water?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  ratio?: string
  ratio_value?: number
  brew_time?: string
  brew_time_seconds?: number
  brew_steps: BrewStep[]
  evaluation?: BrewEvaluation
  bean_rating?: BrewEvaluation | null
  brew_score?: number | null
  notes?: string
  raw_input?: string
  recap?: string
  suggestions: string[]
  trace_id?: string
  created_at: string
  updated_at: string
}

export interface AnonymousBrewRecord {
  id: string
  bean_name?: string | null
  origin?: string | null
  roaster?: string | null
  process?: string | null
  varietal?: string | null
  brew_method?: string | null
  device?: string | null
  grinder?: string | null
  grind_setting?: string | null
  filter_media?: string | null
  water?: string | null
  dose_g?: number | null
  water_ml?: number | null
  water_temp_c?: number | null
  ratio?: string | null
  ratio_value?: number | null
  brew_time?: string | null
  brew_time_seconds?: number | null
  brew_steps: BrewStep[]
  evaluation?: BrewEvaluation | null
  brew_score?: number | null
  created_at: string
}

export interface BrewDraft {
  bean_card_id?: string
  bean_name?: string
  origin?: string
  roaster?: string
  process?: string
  varietal?: string
  brew_method?: string
  device?: string
  grinder?: string
  grind_setting?: string
  filter_media?: string
  water?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  ratio?: string
  ratio_value?: number
  brew_time?: string
  brew_time_seconds?: number
  brew_steps: BrewStep[]
  evaluation?: BrewEvaluation
  notes?: string
}

export interface BrewRecordFormInput {
  bean_card_id: string
  brew_method?: string | null
  device?: string | null
  grinder?: string | null
  grind_setting?: string | null
  filter_media?: string | null
  water?: string | null
  dose_g?: number | null
  water_ml?: number | null
  water_temp_c?: number | null
  brew_time?: string | null
  brew_time_seconds?: number | null
  brew_steps?: BrewStep[]
  bean_rating?: BrewEvaluation | null
  brew_score?: number | null
  notes?: string | null
}

export interface BrewComparisonItem {
  id: string
  date: string
  bean_name?: string
  device?: string
  grinder?: string
  grind_setting?: string
  dose_g?: number
  water_ml?: number
  ratio?: string
  ratio_value?: number
  water_temp_c?: number
  brew_time_seconds?: number
  brew_score?: number | null
  overall_score?: number | null
  active: boolean
}

// ── Bean Cards ─────────────────────────────────────────────────────────────
export interface FlavorAxis {
  label: string
  value?: number | null
}

export interface BeanFlavor {
  notes: string[]
  source: 'roaster' | 'default' | 'user'
  scale_max: number
  axes: FlavorAxis[]
  // AI 解析时为每个风味词配的 emoji（note→emoji）。前端取图优先用它，再退回内置词库。
  note_emojis?: Record<string, string>
}

export type BeanProductType = 'single' | 'blend'

export interface BeanComponent {
  origin_name?: string | null
  coffee_source_name?: string | null
  green_bean_merchant_name?: string | null
  green_bean_product_name?: string | null
  process_name?: string | null
  varietal_names: string[]
  altitude_text?: string | null
  harvest_date_text?: string | null
  share_text?: string | null
  notes?: string | null
  // 后端回填的实体 id（只读）
  origin_entity_id?: string | null
  process_entity_id?: string | null
  coffee_source_entity_id?: string | null
  green_bean_merchant_entity_id?: string | null
  varietal_entity_ids?: string[]
}

export interface BeanDraft {
  name?: string
  roaster_name?: string
  roaster_product_name?: string
  roast_date_text?: string | null
  net_weight_text?: string | null
  bean_components?: BeanComponent[]
  flavor?: BeanFlavor
  private_notes?: string
  public_comment?: string
}

export interface BeanRecommendedParams {
  record_id: string
  record_type?: string
  brew_method?: string
  device?: string
  grinder?: string
  grind_setting?: string
  filter_media?: string
  water?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  ratio?: string
  ratio_value?: number
  brew_time_seconds?: number
}

export interface Bean {
  bean_id: string
  name: string
  roaster?: string | null
  roaster_product?: string | null
  coffee_source?: string | null
  green_bean_merchant?: string | null
  green_bean_product?: string | null
  origin?: string | null
  process?: string | null
  varietal: string[]
  altitude_text?: string | null
  harvest_date_text?: string | null
  roast_date_text?: string | null
  net_weight_text?: string | null
  bean_components: BeanComponent[]
  bean_product_type: BeanProductType
  flavor: BeanFlavor
  rating?: BrewEvaluation | null
  private_notes?: string | null
  public_comment?: string | null
  recommended_record_id?: string | null
  recommended_params?: BeanRecommendedParams | null
  avg_score?: number | null
  record_count: number
  created_at: string
  updated_at: string
}

export interface SquareComment {
  comment: string
  overall_score?: number | null
  created_at: string
}

export interface BeanSquareItem {
  bean_id: string
  name: string
  owner_count: number
  comments: SquareComment[]
  roaster?: string | null
  roaster_canonical?: string | null
  roaster_product?: string | null
  coffee_source?: string | null
  green_bean_merchant?: string | null
  green_bean_product?: string | null
  origin?: string | null
  process?: string | null
  varietal: string[]
  altitude_text?: string | null
  harvest_date_text?: string | null
  roast_date_text?: string | null
  net_weight_text?: string | null
  bean_components: BeanComponent[]
  bean_product_type: BeanProductType
  flavor: BeanFlavor
  rating?: BrewEvaluation | null
  public_comment?: string | null
  recommended_params?: BeanRecommendedParams | null
  avg_score?: number | null
  record_count: number
  created_at: string
  updated_at: string
}

export interface BeanSquareImportItem {
  source_bean_id: string
  bean_id: string
  status: 'created' | 'existing'
}

export interface BeanSquareImportResponse {
  items: BeanSquareImportItem[]
  created_count: number
  existing_count: number
}

export interface BeanParseResponse {
  draft: BeanDraft
  confidence: number
  low_confidence_fields: string[]
  clarification?: string | null
  trace_id: string
}

export interface BeanConfirmResponse {
  bean_id: string
  trace_id: string
}

export interface RecommendParamsResponse {
  recommended_params: BeanRecommendedParams
  recommended_record_id: string
  trace_id: string
}

// ── Recommend Params (多轮) ─────────────────────────────────────────────────
// needs_input: 还需用户补充器具等信息；completed: 已生成建议；fallback: 信息不足给默认兜底
export type RecommendParamsStatus = 'needs_input' | 'completed' | 'fallback'

export interface RecommendEquipment {
  brew_method?: string | null
  dripper?: string | null
  grinder?: string | null
  filter_media?: string | null
  water?: string | null
}

export interface RecommendationParams {
  device?: string | null
  grinder?: string | null
  filter?: string | null
  dose_g?: number | null
  water_ml?: number | null
  water_temp_c?: number | null
  ratio?: string | null
  grind_setting?: string | null
  brew_time_seconds?: number | null
  notes?: string | null
}

export interface RecommendParamsTurnResponse {
  status: RecommendParamsStatus
  intent?: string | null
  assistant_message: string
  session_id: string
  equipment: RecommendEquipment
  missing_fields: string[]
  recommendation?: RecommendationParams | null
  recommended_record_id?: string | null
  source: 'model' | 'local'
  trace_id: string
}

// ── Knowledge Base ─────────────────────────────────────────────────────────
export interface TocItem {
  id: string
  title: string
  level: number
}

export interface RelatedArticle {
  slug: string
  title: string
}

export interface ArticleSection {
  id: string
  heading: string
  body?: string
  items?: string[]
}

export interface Article {
  slug: string
  cat: string
  title: string
  desc: string
  category?: string
  category_key?: string
  summary?: string
  updated_at?: string
  path?: string
  updated?: string
  toc?: TocItem[]
  related?: RelatedArticle[]
}

export interface ArticleDetail extends Article {
  markdown?: string
  sections: ArticleSection[]
}

export interface KBCategory {
  key: string
  label: string
  count: number
  sub: string
  href: string
}

// ── User ───────────────────────────────────────────────────────────────────
export interface UserProfile {
  id: string
  email?: string
  display_name?: string
  plan: string
  plan_source?: string
  plan_expires_at?: string | null
  role?: string          // 'user' | 'admin' — 管理后台入口与守卫依据
  status?: string        // 'active' | 'disabled'
  invite_bound?: boolean // false 时弹「补填邀请码」（后端门禁 invite_required 的前置提示）
  timezone: string
  unit_system: string    // 'metric' | 'imperial'
  created_at: string
}

export interface UserQuota {
  plan: string
  balance: number
  ai_used: number
  ai_total: number | null
  ai_remaining: number | null
  reset_at?: string | null
  features: string[]
}

// GET /v1/billing/plans — 套餐价格/额度一律读接口渲染，不在前端写死
export interface BillingPlan {
  id: string
  name: string
  price: number
  currency: string
  token_limit: number | null
  request_limit: number | null
  period: string
  features: string[]
  prices?: Record<string, {
    amount: number
    currency: string
    interval: 'monthly' | 'yearly'
    display: string
  }>
}

export type BillingInterval = 'monthly' | 'yearly'
export type PaidPlan = 'pro' | 'max'

export interface BillingOrderStatus {
  id: string
  provider: 'alipay' | 'stripe'
  plan: string
  interval: BillingInterval
  amount: number
  currency: string
  status: string
  qr_code?: string | null
  checkout_url?: string | null
  expires_at?: string | null
  paid_at?: string | null
  period_end?: string | null
}

export interface AlipayOrderResponse extends BillingOrderStatus {
  provider: 'alipay'
  plan: PaidPlan
  qr_code: string
  expires_at: string
}

export interface StripeCheckoutResponse {
  id: string
  provider: 'stripe'
  plan: PaidPlan
  interval: BillingInterval
  status: string
  checkout_url: string
}

export interface BillingStatus {
  plan: string
  plan_source: string
  plan_expires_at?: string | null
  active_subscription_status?: string | null
  active_subscription_interval?: string | null
  active_subscription_provider?: string | null
  active_subscription_renews_at?: string | null
}

// ── AI Chat ────────────────────────────────────────────────────────────────
export interface DraftField {
  label: string
  value: string
  lowConf?: boolean
}

// ── Coffea 统一聊天 (POST /v1/coffea/messages) ──────────────────────────────
export interface CoffeaAttachment {
  type: string              // 'image'
  ref?: string | null
  url?: string | null
  data_url?: string | null  // data:image/...;base64,... —— vision 模型只收 base64
  image_base64?: string | null
  mime_type?: string | null
  note?: string | null
}

export type ActionStatus = 'done' | 'degraded' | 'pending' | 'failed'

export interface ActionResult {
  type: string
  status: ActionStatus
  source?: string | null
  output?: Record<string, unknown> | null
  message?: string | null
}

export interface CoffeaSessionState {
  active_bean_id?: string | null
  active_recipe_id?: string | null
  active_brew_id?: string | null
  active_equipment_id?: string | null
}

export interface CoffeaMessageRequest {
  message: string
  session_id?: string | null
  attachments?: CoffeaAttachment[]
  // 向导模式提示：'bean_create' 时后端确定性走文字建豆卡（供「AI 新增豆卡」向导用）
  mode?: 'bean_create'
}

export interface CoffeaMessageResponse {
  session_id: string
  primary_intent: string
  secondary_intents: string[]
  actions: Record<string, unknown>[]
  results: ActionResult[]
  state: CoffeaSessionState
  reply?: string | null
  should_answer_directly: boolean
  source: 'model' | 'local' | 'mixed'
  trace_id: string
}

// web_verify 动作 output.sources[] 的引用条目
export interface WebVerifySource {
  title?: string
  url?: string
  slug?: string
  path?: string
  excerpt?: string
  published_at?: string
  time?: string
}

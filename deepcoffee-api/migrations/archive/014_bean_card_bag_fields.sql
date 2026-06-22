-- 014: 豆卡补齐真实豆袋信息字段，并支持拼配 / 多豆源组成。
--
-- 这些字段都属于用户私有豆卡；公共实体库仍通过候选审核链路沉淀。

ALTER TABLE user_bean_cards ADD COLUMN IF NOT EXISTS altitude_text text;
ALTER TABLE user_bean_cards ADD COLUMN IF NOT EXISTS harvest_date_text text;
ALTER TABLE user_bean_cards ADD COLUMN IF NOT EXISTS roast_date_text text;
ALTER TABLE user_bean_cards ADD COLUMN IF NOT EXISTS net_weight_text text;
ALTER TABLE user_bean_cards ADD COLUMN IF NOT EXISTS bean_components jsonb NOT NULL DEFAULT '[]'::jsonb;

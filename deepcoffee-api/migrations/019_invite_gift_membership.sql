-- Invite codes carry a membership gift: redeeming a code opens the given plan
-- (pro/max) for the given duration in months. Existing unused codes become a
-- 1-month Pro gift (public-beta default).

ALTER TABLE invite_codes
    ADD COLUMN IF NOT EXISTS gift_plan text,
    ADD COLUMN IF NOT EXISTS gift_duration_months integer;

-- 存量未使用（active 且未被领取）的邀请码统一改为「赠 Pro 1 个月」。
UPDATE invite_codes
   SET gift_plan = 'pro',
       gift_duration_months = 1
 WHERE status = 'active'
   AND used_by IS NULL
   AND gift_plan IS NULL;

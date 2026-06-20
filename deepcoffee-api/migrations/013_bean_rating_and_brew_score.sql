-- 013: 拆分豆子评分与单杯冲煮评分。
--
-- 豆子评分属于豆卡 user_bean_cards.rating；单杯冲煮评分属于 brew_records.brew_score。
-- 旧 brew_records.evaluation 只作为迁移来源和兼容字段保留。

ALTER TABLE user_bean_cards ADD COLUMN IF NOT EXISTS rating jsonb;
ALTER TABLE brew_records ADD COLUMN IF NOT EXISTS brew_score integer;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'brew_records_brew_score_ck'
    ) THEN
        ALTER TABLE brew_records
            ADD CONSTRAINT brew_records_brew_score_ck
            CHECK (brew_score IS NULL OR (brew_score >= 1 AND brew_score <= 5));
    END IF;
END $$;

DO $$
DECLARE
    conflict_details text;
BEGIN
    WITH distinct_eval AS (
        SELECT
            bean_card_id,
            count(DISTINCT evaluation) AS variants,
            jsonb_agg(DISTINCT evaluation) AS evaluations
        FROM brew_records
        WHERE bean_card_id IS NOT NULL
          AND evaluation IS NOT NULL
          AND evaluation <> '{}'::jsonb
        GROUP BY bean_card_id
    )
    SELECT COALESCE(
        jsonb_agg(jsonb_build_object(
            'bean_card_id', distinct_eval.bean_card_id,
            'bean_name', user_bean_cards.name,
            'variants', distinct_eval.variants,
            'evaluations', distinct_eval.evaluations
        ))::text,
        '[]'
    )
    INTO conflict_details
    FROM distinct_eval
    LEFT JOIN user_bean_cards ON user_bean_cards.id = distinct_eval.bean_card_id
    WHERE distinct_eval.variants > 1;

    IF conflict_details <> '[]' THEN
        RAISE EXCEPTION
            'bean rating migration stopped: conflicting legacy brew_records.evaluation: %',
            conflict_details;
    END IF;
END $$;

WITH source_rating AS (
    SELECT DISTINCT ON (bean_card_id)
           bean_card_id,
           evaluation
    FROM brew_records
    WHERE bean_card_id IS NOT NULL
      AND evaluation IS NOT NULL
      AND evaluation <> '{}'::jsonb
    ORDER BY bean_card_id, updated_at DESC, created_at DESC, id DESC
)
UPDATE user_bean_cards bean
SET rating = source_rating.evaluation
FROM source_rating
WHERE bean.id = source_rating.bean_card_id
  AND bean.rating IS NULL;

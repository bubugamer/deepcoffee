-- Bug 2 一次性清理（在 Supabase SQL Editor 执行）
-- 候选事实并入 8 / 驳回 3 + 删 2 条脏提案及其 2 条 promoted 候选。
-- 只动 candidate_facts / public_entity_proposals / entity_aliases，不动任何实体本身。
-- 非迁移、不进 create_all；属一次性数据整理，留档在此。

BEGIN;

-- ① 并入：把候选名登记为目标实体的别名（幂等，撞唯一约束跳过）
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_b6ec03fb56ae', '巴拿马', '巴拿马', 'zh', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_778b7774ba3b', '埃塞俄比亚', '埃塞俄比亚', 'zh', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_40bbc432bdac', 'Peru', 'peru', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_778b7774ba3b', 'Ethiopia, Sidama', 'ethiopia, sidama', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_778b7774ba3b', 'Ethiopia, Sidama', 'ethiopiasidama', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_27fe1a3a9a4b', '水洗', '水洗', 'zh', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_27fe1a3a9a4b', 'Washed', 'washed', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_f2d9ec1ea04d', 'Coffeebuff', 'coffeebuff', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_f2d9ec1ea04d', 'coffee buff', 'coffee buff', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;
INSERT INTO entity_aliases (entity_id, alias, normalized_alias, locale, source) VALUES ('ent_f2d9ec1ea04d', 'coffee buff', 'coffeebuff', 'en', 'admin') ON CONFLICT (entity_id, normalized_alias) DO NOTHING;

-- ② 并入：候选标记 merged
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_b6ec03fb56ae', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_7e2eace1615b';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_778b7774ba3b', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_09e506c98fb3';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_40bbc432bdac', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_08346089b67f';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_778b7774ba3b', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_eda8c015fc2c';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_27fe1a3a9a4b', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_8d1f91ea96be';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_27fe1a3a9a4b', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_c9e7bab9a668';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_f2d9ec1ea04d', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_dd90897bc56b';
UPDATE candidate_facts SET status='merged', proposed_entity_id='ent_f2d9ec1ea04d', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：并入已有实体', reviewed_at=now() WHERE id='cand_c63646372af9';

-- ③ 驳回 3 条多值脏串
UPDATE candidate_facts SET status='rejected', reviewer_id='376ca00f-968e-4cb2-9084-19b5553eed82', reviewer_note='清理：多值脏串驳回', reviewed_at=now()
WHERE id IN ('cand_fbac2a2ba913','cand_e4a29d45ab3a','cand_db7711f1e38c');

-- ④ 删除 2 条 promoted 候选（脏链上游：乔治队长 / SEY）
DELETE FROM candidate_facts WHERE id IN ('cand_9cd429cbc1b5','cand_84520e29812b');

-- ⑤ 删除 2 条脏提案（级联删审计事件；对应实体保留不动）
DELETE FROM public_entity_proposals WHERE id IN ('prop_0e4c4b742811','prop_065d98c8c441');

COMMIT;

-- 跑完单独执行下面两句核对：
-- SELECT status, count(*) FROM candidate_facts GROUP BY status;   -- 期望 merged=8, rejected=3, pending_review=14
-- SELECT count(*) FROM public_entity_proposals;                    -- 期望 0

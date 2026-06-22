# 数据库 schema 基线

`baseline_2026_06_22.sql` 是 2026-06-22 从生产库 `public` schema 抽取的结构基线，只包含表结构、约束、索引、序列和 RLS 状态，不包含业务数据。

它只用于初始化全新的 DeepCoffee 数据库，不要把它当成迁移脚本在已有生产库上执行。

新库初始化流程：

1. 执行 `schema/baseline_2026_06_22.sql`。
2. 执行这个基线之后新增在 `migrations/` 根目录下的迁移文件。
3. 不执行 `migrations/archive/`；那里是已经执行过的历史 SQL，只用于追溯和回滚研究。

之后的 schema 变更继续新增到 `deepcoffee-api/migrations/`，从已归档的 `014` 之后接续编号。

# 🗄️ storage 包：状态与长程记忆存储底座

`storage` 包统一管理小说流水线的底层存储与因果知识检索。全包基于原生 SQLite 与 WAL 韧性配置，提供实体图拓扑、FTS5 全文倒排索引、原子检查点与状态快照管理。

---

## 📂 模块清单与架构

```
storage/
├── __init__.py                # 统一导出存储管理 API
├── knowledge_graph.py         # 🔗 因果实体拓扑图谱（NovelKnowledgeGraph）
├── long_term_memory.py        # 🔍 FTS5 倒排索引与时空衰减检索库
├── checkpoints.py             # 💾 章节原子快照与时间旅行回滚机制 (Time-Travel)
├── state_manager.py           # 📊 状态 JSON 深度合并与投影渲染引擎
└── battle_state.py            # ⚔️ 局部战力动态追踪
```

---

## 🛠️ 核心 API 与机制

### 1. 因果实体知识图谱 (`knowledge_graph.py`)
* **核心类**：`NovelKnowledgeGraph(db_path, config_path=None)`
* **机制特性**：
  * **0 孤儿边保证**：添加关系边前自动校验起止节点存在性，图拓扑 100% 闭环；
  * **结构化节点属性**：随从节点持久化承载 `signature_body_part`、`signature_action`、`props` 与 `voice_trait`；
  * **因果权重自适应**：关系边权重区间严格收敛于 `[-1.0, 1.0]`；
  * **未决因果钩子雷达**：`get_unresolved_causal_hooks` 与 `resolve_causal_hook` 追踪跨越百章的未决仇恨与伏笔；
  * **灵魂物象五阶段演进状态机**：`update_soul_totem_state` 与 `get_soul_totem_state` 追踪物象（从开端登场到终局重铸）物理全生命周期；
  * **角色前史创伤冷却**：`can_trigger_character_trauma` 严格防止性格软肋被廉价复读（硬锁定 $\ge 5$ 章冷却期）；
  * **Graph RAG**：提供 `format_graph_rag_context`，为 Planner 注入当章最相关的因果边与未闭环悬念。

### 2. 数据库高韧性并发配置 (`pipeline/utils.py` 联动)
* **核心函数**：`configure_sqlite_resilience(conn)`
* **配置特性**：
  * 强制开启 `PRAGMA journal_mode = WAL;`；
  * 强制配置 `PRAGMA busy_timeout = 5000;`（5 秒排队重试，彻底杜绝 `database is locked`）；
  * 启用 `PRAGMA synchronous = NORMAL;` 与 `PRAGMA foreign_keys = ON;`。

### 3. 长程记忆全文检索 (`long_term_memory.py`)
* **核心函数**：
  * `index_entity(name, category, description, chapter_num)`
  * `index_plot_thread(thread_name, planted_chapter, summary, status)`
  * `query_relevant_lore(query_text, current_chapter, top_k, decay_lambda)`
* **机制特性**：
  * 基于 SQLite FTS5 `unicode61` 分词器；
  * **时空衰减算法**：采用 $Score = BM25 \times e^{-\lambda \times \Delta Chapter}$，让近期发生的设定拥有更高权重，远期设定平滑衰减。

### 4. 原子检查点与时间旅行 (`checkpoints.py`)
* **核心函数**：
  * `save_checkpoint(chapter_num, state_data, chapter_content, review_report, metadata) -> str`
  * `rollback_to(target_chapter, create_backup) -> dict`
  * `list_checkpoints() -> list`
* **机制特性**：每一章审核通过后自动创建快照，支持秒级无损回滚至任意历史章节并自愈关联数据库。

### 5. 状态机管理引擎 (`state_manager.py`)
* **核心函数**：`load_state(novel_dir)`、`save_state(novel_dir, state_data)`
* **机制特性**：状态数据通过 POSIX 原子写入，保证高并发与多轮重试下的 ACID 事务一致性。

### 6. 通用战役与动作微状态机 (`battle_state.py`)
* **核心函数**：
  * `start_battle_universal(battle_name, combat_mode, hero_side, opponent_side, location, total_layers, ...)`
  * `update_battle_turn(consumed_item, boss_damage_layer, broken_item, terrain_damage, new_distance, new_phase, ...)`
  * `end_battle(custom_novel_dir, final_result, spoils)`
  * `get_battle_subgraph_context(chapter_num, custom_novel_dir) -> str`
* **机制特性**：
  * **三大范式自适应**：支持 `DUEL_BOSS`（单挑强敌）、`ARMY_SIEGE`（万人兵团攻防）与 `PURSUIT_ESCAPE`（大纵深追杀突围）；
  * **刚性锁定防复读**：自动将本场已消耗底牌与已损毁装备置入禁令清单，严禁写手跨章违规复用；
  * **动态空间与射程追踪**：动态维护 `engagement_distance`（如 800米 ➔ 300米死线）与战术阶段；
  * **战后软着陆自动归档**：在战后缓冲章自动结算战利品至全局资源表并重置活跃状态。

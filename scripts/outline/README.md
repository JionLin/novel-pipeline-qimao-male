# 🏛️ outline 包：L1~L3 大纲工程母机与脚手架向导

`outline` 包负责小说全生命周期规划，实现从 **L1 宏观全书总纲 ➔ L2 中观卷施工图 ➔ L3 微观 JIT 细纲** 的三层递进生成与多小说工作区沙盒管理。

---

## 📂 模块清单与架构

```
outline/
├── __init__.py                # 统一导出大纲生成与调度函数
├── master_generator.py        # 🏛️ L1 全书架构总纲生成器（沙盘推导与大模型推导）
├── block_planner.py           # 🗺️ L2 卷级块施工图规划器（锁定物资血脉与失效代偿）
├── chapter_generator.py       # ✍️ L3 微观单章细纲生成器（三维坐标 + 动态三幕比例）
├── cli_wizard.py              # 🧙 多小说工作区隔离脚手架与秒切向导
├── kg_weaver.py               # 🕸️ 大纲实体知识编织器
└── narrative_linter.py        # 🔍 叙事一致性与断层质检器
```

---

## 🛠️ 三层大纲生成架构与核心 API

### 1. L1 全书架构总纲 (`master_generator.py`)
* **核心函数**：`generate_master_outline(genre_prompt, target_words, client, model_name, cfg, output_path, log_func) -> str`
* **机制**：
  * **Pass 1 + Pass 2 两段式串行生成**：Pass 1 专注底层设定基座（商业定位/人物羁绊/工业树/势力拓扑），Pass 2 专注时间轴沙盘（三幕/1~8卷分卷/五感物价/7维战役工程参数卡）；
  * **第九板块高浓度瘦身**：将原 5000 字散文彻底压缩为 7 维高纯度战役工程参数卡（战场几何/环境变量/核心杀伤帧/主角动作指令/代差反差/物象回扣/战后寂静），每场 200~300 字，总纲体积稳定在 30~35 KB，彻底根除 8192 Token 输出截断风险；
  * 读取 `config.yaml` 的 `macro_three_act_ratio` 动态推导全书 1125 章三幕九拍沙盘；
  * 生成完成后自动调用脚手架初始化当前项目。

### 2. L2 卷级块施工图 (`block_planner.py`)
* **核心函数**：`generate_volume_blocks(volume_num, start_ch, end_ch, master_text, target_words, client, model_name, cfg, output_path, log_func) -> str`
* **机制**：
  * **半卷双批次串行生成**：针对 100 章单卷大工程，自动拆分为 **上半卷（块 1~3，前 50 章）** 与 **下半卷（块 4~6，后 50 章）** 双批次生成；
  * 第二批次自动继承第一批次终态物资余量与苏冷霜情感阶段，彻底杜绝单次 1.5 万字输出的后半卷疲劳；
  * **三线并行配额平衡**：主线（50%~65%）、支线（20%~30%）、同袍羁绊（15%~25%）；
  * **副手生活棱角保障**：在低强度呼吸空间章中优先分配核心副手非功能性生活细节展示；
  * **跨块情感呼吸波浪管理**：连续高压块后主动规划降压软着陆跑道。

### 3. L3 微观单章细纲 (`chapter_generator.py` 与 `jit_buffer.py`)
* **核心函数**：`generate_chapter_outlines(start_ch, end_ch, volume_num, client, model_name, cfg, master_outline_path, genre_directives, total_chapters_book, log_func) -> str`
* **机制**：
  * **JIT 3~5 章滚动滑动调度**：在流水线撰写正文时，永远保持前方 3 章细纲动态滑动储备（如第 1 章写完自动补充第 4 章细纲），杜绝单次 20 章大请求带来的后半程假寐同质化；
  * 消费 `prompts/03_chapter_outline.md`；
  * 动态从 `config.yaml` 注入 A~F 六类文体的微观三幕自适应比例与滑动窗口配额建议；
  * 字段 1 注入**【本章叙事温度】**，字段 6 落实**【四类章末钩子轮换池】**，末尾执行**【首章贯穿物象微在场条款】**；
  * 字段 13 JSON 元数据引入 `global_lore_used` 跨卷索引。

---

## 💡 章节细纲（L3）两种生成模式与 JIT 滑动窗口实战指南

| 场景模式 | 执行命令示例 | 运作机理与适用场景 |
| :--- | :--- | :--- |
| **模式 1：开书前手动/批量指定生成** | `python3 auto_outline.py chapters 1 3 1`<br>*(或生成前20章: `chapters 1 20 1`)* | • **由用户自由指定生成范围**：传入 `1 3` 即生成 1~3 章，传入 `1 20` 即生成 1~20 章；<br>• 生成后通过 `merge_chapter_outlines_deduplicated` 自动去重合并写入《第1卷_章节细纲.md》，绝不覆盖丢失；<br>• **适用场景**：开书前想先审读前 3~5 章高精度细纲样本。 |
| **模式 2：正文流水线全自动 JIT 滑动窗口** | `python3 run_pipeline.py 1 100`<br>*(全自动流水线运行)* | • **系统后台全自动 3 章滑动滚动**：后台 `jit_buffer.py` 自动探测前瞻视距；<br>• 当写第 1 章时，自动在后台派发生成第 2~4 章（正好 3 章黄金批次！）；<br>• 每次仅生成 3 章（约 3000 字），模型注意力处于巅峰状态，四类休整池与战役三维坐标 100% 满血执行；<br>• **适用场景**：日常批量全自动生成，0 人工干预，边写边动态向前推导！ |

---

### 4. 叙事一致性与断层质检引擎 (`narrative_linter.py`)
* **核心函数**：`lint_chapter_outlines(full_text)`、`lint_block_blueprint(block_text)`、`deep_narrative_lint(outlines_dir)`
* **质检维度**：
  * A~F 章节类型与 JSON `type` 强一致性交叉校验；
  * C 类造物章节连续熔断校验（严禁连续 3 章造物）；
  * 黄金三章禁 E 类过渡叙事，前 20 章 F 类复合高潮配额校验（$\le 1$ 章）；
  * 首两章开头钩子二元强制（物理动作+压迫者即时威胁）校验；
  * 施工图副手生活呼吸章跨块连续重合 0ms 探针拦截；
  * 施工图 M5 情绪阻尼残余词汇检测与 M4 爽点蓄力期超标（$\le 3$ 章）校验；
  * 施工图长技术攻关连续 $\ge 5$ 章无爽点熔断检测。

### 5. 多小说工作区隔离脚手架与全量萃取器 (`cli_wizard.py`)
* **核心函数**：`extract_full_project_manifest(master_text)`、`bootstrap_project_workspace(proj_dir, ...)`
* **机制**：
  * **0 延迟自动萃取**：总纲生成后自动解析副手身体习惯（`signature_body_part`/`signature_action`）、宿敌信物反应、物象 5 阶段里程碑与呼吸章轮换名单；
  * **结构化落盘**：自动回填至本地 `config.yaml` 与 `knowledge_graph.db` 节点属性，0 手动输入。

### 5. 项目脚手架与工作区隔离 (`cli_wizard.py`)
* **核心函数**：
  * `create_new_project_dir(base_dir, target_words, custom_title) -> str`
  * `bootstrap_project_workspace(proj_dir, config_path, master_text, log_func) -> bool`
  * `switch_project(target_proj_dir, config_path, log_func) -> bool`
* **机制**：为每部新书建立时间戳独立目录，原子化生成本地私有 `config.yaml`、`knowledge_graph.db` 和 `memory.db`，实现 100% 物理强隔离。

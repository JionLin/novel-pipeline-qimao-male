# 🤖 agents 包：专职智能体执行体层

`agents` 包封装了流水线中 5 大专职 Agent 执行体。每个 Agent 均遵循单一职责原则，独立消费 `prompts/` 模板并执行大模型推导与结构化产出。

---

## 📂 模块清单与职责架构

```
agents/
├── __init__.py                # 统一导出所有 Agent 调度函数
├── agent_1_planner.py         # 📝 L1 任务书编译引擎（Prompt Caching 三层金字塔组装）
├── agent_2_writer.py          # ✍️ L2 心流主笔撰写引擎（自适应温度采样与物理留白）
├── agent_3_reviewer.py        # 🧐 L3 品控审核引擎（0ms 代码快速熔断 + 五大红线质检）
├── agent_4_publisher.py       # 📦 L4 正文发布引擎（纯净版落盘、全书合集追加与 TOC 目录树生成）
└── agent_5_state_tracker.py   # 🧠 L5 状态因果追踪引擎（全题材双模自适应状态机）
```

---

## 🛠️ 核心 API 与调用契约

### 1. `Planner` (`agent_1_planner.py`)
* **核心函数**：`run_planner(chapter_num, prev_tail, chapter_outline, cfg, outline_file, state_snapshot, novel_settings, log_func) -> str`
* **职责**：
  * 构建严格遵守字节级对齐的 Prompt Caching 静态前缀（`<static_world_and_guidelines>`）；
  * 注入唯一法定主角锁（`<characters_lock>`），彻底杜绝角色名跨书漂移；
  * **随从生活质感物理载体注入**：动态从 `config.yaml` 提取随从 `signature_body_part`、`signature_action`、`props`，组装为专属候选池注入任务书；
  * **呼吸缓冲章副手自动排期**：根据 `output_constraints.breathing_chapter_rotation` 自动指派当前章生活主视角副手；
  * 执行 5-Chapter Horizon 前瞻雷达扫描，自动埋设前置伏笔；
  * **第 1 章超前物象在场与前 200 字极速反击自动注入**：从 SQLite 知识图谱提取贯穿灵魂物象，在首章强制下发微痕迹任务与 M7 极速反击指令；
  * **勘测短句交互打断与章末主动宣战指令注入**：约束推演段落不得说明书化，章末定格后必须以主动宣战姿态收尾。

### 2. `Writer` (`agent_2_writer.py`)
* **核心函数**：`run_writer(task_prompt, client, model_name, temperature, chapter_outline, novel_dir, log_func) -> str`
* **职责**：
  * 消费通用抽象版 `prompts/04_writer.md` 与题材文风卡；
  * 执行【零-甲 黄金开篇第一页硬性熔断】（前 200 字极速反击 + 两屏 500 字法则，优先级最高）；
  * 执行【叙事温度三档管理之微温触发（前置档位）】：在同袍交接物资或确认生死信任时，允许释放 $\le 200$ 字生活微温；
  * 严格遵循主角有限视角，执行开篇 30 字身体感知切入与章末主动宣战留白；
  * 落实**味觉五感直接白描三原则**与专属身体载体微表情动作化；
  * 严格遵守【全书防伪反例黑名单】（杜绝作者说教与口号煽情）。

### 3. `Reviewer` (`agent_3_reviewer.py`)
* **核心函数**：`run_reviewer(chapter_output, chapter_outline, prev_tail, chapter_num, client, model_name, cfg, log_func) -> dict`
* **返回格式**：`{"verdict": "PASS" | "FAIL", "feedback": "...", "word_count": N, "patch_action": "NONE" | "AUTO_SANITIZED" | "APPEND_WRAPPER" | "FULL_REWRITE"}`
* **阶梯式三级自愈机制 (Graduated 3-Tier Self-Healing)**：
  * **Level 1（0ms 正则微创自愈）**：轻微 AI 套话、角色禁用别名、章末口号由代码毫秒级置换，0 额外耗时；
  * **Level 2（增量补写拼接 APPEND_WRAPPER）**：缺失章末留白或局部物理帧时，仅调用 LLM 补写 100~300 字局部片段，拒绝整章推倒；
  * **Level 3（全量重写 FULL_REWRITE）**：核心剧情偏离或严重违规时才触发全量重新生成；
  * **0ms 快速拦截探针**：剥离 Markdown 标题纯化测距，第 1 章前 100 字压迫者显形、前 200 字反击时序（动态读取 `opening_pacing`）、前 500 字非对抗描写三分类拦截；
  * **4C 体验与红线质检**：身体感知切入、相变微观帧、章末主动宣战留白、直接味觉白描与勘测短句交互打断检查。

### 4. `Publisher` (`agent_4_publisher.py`)
* **核心函数**：`run_publisher(chapter_num, chapter_output, chapter_outline, cfg, review_report, log_func) -> str`
* **职责**：
  * POSIX 原子落盘至 `正文/C_正文_第X章.md`；
  * 净化提取纯正文至 `正文/发布版/C_正文_第X章.txt`；
  * 自动增量追加至 `合集.md` 与纯文本 `发布版/合集.txt`，并触发全书目录树 `目录.md` 重新生成。

### 5. `StateTracker` (`agent_5_state_tracker.py`)
* **核心函数**：`run_state_tracker(chapter_num, chapter_content, prev_state_data, client, model_name, cfg, log_func) -> dict`
* **职责**：
  * 消费通用抽象版 `prompts/06_state_tracker.md`；
  * 增量 JSON Patch 解析与递归深度合并，更新 `状态文件.json`；
  * 自动标记已达成的核心物象 5 阶段里程碑状态（`resolved`）；
  * 自动识别本章出场副手，并根据轮换白名单自动计算排期下一个应出场副手（`next_due_sidekick`）；
  * 沉淀实体状态、因果边演进至 `knowledge_graph.db` 与长程倒排记忆 `memory.db`。

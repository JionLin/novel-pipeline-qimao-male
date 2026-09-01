---
name: novel-pipeline-qimao-male
description: 七猫男频通用多Agent小说全生命周期写作流水线 v22.0——全题材双模自适应、五大专职包模块化架构、基于 config.yaml 单一数据源驱动、核心三要素强校验与动态自愈、13 大自动化回归门禁工业级流水线。
version: 22.0.0
metadata:
  hermes:
    tags: [novel, multi-agent, pipeline, qimao, male, outline, knowledge-graph, graphrag, time-travel, checkpoints, modular-packages, ssot]
    category: workflow
    related_skills: [novel-qimao-long-male-generation]
triggers:
  - "七猫流水线写小说"
  - "qimao pipeline"
  - "继续写七猫第"
  - "生成小说大纲"
  - "根据题材写小说"
  - "从大纲开始写小说"
  - "一键写小说"
  - "自动生成大纲"
  - "开一本新书"
  - "帮我构思一本小说"
  - "构思大纲"
  - "生成细纲"
  - "活纲同步"
  - "重塑细纲"
  - "大纲质检"
  - "细纲质检"
  - "大纲一致性校验"
---

# 七猫男频通用多Agent小说全生命周期写作流水线 v22.0 (模块化架构与单一数据源版本)

> **全生命周期工业级闭环架构：**
> 1. **题材构思与向导** ➔ `python3 scripts/auto_outline.py master` ➔ 生成全书架构总纲（正向物理事件驱动+终局物理图腾） + 动态推导沙盘 + **原子初始化项目沙盒 (config.yaml, knowledge_graph.db, memory.db)**
> 2. **卷施工图与细纲** ➔ `python3 scripts/auto_outline.py chapters` ➔ 卷级 6 块施工图规划（攻关零豁免+长攻关熔断+双重爽点叠加）+ 微观动态三幕自适应比例细纲（前200字反击+短句交互打断）
> 3. **正文生产流水线** ➔ `python3 scripts/run_pipeline.py` ➔ Planner(静态缓存+法定主角锁) ➔ Writer(前200字极速反击+非对抗三分类拦截) ➔ Reviewer(0ms代码熔断+五道红线质检) ➔ StateTracker(双模状态机) ➔ Publisher(双格式落盘+TOC目录树)
> 4. **质量守卫与自愈** ➔ 核心三要素强校验 (Triplet Guard) + 19 项全量自动化测试门禁覆盖。

---

## 一、 Skill 触发与执行协议 (Skill Trigger Protocol)

当您在与 AI 交流时，使用任意自然语言即可精准触发本 Skill：

### 🎯 模式 1：题材构思 ➔ 自动生成总纲并初始化独立工作区
* **用户触发**：“帮我构思一本【题材/创意】的小说大纲” 或 “根据题材【xxx】生成小说总纲”
* **执行命令**：
```bash
python3 scripts/auto_outline.py master "<用户提供的题材与核心创意描述>" [预估总字数(默认2700000)]
```

---

### 📑 模式 2：大纲驱动 ➔ 批量生成分卷施工图与微观细纲
* **用户触发**：“生成第 1 到 20 章细纲” 或 “根据大纲生成分卷细纲”
* **执行命令**：
```bash
python3 scripts/auto_outline.py chapters <起始章> <结束章> <卷号(默认1)> [总章数/字数]
```

---

### ✍️ 模式 3：正文流水线批量生产与自愈续写
* **用户触发**：“继续写第 1 到 10 章” 或 “生成后续章节正文”
* **执行命令**：
```bash
python3 scripts/run_pipeline.py <起始章> <结束章或批次数量>
```

---

### 📊 模式 4：离线运维、状态观测与健康巡检
* **用户触发**：“查看当前小说写作进度”、“检查数据库状态”、“全流程巡检”
* **执行命令**：
```bash
# 1. 实时进度与商业指标看板
python3 scripts/tools/check_status.py

# 2. 数据库（图谱节点与长程记忆）底层检视器
python3 scripts/tools/inspect_db.py

# 3. 章节时间旅行回滚
python3 scripts/tools/rollback.py <目标章节号>

# 4. 全流程健康度快速巡检
python3 scripts/tools/verify_pipeline_integrity.py

# 5. 全量 19 项自动化回归门禁测试
python3 scripts/test.py
```

---

## 二、 模块化分包架构与组件映射索引

系统代码已统一归纳为 5 大高内聚子包，根目录仅保留快捷入口：

* 🤖 [**`agents/`**](./scripts/agents/README.md)：Planner、Writer、Reviewer、Publisher、StateTracker 专职 Agent
* 🗄️ [**`storage/`**](./scripts/storage/README.md)：SQLite 因果图谱、FTS5 时空衰减记忆库、原子检查点与状态机
* 🏛️ [**`outline/`**](./scripts/outline/README.md)：L1 全书总纲、L2 卷施工图、L3 细纲生成与项目脚手架
* 🛡️ [**`pipeline/`**](./scripts/pipeline/README.md)：核心三要素守卫、单一配置源加载器、POSIX 原子落盘与 JIT 缓冲
* 🛠️ [**`tools/`**](./scripts/tools/README.md)：离线看板、数据库检视与时间旅行回滚工具箱
* 📜 [**`prompts/`**](./scripts/prompts/README.md)：6 大全题材纯净系统提示词中心
* 📚 [**`genres/`**](./scripts/genres/README.md)：16 种主流商业爆款文体配方库

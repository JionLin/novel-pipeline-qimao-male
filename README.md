<!-- WORKSPACE_META_CARD_START -->
> 📌 **项目速览卡片**  
> - **业务领域**：AI 创作与内容流水线  
> - **核心定位**：七猫/番茄商业网文多智能体工业化批量写作与质量质检流水线。  
> - **核心特性**：多 Agent 协作写书、大纲细化、批量正文生成、合规审核与去 AI 味。  
> - **核心技术栈**：`Python / Multi-Agent / 大模型生成`  
> 
> ---
<!-- WORKSPACE_META_CARD_END -->

# 📖 Novel Pipeline Multi-Agent (七猫/番茄/起点 商业网文多Agent工业化流水线)

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha%20%2F%20Experimental-orange.svg)](#-项目现状与阶段说明)
[![Hermes Skill Compatible](https://img.shields.io/badge/Hermes_Skill-Compatible-purple.svg)](./SKILL.md)

基于多 Agent 协同的百万字长篇网文全生命周期创作与生产流水线（专为七猫、番茄、起点男频/女频高烈度爽文结构定制）。通过分层大纲工程（L1~L3）、专职 Agent 任务流水线、物理级因果知识图谱与 FTS5 长程记忆库，实现长篇网文的半自动/全自动推演生产。

---

## ⚠️ 项目现状与阶段说明 (Disclaimer & Current Status)

> **⚠️ 注意：本项目目前处于早期孵化阶段 (Alpha / Experimental / WIP)。**

- **智能度探索中**：长篇网文对因果逻辑、角色动机深度、情绪节奏波动的要求极高。当前多 Agent 流水线在大模型生成（LLM Calling）层面依然存在偶发性的机械感、AI 腔调（AI-Slop）以及超长篇跨卷大纲推导不够智能的问题。
- **开源共建目的**：开放代码旨在探索**工业化网文生成工程架构**（单一数据源、图谱记忆、分卷施工图、0ms 代码级拦截门禁等）。非常欢迎对 AI 辅助写作、长文本多智能体架构感兴趣的开发者与创作者共同参与反馈、提出 Issue 与 PR！

---

## 🌟 核心架构全景 (Architecture Overview)

```
                    【流水线高内聚分层架构与数据流向】

   ┌────────────────────────────────────────────────────────────────────────┐
   │                    🚀 核心执行入口 (Root Entrypoints)                   │
   │   ├─ run_pipeline.py   (正文多Agent流水线: Planner→Writer→Reviewer)     │
   │   ├─ auto_outline.py   (L1~L3 大纲工程母机: Master→Block→Chapters)     │
   │   └─ test.py           (23 项全量自动化单元与回归测试套件)              │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
│  📦 agents/      │          │  📦 storage/     │          │  📦 outline/     │
│  [专职智能体]    │          │  [存储与长程记忆]│          │  [大纲工程规划]  │
├──────────────────┤          ├──────────────────┤          ├──────────────────┤
│ ├─ planner.py    │          │ ├─ graph.py (KG) │          │ ├─ master.py     │
│ ├─ writer.py     │          │ ├─ memory.py(FTS)│          │ ├─ block.py      │
│ ├─ reviewer.py   │          │ ├─ checkpoint.py │          │ ├─ chapter.py    │
│ ├─ publisher.py  │          │ ├─ state_mgr.py  │          │ ├─ wizard.py     │
│ └─ tracker.py    │          │ └─ battle.py     │          │ └─ linter.py     │
└────────┬─────────┘          └────────┬─────────┘          └────────┬─────────┘
         │                             │                             │
         └─────────────────────────────┼─────────────────────────────┘
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                  📦 pipeline/ (调度守卫与基础设施层)                    │
   │   ├─ guards.py       (核心三要素强校验、动态自愈与代码防硬编码守卫)     │
   │   ├─ utils.py        (单配置加载器、POSIX 原子落盘、0ms 预检与微创修剪) │
   │   ├─ prompt_loader.py(两级 Prompt 模板加载与内存缓存引擎)              │
   │   ├─ context_builder (细纲智能切片与高信噪比 AST 设定集提取)           │
   │   └─ jit_buffer.py   (JIT 细纲储备缓冲滑动调度器)                      │
   └────────────────────────────────────────────────────────────────────────┘
```

### 关键组件

1. **三级大纲工程 (L1 ➔ L2 ➔ L3)**：
   - **L1 总纲 (`master_generator.py`)**：双阶段串行生成全书世界观基座、主线动力学与分卷大纲。
   - **L2 卷施工图 (`block_planner.py`)**：分块拆解（6块式），锁定主副线配额、升级节奏与情感落地。
   - **L3 章节细纲 (`chapter_generator.py`)**：动态三幕比例微观细纲，支持 JIT 滑动窗口向前预推。
2. **五大专职 Agent 流水线**：
   - **Planner**：读取因果图谱与伏笔库，编译出确定性填空任务书。
   - **Writer**：按视角规范、反击前置与叙事温度句式进行初稿生成。
   - **Reviewer**：0ms 本地规则拦截 + LLM 深度审读质检。
   - **StateTracker**：状态增量回写至 SQLite 物理图谱与 FTS5 记忆库。
   - **Publisher**：格式净化、全书聚合与 TOC 目录树渲染。
3. **质量防御与自愈门禁**：
   - **Triplet Guard**：自动校验 `config.yaml`、`knowledge_graph.db`、`memory.db` 一致性。
   - **Anti-Slop 0ms 探针**：拦截常见 AI 空泛修辞、假寐套路与机械口号。

---

## ⚡ 快速上手 (Quick Start)

### 1. 环境准备

```bash
git clone https://github.com/JionLin/novel-pipeline-qimao-male.git
cd novel-pipeline-qimao-male
pip install -r requirements.txt
```

配置大模型 API 环境变量（支持任何兼容 OpenAI 接口规范的模型，如 DeepSeek、Claude、GPT-4o、Qwen 等）：

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 或你的中转/本地代理地址
export OPENAI_API_KEY="your-api-key"
```

---

### 2. 标准三步生成流程

#### 第一步：生成全书总纲与沙盒初始化
```bash
python3 scripts/auto_outline.py master "题材描述：历史架空/工业争霸/藩王就藩，主角利用现代工业知识在极北封地平推异族" 2700000
```
> 系统将自动在桌面/工作区创建独立小说沙盒，初始化 `config.yaml`、`knowledge_graph.db` 和 `memory.db`。

#### 第二步：生成分卷施工图与章节细纲
```bash
# 生成第 1 卷第 1 到 3 章细纲
python3 scripts/auto_outline.py chapters 1 3 1
```

#### 第三步：启动正文流水线生产
```bash
# 批量全自动生产第 1 到 3 章正文
python3 scripts/run_pipeline.py 1 3
```

---

### 3. 工具与运维看板

```bash
# 查看当前小说进度与商业指标看板
python3 scripts/tools/check_status.py

# 图谱节点与记忆库底层检视
python3 scripts/tools/inspect_db.py

# 章节时间旅行回滚（例如回滚到第 5 章）
python3 scripts/tools/rollback.py 5

# 执行 23 项全量自动化回归门禁测试
python3 scripts/test.py
```

---

## 🔌 作为 Hermes / AI Agent Skill 引入

本项目原生遵循 [Hermes](https://github.com/anthropics) / AI Agent Skill 规范，根目录提供 `SKILL.md`。

你可以直接将其引入你的 AI 助手工作区：
```bash
# 将本仓库克隆至 Hermes skills 目录
git clone https://github.com/JionLin/novel-pipeline-qimao-male.git ~/.hermes/skills/workflow/novel-pipeline-qimao-male
```
在与 AI 对话时即可直接通过自然语言触发：
- *“帮我构思一本【末日避难所】的小说大纲”*
- *“生成第 1 到 10 章细纲”*
- *“继续写后续 5 章正文”*

---

## 🗺️ 演进路线与待攻坚问题 (Roadmap & Future Work)

- [ ] **Prompt 叙事智能度升级**：降低模板化痕迹，强化对话中的潜台词与情绪留白。
- [ ] **GraphRAG 因果检索精度提升**：单章生成时实现动态实体剪枝，避免长上下文注意力分散。
- [ ] **多流派文体配方（Genres）扩展**：丰富仙侠、科幻、悬疑、女频等不同赛道的规则模板。
- [ ] **Web UI 可视化控制台**：支持章节大纲拖拽编排与角色图谱实时可视化编辑。
- [ ] **多模型异构调度**：大纲规划采用高推理模型（如 Claude 3.7 / o1 / R1），正文生成采用高吞吐模型。

---

## 🤝 参与贡献 (Contributing)

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 运行完整测试套件确保门禁全部通过 (`python3 scripts/test.py`)
4. 提交修改 (`git commit -m 'feat: add amazing feature'`)
5. 推送到分支 (`git push origin feature/amazing-feature`)
6. 发起 Pull Request

---

## 📄 开源许可 (License)

本项目采用 [MIT License](./LICENSE) 协议开源。

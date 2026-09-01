# 🛡️ pipeline 包：调度守卫与基础设施层

`pipeline` 包为整套小说流水线提供底层的质量守卫、单配置源解析、POSIX 原子安全落盘与 JIT 动态滑动上下文装配。

---

## 📂 模块清单与架构

```
pipeline/
├── __init__.py                # 统一导出守卫与基础设施函数
├── guards.py                  # 🛡️ 核心三要素强校验与动态自愈守卫 (Triplet Guard)
├── utils.py                   # 🧰 通用基础设施（单配置源加载器、原子写入、微创自愈）
├── prompt_loader.py           # 📜 两级 Prompt 模板加载与缓存引擎
├── context_builder.py         # 📖 细纲智能切片与高信噪比 AST 设定集提取
├── context_analyzer.py        # 🔬 动态滑动窗口前情提取与前史分析器
└── jit_buffer.py              # ⚡ JIT 细纲储备缓冲调度器
```

---

## 🛠️ 核心 API 与机制

### 1. 核心三要素强校验与动态自愈 (`guards.py`)
* **核心函数**：
  * `validate_and_heal_core_triplet(novel_dir, script_dir, fix_if_missing, log_func) -> bool`
  * `post_chapter_triplet_audit_and_heal(novel_dir, chapter_num, script_dir, log_func) -> dict`
* **机制**：
  * 在章节正文生成前后，自动对 `config.yaml`、`knowledge_graph.db`、`memory.db` 执行结构完整性、图拓扑孤儿边检测与 FTS5 倒排索引探针校验，发现轻微破损自动 0 秒自愈！

### 2. 单配置源统一调度与韧性基础设施 (`utils.py`)
* **核心函数**：
  * `load_active_config(script_dir, project_dir) -> dict`
  * `get_active_project_dir(script_dir) -> str`
  * `set_active_project_dir(novel_dir, script_dir) -> bool`
  * `atomic_write(file_path, content)`
  * `configure_sqlite_resilience(conn)` (WAL 模式、5秒 busy_timeout 与 NORMAL 同步)
  * `safe_chat_completion(client, model, messages, ...)` (指数退避容错调用)
  * `apply_surgical_micro_patch(content, cfg) -> (bool, str, list)` (0ms 正则微创自愈修剪)
* **机制**：
  * 通过 `scripts/.active_project` 指针秒级定位当前活动小说目录，100% 优先读取桌面小说的私有 `config.yaml`，消除全局多份配置冲突；
  * POSIX 原子替换保障文件绝对不产生 0 字节半损坏。

### 3. 上下文与元数据智能装配 (`context_builder.py`)
* **核心函数**：
  * `build_task_prompt(...)`、`build_novel_settings(...)`
  * `get_recent_chapter_types(novel_dir, current_ch, window_size)`
  * `build_chapter_type_advisory_directive(recent_types, target_ch)`
* **机制**：
  * 滑动窗口提取前 N 章类型分布，动态向细纲生成器注入 A~F 配额与熔断建议；
  * 自动装配角色锁、灵魂物象物理状态机快照与未决因果钩子。

### 4. 两级 Prompt 模板与文风卡加载器 (`prompt_loader.py`)
* **核心函数**：`load_prompt(prompt_name, custom_dir, reload) -> str`、`load_genre_prose_card(genre_name, stage, ...)`
* **机制**：优先加载项目工作区自定义的 `prompts/{name}.md`，回退加载全局 `scripts/prompts/{name}.md`，带内存缓存并支持阶段感知加载题材文风卡。

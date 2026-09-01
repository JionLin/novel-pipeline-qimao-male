# 小说流水线底层重构与零文件依赖架构变动记录 (CHANGELOG)

> **文档定位**：供后续 AI 快速了解系统架构演进、核心改动点、单一事实源（SSOT）设计规范及防硬编码门禁。  
> **更新时间**：2026-08-23  
> **适用版本**：Novel Multi-Agent Industrial Pipeline v22.0+

---

## 📌 一、 核心架构重构背景与目标

为彻底根除“多书并发/新旧书切换时配置互相污染”、“历史书名/角色名暗中残留”、“公共配置文件误删导致系统瘫痪”等痛点，本次对流水线底层进行了三大维度的彻底重构：
1. **单一事实源（SSOT）**：每本小说的所有元数据与规则 100% 封闭在自己的项目沙盒目录 `<novel_dir>/config.yaml` 中。
2. **零外部配置模板文件依赖（Zero-Template Architecture）**：彻底删除公共 `scripts/` 目录下的 `config.yaml` 和 `config.template.yaml`，转为代码内置的纯净内存骨架。
3. **全链路异常捕获与日志分级落盘**：所有智能体 API 崩溃、重试、质检打回、降级均显式输出为结构化 `[INFO]` / `[WARN]` / `[ERROR]` 并单向刷盘至 `<novel_dir>/日志.log`。

---

## 🛠️ 二、 具体代码文件改动明细

### 1. `pipeline/utils.py`
* **新增 `get_default_base_config()`**：
  * 内置极简纯净基础配置骨架（纯 Python 字典），仅包含核心模型选型（`models`）、质量字数标准（`quality: 2000~2800`）、三幕比例与状态追踪开关。
  * 0 外部文件读取，杜绝因文件丢失导致的初始化异常。
* **重构 `load_active_config()`**：
  * 100% 优先从当前活动项目目录（`get_active_project_dir()` ➔ `<novel_dir>/config.yaml`）读取唯一真实数据源。
  * 移除对 `scripts/config.yaml` 和 `scripts/config.template.yaml` 的任何物理读取依赖；无活动项目时优雅回退至 `get_default_base_config()`。
* **新增 `_resolve_scripts_root()`**：
  * 自动解析并标准化 `scripts/` 根目录物理路径，兼容在 `pipeline/`、`outline/`、`agents/` 等各级子模块中跨目录调度的路径自愈。
* **新增通用 LLM 重试网关 `safe_chat_completion()`**：
  * 统一封装大模型 API 请求，支持指数退避重试（Backoff Retry）与超时拦截，捕获网络崩溃并格式化抛出 `[WARN]` / `[ERROR]`。
* **新增内存启动日志暂存器 `LogMemoryBuffer`**：
  * 在项目物理沙盒尚未建立前（如开全书总纲前置阶段），先将启动日志暂存在内存队列中；沙盒建立完成后原子级 `flush_to_file` 刷入新书 `日志.log`。

---

### 2. `outline/cli_wizard.py`
* **重构 `bootstrap_project_workspace()`**：
  * 不再依赖外部 `config.template.yaml` 文件，直接基于 `get_default_base_config()` 初始化新书沙盒。
  * 自动从本次生成的 `大纲.md` 中动态正则提取**真实书名、题材标签、目标总字数、总章数及角色锁清单**，直接写入 `<novel_dir>/config.yaml`，实现元数据 100% 自动化闭环。
* **重构 `switch_project()`**：
  * 切换项目时仅更新目标项目私有的 `<target_proj_dir>/config.yaml` 与全局活动指针 `.active_project`，不再向公共 `scripts/` 目录下写入任何冗余文件。

---

### 3. `outline/master_generator.py`
* **解耦脚手架初始化调用**：
  * 移除对 `config.template.yaml` 路径的传递，总纲生成落盘后直接调用纯净版 `bootstrap_project_workspace(out_dir, master_text=result)`。
* **接入 `safe_chat_completion`**：
  * 总纲构思 API 遇网络抖动自动指数退避重试，崩溃时记录详细 `[ERROR]` 日志。

---

### 4. `outline/block_planner.py` & `outline/chapter_generator.py`
* **接入统一 LLM 安全网关**：
  * 施工图（Prompt 1）与章节细纲（Prompt 2）生成全量接入 `safe_chat_completion`。
  * 捕获长批次细纲生成超时与 YAML 解析异常，显式输出 `[WARN]` / `[ERROR]`。

---

### 5. `agents/agent_3_reviewer.py` (审稿品控智能体)
* **日志分级与溯源显式化**：
  * 初审不通过（FAIL）打回重写时，显式记录 `[WARN] [Reviewer] 第X章初审未通过 (FAIL)，触发自愈重写: {原因}`。
  * 审稿模型调用异常时，显式记录 `[ERROR] [Reviewer] 审稿模型调用失败: {e}`。

---

### 6. `pipeline/context_builder.py`
* **修复分卷大纲路由 `KeyError: 'outline'`**：
  * 将 `vol["outline"]` 强索引升级为安全回退访问 `vol.get("outline") or vol.get("file")`。

---

### 7. `pipeline/jit_buffer.py`
* **细化细纲缺失判定**：
  * 精确捕获 `ValueError` 作为细纲未就绪的触发条件，其余系统异常输出 `[WARN] [JIT] 检查细纲状态异常`，杜绝静默重试。

---

### 8. `run_pipeline.py` & `auto_outline.py`
* **日志格式净化与防双前缀**：
  * 增加正则前缀清洗，确保控制台与 `日志.log` 统一输出标准单标签 `[INFO]` / `[WARN]` / `[ERROR]`。
* **动态配置加载**：
  * 所有调度引擎统一通过 `load_active_config()` 按需获取当前活动小说配置。

---

## 🧪 三、 自动化质量门禁与验证套件

每次对底层引擎进行改动后，必须运行以下双重门禁确保 100% 健壮：

1. **全量单元与回归测试套件 (`python3 test.py`)**：
   * **Test 1**：细纲切片严格锚定测试
   * **Test 2**：方案 B 动态滑动细纲加载测试
   * **Test 3**：项目工作区日志单一落盘与纯净化测试
   * **Test 4**：CLI 参数智能解析兼容性测试
   * **Test 5**：全目录 Python 脚本 0 业务硬编码递归扫描
   * **Test 6**：底层【强制阻断门禁】真实拦截与防御测试
   * **Test 7**：核心三要素强校验与自动自愈守卫测试 (Triplet Guard)
   * **Test 8**：三要素深层正确性校验、动态变动沉淀与健康审计全生命周期测试
   * **Test 9**：提示词解耦与多级加载器覆盖机制测试
   * **Test 10**：POSIX 原子写入与 SQLite WAL 韧性模式压力测试
   * **Test 11**：Prompt Caching 静态前缀对齐与 KV 缓存命中测试
   * **Test 12**：本地微创自愈修剪、FTS5 时空衰减与目录树生成测试
   * **Test 13**：多题材跨界模糊对抗测试（赛博科幻 vs 都市神医 0 业务泄漏）
   * **Test 14**：日志分级落盘、启动缓冲 Flush 与 LLM 安全重试测试

2. **全链路防污染与数据一致性质检 (`python3 tools/verify_pipeline_integrity.py`)**：
   * 校验当前活跃项目 `config.yaml` 纯净度
   * 校验主角人设与角色锁动态绑定
   * 校验 Planner 任务书提示词纯净度
   * 校验项目专属 SQLite 知识图谱与 `memory.db` 双核就绪状态
   * 校验全题材热插拔扩展库覆盖度

---

## ⚠️ 四、 后续 AI 开发维护铁律（必读）

1. **严禁在 `scripts/` 下创建任何全局 `config.yaml` 或 `.template.yaml` 文件**。
2. **严禁在任何 `.py` 代码中硬编码具体书名、人名、境界或特定剧情名词**；所有规则必须下沉至配置文件或数据库。
3. **保持单一事实源原则**：代码中获取配置必须统一调用 `pipeline.utils.load_active_config()`。
4. **代码改动后必跑门禁**：改动任何底层逻辑后，必须运行 `python3 test.py` 确保 14 项测试全部通过（ALL 14 TEST SUITES PASSED）。

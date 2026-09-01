# 🛠️ tools 包：离线运维、状态观测与健康巡检工具箱

`tools` 包提供小说流水线在脱机与离线状态下的进度观测、图谱底层检视、时间旅行回滚与全流程健康巡检工具。

---

## 📂 模块清单与架构

```
tools/
├── __init__.py                # 统一导出运维工具接口
├── check_status.py            # 📊 实时进度与商业指标看板
├── inspect_db.py              # 🗄️ 图谱节点边与记忆库暗线伏笔检视器
├── rollback.py                # ⏪ 章节原子回滚与状态还原工具
└── verify_pipeline_integrity.py# 🔍 全流程环境与依赖健康度快速巡检器
```

---

## 💻 命令行工具执行方法

### 1. 实时进度看板 (`check_status.py`)
自动读取当前活动小说的正文目录、已交付章节、字数达标状态与图谱统计：
```bash
python3 tools/check_status.py
```
* **输出示例**：
  * 累计交付章节列表、单章字数、品控报告概要；
  * 知识图谱节点总数、因果关系边数、长程记忆线索数。

### 2. 数据库底层检视器 (`inspect_db.py`)
直接打印 `knowledge_graph.db` 和 `memory.db` 的底层数据结构：
```bash
python3 tools/inspect_db.py
```
* **输出内容**：
  * 核心角色节点与身份分类；
  * 社交与利益拓扑因果关系边；
  * `plot_vault` 活跃伏笔库与 `fts_lore` 全文索引条目。

### 3. 时间旅行章节回滚 (`rollback.py`)
将小说状态机、图谱和正文安全回滚至指定目标章节：
```bash
# 回滚至第 5 章（自动为被覆盖章节创建备份）
python3 tools/rollback.py 5

# 查看当前小说所有可用检查点
python3 tools/rollback.py list
```

### 4. 全流程健康巡检器 (`verify_pipeline_integrity.py`)
执行 0.2 秒静态健康巡检，校验当前活动小说项目完整性与依赖健康：
```bash
python3 tools/verify_pipeline_integrity.py
```

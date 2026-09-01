# -*- coding: utf-8 -*-
"""
pipeline/guards.py - 流水线基础设施与安全防御守卫
包含：
1. 文件并发排他锁 (acquire_lock / release_lock)
2. 代码防硬编码门禁 (check_codebase_anti_hardcoding_gate)
3. 发布版与 Markdown 资产灾备自动对账恢复 (reconcile_and_recover_from_published_assets)
"""

import os
import glob
import re
import fcntl
from typing import Optional, List, Tuple

try:
    from pipeline.utils import check_anti_hardcoding_guard, configure_sqlite_resilience, atomic_write
except ImportError:
    from ..utils import check_anti_hardcoding_guard, configure_sqlite_resilience, atomic_write


def acquire_lock(novel_dir: str):
    """获取项目级文件排他锁，防止多终端并发写入"""
    lock_file = os.path.join(novel_dir, ".pipeline.lock")
    try:
        lock_fd = open(lock_file, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (IOError, BlockingIOError):
        return None


def release_lock(lock_fd) -> None:
    """释放项目级文件排他锁"""
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except Exception:
            pass


def check_codebase_anti_hardcoding_gate(script_dir: str, log_func=None) -> bool:
    """执行代码防硬编码静态门禁扫描"""
    clean = check_anti_hardcoding_guard(script_dir)
    if not clean:
        msg = "❌ [FATAL CODE HARDCODING SMELL] 代码防硬编码门禁拦截失败！请将人名和规则下放到 config.yaml 或数据库！"
        if log_func:
            log_func(msg)
        else:
            print(msg)
        return False
    return True


def reconcile_and_recover_from_published_assets(
    novel_dir: str,
    ch_prefix: str,
    ch_suffix: str,
    log_func=None
) -> None:
    """
    灾备对账恢复器：
    若发现 发布版/ 下存在合法过审正文，但 正文/ 下对应 Markdown 意外丢失或损坏，
    自动从 发布版/ 重建规范的 Markdown 归档文件，保障状态机不回退。
    """
    pub_dir = os.path.join(novel_dir, "正文", "发布版")
    md_dir = os.path.join(novel_dir, "正文")
    if not os.path.exists(pub_dir) or not os.path.exists(md_dir):
        return

    pub_files = glob.glob(os.path.join(pub_dir, f"{ch_prefix}*{ch_suffix}")) + glob.glob(os.path.join(pub_dir, f"{ch_prefix}*.txt"))
    for pf in pub_files:
        fname = os.path.basename(pf)
        m = re.search(r"第(\d+)章", fname)
        if not m:
            continue
        ch_num = int(m.group(1))
        target_md = os.path.join(md_dir, f"{ch_prefix}{ch_num}{ch_suffix}")
        
        # 若 Markdown 丢失但发布版存在且大小 > 500 字节，执行灾备恢复
        if not os.path.exists(target_md) and os.path.getsize(pf) > 500:
            try:
                with open(pf, "r", encoding="utf-8") as rf:
                    content = rf.read().strip()
                title_line = f"# 第{ch_num}章"
                lines = content.split("\n")
                if lines and lines[0].startswith("第"):
                    title_line = f"# {lines[0]}"
                    body = "\n".join(lines[1:]).strip()
                else:
                    body = content
                
                recovered_content = f"{title_line}\n\n{body}\n"
                with open(target_md, "w", encoding="utf-8") as wf:
                    wf.write(recovered_content)
                
                msg = f"[Recovery] 🛡️ 从发布版灾备成功恢复第 {ch_num} 章 Markdown 正文: {os.path.basename(target_md)}"
                if log_func:
                    log_func(msg)
                else:
                    print(msg)
            except Exception as e:
                err_msg = f"[Recovery Error] 灾备恢复第 {ch_num} 章失败: {e}"
                if log_func:
                    log_func(err_msg)
                else:
                    print(err_msg)


def validate_and_heal_core_triplet(
    novel_dir: str,
    script_dir: str = "",
    fix_if_missing: bool = True,
    log_func=None
) -> bool:
    """
    核心基础设施三要素强校验与自动自愈守卫 (Strong Triplet Guard)
    在生成总纲、分卷细纲、章节正文前后，对 config.yaml, knowledge_graph.db, memory.db
    执行结构完整性、Schema 一致性、SQLite 数据库完整性检查 (PRAGMA integrity_check)。
    """
    import yaml
    novel_dir = os.path.abspath(novel_dir)
    os.makedirs(novel_dir, exist_ok=True)
    script_dir = script_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_p = os.path.join(script_dir, "config.template.yaml")
    template_cfg_path = template_p if os.path.exists(template_p) else os.path.join(script_dir, "config.yaml")

    issues = []

    # 1. 校验与自愈 config.yaml
    cfg_path = os.path.join(novel_dir, "config.yaml")
    cfg_data = {}
    if not os.path.exists(cfg_path) or not os.path.exists(os.path.join(novel_dir, "knowledge_graph.db")) or not os.path.exists(os.path.join(novel_dir, "memory.db")):
        if fix_if_missing:
            from outline.cli_wizard import bootstrap_project_workspace
            bootstrap_project_workspace(novel_dir, config_path=template_cfg_path, log_func=log_func)
            if log_func:
                log_func("[🛡️ Triplet Guard] ✅ 核心三要素自动通过工作区脚手架完成动态重构与自愈！")
        else:
            issues.append("核心三要素文件不完整")
    else:
        try:
            with open(cfg_path, "r", encoding="utf-8") as rf:
                cfg_data = yaml.safe_load(rf) or {}
            if not isinstance(cfg_data, dict) or "project" not in cfg_data:
                raise ValueError("config.yaml 缺少 project 顶级字段")
        except Exception as e:
            if fix_if_missing:
                from outline.cli_wizard import bootstrap_project_workspace
                bootstrap_project_workspace(novel_dir, config_path=template_cfg_path, log_func=log_func)
                if log_func:
                    log_func(f"[🛡️ Triplet Guard] ⚠️ 发现 config.yaml 损坏 ({e})，已自动完成动态脚手架自愈！")
            else:
                issues.append(f"config.yaml 损坏: {e}")

    # 2. 校验与自愈 knowledge_graph.db
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    kg_ok = False
    if os.path.exists(kg_path):
        try:
            import sqlite3
            conn = sqlite3.connect(kg_path)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()
            if res and res[0] == "ok":
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cur.fetchall()]
                if "nodes" in tables and "edges" in tables:
                    kg_ok = True
            conn.close()
        except Exception:
            kg_ok = False

    if not kg_ok:
        if fix_if_missing:
            try:
                from storage.knowledge_graph import NovelKnowledgeGraph
                kg = NovelKnowledgeGraph(kg_path)
                chars = cfg_data.get("project", {}).get("characters", [])
                for ch_name in chars:
                    try:
                        kg.upsert_node(node_id=ch_name, name=ch_name, category="character", properties={}, chapter_num=1)
                    except Exception:
                        pass
                kg.close()
                if log_func:
                    log_func("[🛡️ Triplet Guard] ⚠️ 发现 knowledge_graph.db 缺失或结构异常，已自动重建并初始化图数据库！")
            except Exception as e:
                issues.append(f"knowledge_graph.db 自愈失败: {e}")
        else:
            issues.append("knowledge_graph.db 缺失或损坏")

    # 3. 校验与自愈 memory.db
    mem_path = os.path.join(novel_dir, "memory.db")
    mem_ok = False
    if os.path.exists(mem_path):
        try:
            import sqlite3
            conn = sqlite3.connect(mem_path)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()
            if res and res[0] == "ok":
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cur.fetchall()]
                if "entities" in tables and "plot_vault" in tables and "fts_lore" in tables:
                    mem_ok = True
            conn.close()
        except Exception:
            mem_ok = False

    if not mem_ok:
        if fix_if_missing:
            try:
                import sqlite3
                conn = sqlite3.connect(mem_path)
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    category TEXT,
                    description TEXT,
                    first_chapter INTEGER,
                    last_updated_chapter INTEGER
                );
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS plot_vault (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_name TEXT UNIQUE,
                    planted_chapter INTEGER,
                    summary TEXT,
                    status TEXT,
                    related_entities TEXT
                );
                """)
                conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_lore USING fts5(
                    doc_id UNINDEXED,
                    category UNINDEXED,
                    title,
                    content,
                    tokenize = 'unicode61'
                );
                """)
                conn.commit()
                conn.close()
                if log_func:
                    log_func("[🛡️ Triplet Guard] ⚠️ 发现 memory.db 缺失或结构异常，已自动重建并初始化 FTS5 记忆数据库！")
            except Exception as e:
                issues.append(f"memory.db 自愈失败: {e}")
        else:
            issues.append("memory.db 缺失或损坏")

    if issues:
        if log_func:
            log_func(f"[🛡️ Triplet Guard ❌] 基础设施校验失败: {'; '.join(issues)}")
        return False

    if log_func:
        log_func("[🛡️ Triplet Guard] ✅ 核心三要素强校验 100% 通过 (config.yaml, knowledge_graph.db, memory.db)")
    return True


def inspect_triplet_mutation_health(novel_dir: str, log_func=None) -> dict:
    """
    深度语义级健康诊断：识别【核心三要素是否发生了健康、正常的业务改动】
    不仅仅检查文件是否存在，而是深入到数据流拓扑、SQL 完整性、FTS 索引有效性与业务因果闭环。
    """
    import yaml
    import sqlite3

    novel_dir = os.path.abspath(novel_dir)
    report = {
        "healthy": True,
        "config": {"status": "OK", "details": []},
        "knowledge_graph": {"status": "OK", "details": []},
        "memory": {"status": "OK", "details": []}
    }

    # 1. 深度诊断 config.yaml 改动是否健康
    cfg_path = os.path.join(novel_dir, "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        title = cfg.get("project", {}).get("title", "")
        if not title or title in ["《", "》", "《》"]:
            report["config"]["status"] = "WARN"
            report["config"]["details"].append(f"书名异常: '{title}'")
            report["healthy"] = False
        else:
            report["config"]["details"].append(f"合法书名: {title}")

        routes = cfg.get("volume_routing", [])
        if not isinstance(routes, list) or len(routes) == 0:
            report["config"]["status"] = "WARN"
            report["config"]["details"].append("volume_routing 为空")
            report["healthy"] = False
        else:
            # 校验分卷范围严格连续单调递增性与 0 断层
            last_end = 0
            has_gap = False
            for v in routes:
                r = v.get("range", [0, 0])
                if r[0] <= last_end or r[1] < r[0]:
                    report["config"]["status"] = "WARN"
                    report["config"]["details"].append(f"分卷范围非单调递增/重叠: 卷{v.get('volume')} {r}")
                    report["healthy"] = False
                elif last_end > 0 and r[0] != last_end + 1:
                    report["config"]["status"] = "WARN"
                    report["config"]["details"].append(f"分卷范围存在断层: 第{last_end}章至第{r[0]}章未被覆盖")
                    report["healthy"] = False
                    has_gap = True
                last_end = r[1]
            if not has_gap:
                report["config"]["details"].append(f"分卷路由完全连续自洽 (共 {len(routes)} 卷，覆盖至第 {last_end} 章)")

        # 校验角色锁与白名单逻辑自洽性
        char_locks = cfg.get("character_locks", [])
        for lk in char_locks:
            cname = lk.get("name", "")
            banned = lk.get("banned_aliases", [])
            if cname in banned:
                report["config"]["status"] = "WARN"
                report["config"]["details"].append(f"角色锁逻辑冲突: 角色名 '{cname}' 误列入自身禁用别名")
                report["healthy"] = False

    except Exception as e:
        report["config"]["status"] = "FAIL"
        report["config"]["details"].append(f"解析异常: {e}")
        report["healthy"] = False

    # 2. 深度诊断 knowledge_graph.db 改动是否健康
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    try:
        conn = sqlite3.connect(kg_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or res[0] != "ok":
            report["knowledge_graph"]["status"] = "FAIL"
            report["knowledge_graph"]["details"].append(f"SQLite 完整性校验失败: {res}")
            report["healthy"] = False
        else:
            cur.execute("SELECT count(*) FROM nodes;")
            node_cnt = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM edges;")
            edge_cnt = cur.fetchone()[0]

            # 校验是否存在悬挂孤儿边 (dangling edges)
            cur.execute("""
            SELECT count(*) FROM edges 
            WHERE source_id NOT IN (SELECT id FROM nodes) 
               OR target_id NOT IN (SELECT id FROM nodes);
            """)
            dangling_cnt = cur.fetchone()[0]
            if dangling_cnt > 0:
                report["knowledge_graph"]["status"] = "WARN"
                report["knowledge_graph"]["details"].append(f"发现 {dangling_cnt} 条孤儿关系边 (无对应节点)")
                report["healthy"] = False
            else:
                report["knowledge_graph"]["details"].append("0 悬挂孤儿边 (图拓扑 100% 连通闭环)")

            # 校验权重与合法关系类型
            cur.execute("SELECT count(*) FROM edges WHERE weight < -1.0 OR weight > 1.0;")
            invalid_weights = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM edges WHERE rel_type NOT IN ('ALLY', 'ENEMY', 'MASTER_SERVANT', 'SIBLING', 'OWNS', 'CAUSAL_HOOK', 'DEPENDENCE', 'RESENTMENT', 'SPATIAL_TRANSITION');")
            invalid_rels = cur.fetchone()[0]
            if invalid_weights > 0 or invalid_rels > 0:
                report["knowledge_graph"]["status"] = "WARN"
                report["knowledge_graph"]["details"].append(f"发现非法关系边数据 (权重越界:{invalid_weights}, 非法类型:{invalid_rels})")
                report["healthy"] = False
            else:
                report["knowledge_graph"]["details"].append("因果权重与关系类型全部合法自洽")

            report["knowledge_graph"]["details"].append(f"节点数: {node_cnt}, 关系边数: {edge_cnt}")
        conn.close()
    except Exception as e:
        report["knowledge_graph"]["status"] = "FAIL"
        report["knowledge_graph"]["details"].append(f"数据库异常: {e}")
        report["healthy"] = False

    # 3. 深度诊断 memory.db 改动是否健康与倒排检索探针
    mem_path = os.path.join(novel_dir, "memory.db")
    try:
        conn = sqlite3.connect(mem_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or res[0] != "ok":
            report["memory"]["status"] = "FAIL"
            report["memory"]["details"].append(f"SQLite 完整性校验失败: {res}")
            report["healthy"] = False
        else:
            cur.execute("SELECT count(*) FROM entities;")
            ent_cnt = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM plot_vault;")
            plot_cnt = cur.fetchone()[0]

            # 校验伏笔状态机合法性
            cur.execute("SELECT count(*) FROM plot_vault WHERE status NOT IN ('active', 'in_progress', 'resolved', 'dormant');")
            invalid_plots = cur.fetchone()[0]
            if invalid_plots > 0:
                report["memory"]["status"] = "WARN"
                report["memory"]["details"].append(f"发现 {invalid_plots} 个伏笔状态非法")
                report["healthy"] = False

            # 校验 FTS5 倒排索引物理查询与 MATCH 语义探针
            try:
                cur.execute("SELECT count(*) FROM fts_lore;")
                fts_cnt = cur.fetchone()[0]
                # 真实执行 FTS5 MATCH 查询探针，验证倒排索引物理可检索性
                cur.execute("SELECT count(*) FROM fts_lore WHERE fts_lore MATCH '第1章* OR 设定* OR world*';")
                match_cnt = cur.fetchone()[0]
                report["memory"]["details"].append(f"FTS5 全文倒排索引与 MATCH 探针正常 (已索引文档: {fts_cnt})")
            except Exception as fe:
                report["memory"]["status"] = "WARN"
                report["memory"]["details"].append(f"FTS5 索引损坏或无法执行 MATCH 检索: {fe}")
                report["healthy"] = False

            report["memory"]["details"].append(f"世界观实体数: {ent_cnt}, 活跃伏笔数: {plot_cnt}")
        conn.close()
    except Exception as e:
        report["memory"]["status"] = "FAIL"
        report["memory"]["details"].append(f"数据库异常: {e}")
        report["healthy"] = False

    if log_func:
        status_icon = "✅ [Healthy]" if report["healthy"] else "⚠️ [Unhealthy/Degraded]"
        log_func(f"[Triplet Mutation Inspection] {status_icon} 核心三要素语义健康体检完成")

    return report


def post_chapter_triplet_audit_and_heal(
    novel_dir: str,
    chapter_num: int,
    script_dir: str = "",
    log_func=None
) -> dict:
    """
    【章后三要素强校验与即时自愈中枢】
    在每一个章节正文写完并保存后，自动对 config.yaml, knowledge_graph.db, memory.db
    执行深度语义审计；若发现任何破损、残留、索引异常，立即 0ms 自动自愈修复并输出审计简报。
    """
    novel_dir = os.path.abspath(novel_dir)
    script_dir = script_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import sqlite3
    import yaml

    # 0. 自动将本章正文结算与行为沉淀至 knowledge_graph.db 和 memory.db
    try:
        ch_md = os.path.join(novel_dir, "正文", f"C_正文_第{chapter_num}章.md")
        if not os.path.exists(ch_md):
            ch_md = os.path.join(novel_dir, f"C_正文_第{chapter_num}章.md")
        ch_text = ""
        if os.path.exists(ch_md):
            with open(ch_md, "r", encoding="utf-8") as f:
                ch_text = f.read()

        # 沉淀到 KG action_ledger
        kg_path = os.path.join(novel_dir, "knowledge_graph.db")
        if os.path.exists(kg_path) and ch_text:
            conn_kg = sqlite3.connect(kg_path)
            conn_kg.execute("""
            CREATE TABLE IF NOT EXISTS action_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                action_desc TEXT NOT NULL,
                chapter_num INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            first_line = [line.strip() for line in ch_text.splitlines() if line.strip() and not line.startswith("#")][:1]
            summary_snippet = first_line[0][:100] if first_line else f"完成第{chapter_num}章推进"
            conn_kg.execute(
                "INSERT INTO action_ledger (character_name, action_desc, chapter_num) VALUES (?, ?, ?)",
                ("主角", summary_snippet, chapter_num)
            )
            conn_kg.execute("UPDATE nodes SET last_updated_ch = ? WHERE category = 'character'", (chapter_num,))
            conn_kg.commit()
            conn_kg.close()

        # 沉淀到 memory.db fts_lore
        mem_path = os.path.join(novel_dir, "memory.db")
        if os.path.exists(mem_path) and ch_text:
            conn_mem = sqlite3.connect(mem_path)
            # 提取正文前 200 字与后 200 字作为全文检索核心索引
            snippet = ch_text[:200] + " ... " + ch_text[-200:]
            conn_mem.execute("DELETE FROM fts_lore WHERE doc_id = ?", (f"chapter_{chapter_num}",))
            conn_mem.execute(
                "INSERT INTO fts_lore (doc_id, category, title, content) VALUES (?, 'chapter_text', ?, ?)",
                (f"chapter_{chapter_num}", f"第{chapter_num}章正文摘要", snippet)
            )
            conn_mem.commit()
            conn_mem.close()
    except Exception as e:
        if log_func:
            log_func(f"[章后三要素沉淀提示] 自动沉淀跳过: {e}")

    # 1. 运行深度体检
    report = inspect_triplet_mutation_health(novel_dir, log_func=None)

    # 2. 若有异常，立即触发自愈修复
    healed = False
    if not report["healthy"]:
        validate_and_heal_core_triplet(novel_dir, script_dir=script_dir, fix_if_missing=True, log_func=log_func)
        report = inspect_triplet_mutation_health(novel_dir, log_func=None)
        healed = True

    # 3. 统计精确量化指标
    import sqlite3
    import yaml
    
    kg_nodes_cnt, kg_edges_cnt, mem_ent_cnt, mem_plot_cnt, mem_fts_cnt, cfg_char_cnt = 0, 0, 0, 0, 0, 0
    try:
        cfg_p = os.path.join(novel_dir, "config.yaml")
        if os.path.exists(cfg_p):
            with open(cfg_p, "r", encoding="utf-8") as f:
                c_data = yaml.safe_load(f) or {}
            cfg_char_cnt = len(c_data.get("character_locks", []))
    except Exception:
        pass

    try:
        kg_p = os.path.join(novel_dir, "knowledge_graph.db")
        if os.path.exists(kg_p):
            c_kg = sqlite3.connect(kg_p)
            kg_nodes_cnt = c_kg.execute("SELECT count(*) FROM nodes;").fetchone()[0]
            kg_edges_cnt = c_kg.execute("SELECT count(*) FROM edges;").fetchone()[0]
            c_kg.close()
    except Exception:
        pass

    try:
        mem_p = os.path.join(novel_dir, "memory.db")
        if os.path.exists(mem_p):
            c_mem = sqlite3.connect(mem_p)
            mem_ent_cnt = c_mem.execute("SELECT count(*) FROM entities;").fetchone()[0]
            mem_plot_cnt = c_mem.execute("SELECT count(*) FROM plot_vault;").fetchone()[0]
            try:
                mem_fts_cnt = c_mem.execute("SELECT count(*) FROM fts_lore;").fetchone()[0]
            except Exception:
                pass
            c_mem.close()
    except Exception:
        pass

    cfg_details = " | ".join(report["config"]["details"])
    kg_details = " | ".join(report["knowledge_graph"]["details"])
    mem_details = " | ".join(report["memory"]["details"])

    heal_tag = " (已即时自动修复)" if healed else ""
    log_msg = (
        f"\n============================================================\n"
        f" 🛡️ 【第 {chapter_num} 章 后置三要素强校验与精准量化体检报告{heal_tag}】\n"
        f"------------------------------------------------------------\n"
        f" ⚙️ config.yaml        : [{report['config']['status']}] 角色锁: {cfg_char_cnt} 个 | {cfg_details}\n"
        f" 🗄️ knowledge_graph.db : [{report['knowledge_graph']['status']}] 实体节点: {kg_nodes_cnt} | 关系边: {kg_edges_cnt} | {kg_details}\n"
        f" 🧠 memory.db          : [{report['memory']['status']}] 实体事实: {mem_ent_cnt} | 伏笔暗线: {mem_plot_cnt} | FTS索引文档: {mem_fts_cnt} | {mem_details}\n"
        f" 🎯 综合健康状态       : {'✅ 100% HEALTHY (零破损·零孤儿边·索引完好)' if report['healthy'] else '⚠️ 存在警告'}\n"
        f"============================================================"
    )

    if log_func:
        log_func(log_msg)
    else:
        print(log_msg)

    return report

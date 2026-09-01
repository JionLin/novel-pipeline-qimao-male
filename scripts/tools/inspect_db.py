#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说双数据库一键极速查看器 (SQLite Visual Inspector for Novel Pipeline)
用法：
  python3 scripts/tools/inspect_db.py kg        # 查看知识图谱节点与因果拓扑
  python3 scripts/tools/inspect_db.py memory    # 查看长程记忆库与暗线伏笔
  python3 scripts/tools/inspect_db.py all       # 综合查看双库健康状态
  python3 scripts/tools/inspect_db.py mermaid   # 导出知识图谱 Mermaid 流程图代码 (可直接在 Markdown 或网页中渲染)
  python3 scripts/tools/inspect_db.py all /path/to/novel_dir  # 指定小说目录查看
"""

import os
import sys
import glob
import sqlite3

SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)

from pipeline.utils import load_active_config, configure_sqlite_resilience, get_active_project_dir


def resolve_novel_dir(custom_path: str = "") -> str:
    """智能解析活动小说工作区目录"""
    if custom_path and os.path.exists(custom_path):
        return os.path.abspath(custom_path)
    
    # 1. 从 .active_project 指针获取
    act_dir = get_active_project_dir(SCRIPTS_ROOT)
    if act_dir and os.path.exists(act_dir):
        return act_dir
    
    # 2. 从 load_active_config 获取
    cfg = load_active_config(script_dir=SCRIPTS_ROOT)
    novel_dir = cfg.get("project", {}).get("novel_dir", "")
    if novel_dir and os.path.exists(novel_dir):
        return os.path.abspath(novel_dir)
    
    # 3. 自动探测桌面最新小说目录
    desktop_novels = os.path.expanduser("~/Desktop/生成的小说")
    if os.path.exists(desktop_novels):
        dirs = [os.path.join(desktop_novels, d) for d in os.listdir(desktop_novels) if os.path.isdir(os.path.join(desktop_novels, d))]
        if dirs:
            dirs.sort(key=os.path.getmtime, reverse=True)
            return dirs[0]
            
    return ""


def inspect_kg(novel_dir: str):
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    print("\n" + "="*70)
    print(f"      🗄️  知识图谱 (knowledge_graph.db) 节点与关系总览")
    print(f"      📂 小说目录: {novel_dir}")
    print("="*70)
    if not os.path.exists(kg_path):
        print(f"❌ 未找到知识图谱数据库: {kg_path}")
        return
    
    conn = sqlite3.connect(kg_path)
    configure_sqlite_resilience(conn)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM nodes")
    node_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM edges")
    edge_cnt = c.fetchone()[0]
    
    print(f"📊 统计数据: 共 {node_cnt} 个实体节点 | {edge_cnt} 条因果关系边\n")
    
    print("【核心角色与重要实体列表 (前 15 条)】:")
    c.execute("PRAGMA table_info(nodes)")
    n_cols = [r[1] for r in c.fetchall()]
    type_col = "entity_type" if "entity_type" in n_cols else ("category" if "category" in n_cols else "name")
    c.execute(f"SELECT id, name, {type_col} FROM nodes LIMIT 15")
    for row in c.fetchall():
        print(f"  🔹 [{row[2]}] {row[1]} (ID: {row[0]})")
    
    print("\n【核心因果与社交拓扑边 (前 15 条)】:")
    c.execute("PRAGMA table_info(edges)")
    e_cols = [r[1] for r in c.fetchall()]
    src_col = "source" if "source" in e_cols else "source_id"
    tgt_col = "target" if "target" in e_cols else "target_id"
    rel_col = "relation_type" if "relation_type" in e_cols else "rel_type"
    c.execute(f"SELECT {src_col}, {rel_col}, {tgt_col}, description FROM edges LIMIT 15")
    for row in c.fetchall():
        print(f"  🔗 {row[0]} ──[{row[1]}]──► {row[2]}  ({row[3]})")
    
    conn.close()


def inspect_memory(novel_dir: str):
    mem_path = os.path.join(novel_dir, "memory.db")
    print("\n" + "="*70)
    print(f"      🧠  长程记忆库 (memory.db) 暗线伏笔与全文索引")
    print(f"      📂 小说目录: {novel_dir}")
    print("="*70)
    if not os.path.exists(mem_path):
        print(f"❌ 未找到记忆库数据库: {mem_path}")
        return
    
    conn = sqlite3.connect(mem_path)
    configure_sqlite_resilience(conn)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM plot_vault")
    pv_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM fts_lore")
    fts_cnt = c.fetchone()[0]
    
    print(f"📊 统计数据: 伏笔库 {pv_cnt} 条 | FTS5 全文索引 {fts_cnt} 条\n")
    
    print("【长线暗线伏笔库 (Plot Vault 前 15 条)】:")
    c.execute("PRAGMA table_info(plot_vault)")
    pv_cols = [r[1] for r in c.fetchall()]
    title_col = "title" if "title" in pv_cols else "thread_name"
    ch_col = "planted_ch" if "planted_ch" in pv_cols else "planted_chapter"
    content_col = "content" if "content" in pv_cols else "summary"
    c.execute(f"SELECT {title_col}, {ch_col}, {content_col}, status FROM plot_vault LIMIT 15")
    for row in c.fetchall():
        print(f"  📌 [{row[3].upper()}] 第{row[1]}章: {row[0]}")
        print(f"     └─ 内容: {row[2]}")
    
    conn.close()


def export_mermaid(novel_dir: str):
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    print("\n" + "="*70)
    print(f"      🎨  知识图谱 Mermaid 可视化拓扑图代码")
    print(f"      📂 小说目录: {novel_dir}")
    print("="*70)
    if not os.path.exists(kg_path):
        print(f"❌ 未找到知识图谱: {kg_path}")
        return
    
    conn = sqlite3.connect(kg_path)
    configure_sqlite_resilience(conn)
    c = conn.cursor()
    c.execute("PRAGMA table_info(edges)")
    e_cols = [r[1] for r in c.fetchall()]
    src_col = "source" if "source" in e_cols else "source_id"
    tgt_col = "target" if "target" in e_cols else "target_id"
    rel_col = "relation_type" if "relation_type" in e_cols else "rel_type"
    c.execute(f"SELECT {src_col}, {rel_col}, {tgt_col}, description FROM edges LIMIT 25")
    edges = c.fetchall()
    conn.close()

    print("```mermaid")
    print("graph TD")
    for src, rel, tgt, desc in edges:
        s = src.replace("char:", "").replace("item:", "").replace("faction:", "")
        t = tgt.replace("char:", "").replace("item:", "").replace("faction:", "")
        print(f'    {s} -->|"{rel}: {desc[:12]}"| {t}')
    print("```")
    print("\n💡 提示：将上述代码复制到任何 Markdown 预览器（如 Notion / Typora / GitHub / VS Code）即可直观看到角色网络拓扑！")


if __name__ == "__main__":
    mode = "all"
    custom_dir = ""
    for arg in sys.argv[1:]:
        if arg in ["kg", "memory", "all", "mermaid"]:
            mode = arg
        elif os.path.exists(arg):
            custom_dir = arg

    resolved_novel_dir = resolve_novel_dir(custom_dir)
    if not resolved_novel_dir:
        print("❌ 错误: 未能定位到有效的小说工作区目录，请指定路径或通过 auto_outline.py 初始化项目。")
        sys.exit(1)

    if mode == "kg":
        inspect_kg(resolved_novel_dir)
    elif mode == "memory":
        inspect_memory(resolved_novel_dir)
    elif mode == "mermaid":
        export_mermaid(resolved_novel_dir)
    else:
        inspect_kg(resolved_novel_dir)
        inspect_memory(resolved_novel_dir)

import os, sys
SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说写作流水线进度看板
"""
import os, glob, re, sys, yaml
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
from pipeline.utils import count_chinese_chars, load_active_config

cfg = load_active_config(script_dir=SCRIPTS_ROOT)

NOVEL_DIR = cfg.get("project", {}).get("novel_dir", "")
MIN_CHARS = cfg.get("quality", {}).get("min_chinese_chars", 2000)
MAX_CHARS = cfg.get("quality", {}).get("max_chinese_chars", 2800)

def check():
    print("=" * 65)
    print("        📖 小说多Agent写作流水线 — 实时进度看板")
    print("=" * 65)
    print(f"小说正文目录: {NOVEL_DIR}")
    print(f"字数标准要求: {MIN_CHARS} - {MAX_CHARS} 字 (目标 2400 字)")
    print("-" * 65)

    ch_files = sorted(glob.glob(os.path.join(NOVEL_DIR, "正文", "C_正文_第*章.md")), 
                      key=lambda x: int(re.search(r'第(\d+)章', x).group(1)) if re.search(r'第(\d+)章', x) else 0)
    if not ch_files:
        ch_files = sorted(glob.glob(os.path.join(NOVEL_DIR, "C_正文_第*章.md")), 
                          key=lambda x: int(re.search(r'第(\d+)章', x).group(1)) if re.search(r'第(\d+)章', x) else 0)

    total_words = 0
    print(f"\n【已完成并过审章节列表】(共 {len(ch_files)} 章):")
    for cf in ch_files:
        fname = os.path.basename(cf)
        ch_num_match = re.search(r'第(\d+)章', fname)
        ch_num = int(ch_num_match.group(1)) if ch_num_match else 0
        content = open(cf, encoding="utf-8").read()
        wc = count_chinese_chars(content)
        total_words += wc
        
        # 质检报告在新架构位于 checkpoints/chapter_XXX/review_report.md（旧版根目录报告兼容检测）
        report_file = os.path.join(NOVEL_DIR, "checkpoints", f"chapter_{ch_num:03d}", "review_report.md")
        has_rep = "📑 有报告" if os.path.exists(report_file) else ("📑 有报告" if os.path.exists(os.path.join(NOVEL_DIR, f"第{ch_num:03d}章_自检清单分析报告.md")) else "无报告")
        status = "✅ 达标" if MIN_CHARS <= wc <= MAX_CHARS else f"⚠️ {wc}字"
        
        # 提取标题
        title_m = re.search(r'^#\s*第\d+章[：:](.*)$', content, re.MULTILINE)
        title_str = title_m.group(1).strip() if title_m else ""
        if len(title_str) > 18:
            title_str = title_str[:16] + "..."
            
        status = "✅ 达标" if MIN_CHARS <= wc <= MAX_CHARS + 10 else f"⚠️ {wc}字"
        print(f"   ├─ 第{ch_num:02d}章: {title_str:<18} | {wc:5d} 字 | {status} | {has_rep}")

    print("-" * 65)
    print(f"📊 汇总统计: 已成功交付 {len(ch_files)} 章 | 累计正文字数: {total_words} 字")
    
    # 知识图谱与长程记忆健康度
    kg_db = os.path.join(NOVEL_DIR, "knowledge_graph.db")
    mem_db = os.path.join(NOVEL_DIR, "memory.db")
    kg_nodes, kg_edges, mem_count, unresolved_edges = 0, 0, 0, 0
    try:
        import sqlite3, json
        if os.path.exists(kg_db):
            with sqlite3.connect(kg_db) as conn:
                c = conn.cursor()
                kg_nodes = c.execute("SELECT count(*) FROM nodes").fetchone()[0]
                kg_edges = c.execute("SELECT count(*) FROM edges").fetchone()[0]
                rows = c.execute("SELECT properties FROM edges").fetchall()
                for r in rows:
                    p = json.loads(r[0]) if r[0] else {}
                    if p.get("resolution_status") == "UNRESOLVED":
                        unresolved_edges += 1
        if os.path.exists(mem_db):
            with sqlite3.connect(mem_db) as conn:
                c = conn.cursor()
                try:
                    mem_count = c.execute("SELECT count(*) FROM plot_threads").fetchone()[0]
                except Exception:
                    try:
                        mem_count = c.execute("SELECT count(*) FROM plot_vault").fetchone()[0]
                    except Exception:
                        mem_count = 0
    except Exception:
        pass
    print(f"🧠 图谱与记忆: 图谱节点 {kg_nodes} 个 | 关系边 {kg_edges} 条 (待闭环因果 {unresolved_edges} 条) | LTM线索 {mem_count} 条")
    print("=" * 65)

if __name__ == "__main__":
    from pipeline.utils import check_anti_hardcoding_guard
    if not check_anti_hardcoding_guard(SCRIPTS, os.path.join(SCRIPTS, "config.yaml")):
        sys.exit(1)
    check()

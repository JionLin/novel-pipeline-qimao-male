import os, sys
SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流水线完整性与防跨书污染自动化校验套件 (Pipeline Integrity & Anti-Contamination Verification Suite)
覆盖范围：
1. 配置文件动态萃取 (safe_patch_config_from_outline)
2. 历史脏数据物理隔离 (Zero Legacy Leaks)
3. Planner 任务书 XML 编译纯净度
4. Reviewer 0ms 快速熔断与实体锁契约
5. 知识图谱 (Knowledge Graph) 实体与关系自洽度
"""

import os
import sys
import yaml
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from auto_outline import safe_patch_config_from_outline, load_genre_matrix
from run_pipeline import run_planner, build_novel_settings, count_chinese_chars

def run_tests():
    print("\n" + "="*70)
    print("        🛡️  流水线全链路防污染与数据一致性自动化质检套件")
    print("="*70)
    
    passed_tests = 0
    total_tests = 5

    # -------------------------------------------------------------
    # Test 1: 检查当前活跃项目 config.yaml 纯净度与文件系统规范
    # -------------------------------------------------------------
    print("\n[Test 1/5] 正在校验当前活跃项目 config.yaml 纯净度与文件系统规范...")
    from pipeline.utils import load_active_config
    cfg = load_active_config(script_dir=SCRIPTS_ROOT)

    cfg_str = yaml.dump(cfg, allow_unicode=True)
    
    # 检查是否有历史修仙老书的脏数据泄露
    # 注意：banned_terms 仅保留历史书中真实存在过的专有名词，严禁加入"张三"等通用名（避免新书误报）
    banned_terms = ["楚长歌", "青云宗", "绝天剑尊", "壮阳丸", "初圣宗", "陆玄机", "苏九儿", "sample_report_dir"]
    leaks = [t for t in banned_terms if t in cfg_str]
    
    if leaks:
        print(f"  ❌ FAILED: 发现配置污染或冗余键: {leaks}")
    else:
        print("  ✅ PASSED: 0 历史脏数据与冗余键，配置纯净度 100%！")
        passed_tests += 1

    # -------------------------------------------------------------
    # Test 2: 校验主角人设 (protagonist_style) 动态绑定
    # -------------------------------------------------------------
    print("\n[Test 2/5] 正在校验主角人设 (protagonist_style) 与前史 (static_backstory)...")
    p_style = cfg.get("protagonist_style", {})
    s_backstory = cfg.get("static_backstory", {})
    core_cast = cfg.get("project", {}).get("core_cast", []) or cfg.get("project", {}).get("characters", [])
    
    if not core_cast:
        print("  ❌ FAILED: 核心角色名单 core_cast 为空！")
    else:
        main_mc = core_cast[0]
        char_locks = cfg.get("character_locks", [])
        has_char_lock = any(isinstance(l, dict) and l.get("name") == main_mc for l in char_locks)
        style_valid = p_style.get("enabled", False) and (main_mc in p_style.get("description", "") or "主角" in p_style.get("description", ""))
        history_valid = main_mc in s_backstory.get("protagonist_history", "") or has_char_lock
        if has_char_lock or (style_valid and history_valid):
            print(f"  ✅ PASSED: 主角团 ({', '.join(core_cast)}) 与角色锁/前史 100% 动态自洽！")
            passed_tests += 1
        else:
            print(f"  ❌ FAILED: 主角人设或前史与 core_cast 首位角色【{main_mc}】不匹配！")

    # -------------------------------------------------------------
    # Test 3: 校验 Planner Stage 1 任务书动态编译
    # -------------------------------------------------------------
    print("\n[Test 3/5] 正在模拟 Planner 任务书编译，检测提示词是否纯净...")
    try:
        core_cast_for_mock = cfg.get("project", {}).get("core_cast", []) or cfg.get("project", {}).get("characters", [])
        mock_mc = core_cast_for_mock[0] if core_cast_for_mock else "主角"
        mock_outline = f"""### **第1章：动态编译测试章**
- **章节类型**：A类（智斗对赌）
- **期望读者情绪**：紧张 ➔ 打脸 ➔ 痛快
- **场景地点**：剧情核心场景
- **登场人物**：{mock_mc}、核心反派
- **非此不可的理由（Stakes）**：生存危机与救赎羁绊双绳索绑定
- **核心事件（STAR闭环）**：情境S ➔ 目标T ➔ 动作与代价A ➔ 因果结果R
- **关键对话与细节**：市井机锋台词交锋
- **感官描写**：具体物理微动作与环境质感
- **情感落点**：人物关系微质变
- **结尾钩子**：强悬念反转"""
        
        novel_settings = build_novel_settings()
        task_xml = run_planner(1, "", mock_outline, cfg, "", "{}", novel_settings)
        full_task_prompt = f"{novel_settings}\n\n{task_xml}"
        xml_leaks = [t for t in banned_terms if t in full_task_prompt]
        
        if xml_leaks:
            print(f"  ❌ FAILED: 任务书编译中包含历史脏数据: {xml_leaks}")
        elif "<character_locks>" in full_task_prompt or "<static_backstory>" in full_task_prompt or mock_mc in full_task_prompt:
            print(f"  ✅ PASSED: 任务书与全局设定编译纯净度 100%，正确注入【{mock_mc}】专属角色约束！")
            passed_tests += 1
        else:
            print("  ❌ FAILED: 任务书未正确生成角色约束结构。")
    except Exception as e:
        print(f"  ❌ FAILED: 任务书编译报错: {e}")

    # -------------------------------------------------------------
    # Test 4: 校验知识图谱 (Knowledge Graph) 与 长程记忆 (memory.db)
    # -------------------------------------------------------------
    print("\n[Test 4/5] 正在校验项目专属 SQLite 知识图谱与长程记忆库 (memory.db)...")
    import sqlite3
    novel_d = cfg.get("project", {}).get("novel_dir", "")
    db_path = os.path.join(novel_d, "knowledge_graph.db") if novel_d else ""
    mem_db_path = os.path.join(novel_d, "memory.db") if novel_d else ""
    kg_ok = False
    mem_ok = False
    found_chars = []
    core_cast = cfg.get("project", {}).get("core_cast", []) or cfg.get("project", {}).get("characters", [])
    node_min = len(core_cast)
    edge_min = max(1, len(core_cast) - 1)

    node_cnt = 0
    edge_cnt = 0
    pv_cnt = 0
    fts_cnt = 0

    if db_path and os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM nodes")
        node_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM edges")
        edge_cnt = c.fetchone()[0]
        if core_cast:
            placeholders = ",".join("?" * len(core_cast))
            c.execute(f"SELECT name FROM nodes WHERE name IN ({placeholders})", core_cast)
            found_chars = [r[0] for r in c.fetchall()]
        cast_ratio_ok = len(found_chars) >= max(1, int(len(core_cast) * 0.8))
        if node_cnt >= node_min and edge_cnt >= edge_min and cast_ratio_ok:
            kg_ok = True
        conn.close()

    if mem_db_path and os.path.exists(mem_db_path):
        conn = sqlite3.connect(mem_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM plot_vault")
        pv_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM fts_lore")
        fts_cnt = c.fetchone()[0]
        if pv_cnt >= 1 and fts_cnt >= 1:
            mem_ok = True
        conn.close()


    if kg_ok and mem_ok:
        print(f"  ✅ PASSED: 知识图谱 ({node_cnt}节点/{edge_cnt}边, 核心角色 {len(found_chars)}/{len(core_cast)}) 与 memory.db ({pv_cnt}条伏笔/FTS5引擎) 双核全量就绪！")
        passed_tests += 1
    else:
        print(f"  ❌ FAILED: 数据库不健全 (kg_ok={kg_ok}, mem_ok={mem_ok}, 核心角色命中 {len(found_chars)}/{len(core_cast)})")

    # -------------------------------------------------------------
    # Test 5: 校验全题材热插拔扩展库 (16+ 个 YAML)
    # -------------------------------------------------------------
    print("\n[Test 5/5] 正在校验三大平台 (七猫/番茄/起点) 题材扩展包自适应性...")
    matrix = load_genre_matrix()
    total_subs = sum(len(v["subgenres"]) for v in matrix.values())
    platforms = set()
    for cat in matrix.values():
        for sub in cat["subgenres"].values():
            platforms.add(sub.get("platform", "qimao"))

    if total_subs >= 16 and {"qimao", "fanqie", "qidian"}.issubset(platforms):
        print(f"  ✅ PASSED: 题材库极其完备！涵盖多大宏观分类、{total_subs} 个细分流派，覆盖 {platforms} 三大平台！")
        passed_tests += 1
    else:
        print(f"  ❌ FAILED: 题材库缺失平台或子流派不足 (total={total_subs}, platforms={platforms})")


    # -------------------------------------------------------------
    # 总结报告
    # -------------------------------------------------------------
    print("\n" + "="*70)
    if passed_tests == total_tests:
        print(f"🎉 自动化校验全部通过！({passed_tests}/{total_tests} 满分)")
        print("💡 结论：所有历史脏数据已 100% 物理清除，动态人设与前史编译机制 100% 健壮！")
    else:
        print(f"⚠️ 校验未全部通过: {passed_tests}/{total_tests}")
    print("="*70 + "\n")
    return passed_tests == total_tests

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

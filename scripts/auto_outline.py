#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大纲与图谱一体化织网母机 - CLI 调度入口 (v22.0 Modular Outline Engine)
包含：
1. JIT 滑动细纲调度入口 (chapters 命令)
2. 全书总纲生成入口 (master 命令)
3. 细纲质检与 Linter (lint 命令)
4. 多项目向导与切换 (wizard / switch / projects 命令)
架构：业务逻辑已垂直解耦下沉至 outline/ 模块包，保持极简高效。
"""

import os
import sys
import re
import yaml
import time

from openai import OpenAI

from pipeline.guards import validate_and_heal_core_triplet, post_chapter_triplet_audit_and_heal
from outline.cli_wizard import (
    create_new_project_dir,
    list_projects,
    switch_project,
    rotate_backup_files
)
from outline.master_generator import (
    load_genre_matrix,
    generate_master_outline as _generate_master_outline,
    safe_patch_config_from_outline
)
from outline.chapter_generator import (
    get_volume_info,
    generate_chapter_outlines as _generate_chapter_outlines,
    merge_chapter_outlines_deduplicated
)
from outline.block_planner import (
    generate_volume_blocks,
    load_active_block_context
)
from outline.narrative_linter import (
    lint_chapter_outlines,
    deep_narrative_lint
)
from outline.kg_weaver import (
    init_kg_from_master_outline,
    weave_outlines_into_graph_v5
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
from pipeline.utils import load_active_config, get_active_project_dir, LogMemoryBuffer

class _LazyOpenAIProxy:
    """OpenAI 客户端惰性代理，避免在模块 import 时即刻创建底层网络客户端连接"""
    def __init__(self, script_dir: str):
        self._script_dir = script_dir
        self._client = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            c = load_active_config(script_dir=self._script_dir)
            api_base = os.getenv("OPENAI_BASE_URL") or c.get("api", {}).get("base_url", "http://127.0.0.1:19528/v1")
            api_key = os.getenv("OPENAI_API_KEY") or c.get("api", {}).get("api_key", "dfdf")
            api_timeout = int(c.get("api", {}).get("timeout", 300))
            self._client = OpenAI(base_url=api_base, api_key=api_key, timeout=api_timeout)
        return self._client

    def reset(self):
        self._client = None

    def __getattr__(self, name: str):
        return getattr(self._get_client(), name)

CLIENT = _LazyOpenAIProxy(SCRIPT_DIR)

def get_client(cfg=None) -> OpenAI:
    """获取或按需创建活动 OpenAI 客户端"""
    if cfg is not None:
        api_base = os.getenv("OPENAI_BASE_URL") or cfg.get("api", {}).get("base_url", "http://127.0.0.1:19528/v1")
        api_key = os.getenv("OPENAI_API_KEY") or cfg.get("api", {}).get("api_key", "dfdf")
        api_timeout = int(cfg.get("api", {}).get("timeout", 300))
        return OpenAI(base_url=api_base, api_key=api_key, timeout=api_timeout)
    return CLIENT._get_client()

def get_cfg(reload: bool = False):
    global CFG
    if reload or not CFG:
        refresh_runtime_config()
    return CFG

def refresh_runtime_config():
    """按需重新对齐当前活动项目的配置与全局参数"""
    global CFG, NOVEL_DIR, OUTLINE_DIR, MASTER_OUTLINE, API_TIMEOUT, PLANNER_MODEL
    CFG = load_active_config(script_dir=SCRIPT_DIR)
    NOVEL_DIR = os.path.abspath(CFG.get("project", {}).get("novel_dir", ""))
    OUTLINE_DIR = os.path.abspath(CFG.get("project", {}).get("outline_dir", NOVEL_DIR))
    MASTER_OUTLINE = os.path.abspath(CFG.get("project", {}).get("master_outline", os.path.join(OUTLINE_DIR, "大纲.md")))
    API_TIMEOUT = int(CFG.get("api", {}).get("timeout", 300))
    PLANNER_MODEL = CFG.get("models", {}).get("planner", {}).get("name", "gemini-3.7-flash-tiered")

CFG = {}
refresh_runtime_config()

def get_current_log_path() -> str:
    """动态定位当前有效的小说日志路径"""
    n_dir = get_active_project_dir(script_dir=SCRIPT_DIR)
    if n_dir and os.path.exists(n_dir):
        return os.path.join(n_dir, "日志.log")
    return ""

def log(msg: str, level: str = "INFO"):
    """小说项目工作区唯一日志落盘 (带结构化 INFO / WARN / ERROR 级别与内存启动缓冲)"""
    ts = time.strftime("%H:%M:%S")
    # 智能推导日志级别
    if any(k in msg for k in ["[WARN]", "⚠️", "未通过", "熔断", "警告", "[❌]"]):
        level = "WARN"
    elif any(k in msg for k in ["[ERROR]", "FATAL", "严重", "失败", "损坏", "崩溃"]):
        level = "ERROR"

    clean_msg = re.sub(r"^\[(INFO|WARN|ERROR)\]\s*", "", msg).strip()

    print(f"[{ts}] [{level}] {clean_msg}", flush=True)
    full_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {clean_msg}\n"
    log_path = get_current_log_path()
    if log_path:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(full_entry)
        except Exception:
            pass
    else:
        # 项目尚未建立物理目录时，推入内存暂存区
        LogMemoryBuffer.push(clean_msg, level=level)



# 代理兼容函数
def generate_master_outline(genre_prompt: str, target_words: int = 300000, output_path: str = "") -> str:
    out_p = output_path or MASTER_OUTLINE
    return _generate_master_outline(genre_prompt, target_words, CLIENT, PLANNER_MODEL, CFG, out_p, log_func=log)

def generate_chapter_outlines(start_ch: int, end_ch: int, volume_num: int = 1, master_outline_path: str = "", genre_directives: str = "", total_chapters_book: int = 125) -> str:
    m_p = master_outline_path or MASTER_OUTLINE
    return _generate_chapter_outlines(start_ch, end_ch, volume_num, CLIENT, PLANNER_MODEL, CFG, m_p, genre_directives, total_chapters_book, log_func=log)

def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("大纲与图谱一体化织网母机 (v22.0 Modular Engine)")
        print("=" * 60)
        print("使用说明:")
        print("  1. 生成章节细纲: python3 auto_outline.py chapters <start_ch> <end_ch> [volume_num] [total_ch]")
        print("  2. 生成全书总纲: python3 auto_outline.py master <genre_prompt> [target_words]")
        print("  3. 细纲质检扫描: python3 auto_outline.py lint")
        print("  4. 切换项目目录: python3 auto_outline.py switch <project_dir>")
        print("  5. 列出所有项目: python3 auto_outline.py projects")
        print("=" * 60)
        return

    cmd = sys.argv[1].lower()

    if cmd == "block":
        validate_and_heal_core_triplet(NOVEL_DIR, script_dir=SCRIPT_DIR, log_func=log)
        vol_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        tw = CFG.get("project", {}).get("target_words", 2700000)
        target_ch_words = CFG.get("quality", {}).get("target_chinese_chars", 2400)
        total_ch = max(50, tw // target_ch_words)
        vol_num_calc, start_ch, end_ch = get_volume_info((vol_num - 1) * 50 + 1, total_ch, tw)
        
        master_md = os.path.join(NOVEL_DIR, "大纲.md")
        master_text = ""
        if os.path.exists(master_md):
            with open(master_md, "r", encoding="utf-8") as mf:
                master_text = mf.read()

        out_block_path = os.path.join(OUTLINE_DIR, f"第{vol_num}卷_块级施工图.md")
        model_name = CFG.get("models", {}).get("planner", {}).get("name", "gemini-3.7-flash-tiered")
        res_block = generate_volume_blocks(
            vol_num, start_ch, end_ch, master_text, tw, CLIENT, model_name, CFG, output_path=out_block_path, log_func=log
        )
        # 0ms 在线块施工图质检
        try:
            from outline.narrative_linter import lint_block_blueprint
            blk_lint = lint_block_blueprint(res_block)
            if not blk_lint.get("passed", True):
                for fi in blk_lint.get("fatal_issues", []):
                    log(f"[Auto-Outline] ⚠️ 块施工图违规: {fi}", level="WARN")
            else:
                log(f"[Auto-Outline] ✅ 块施工图 0ms 质检通过 (得分: {blk_lint.get('score', 100)})")
        except Exception:
            pass
        post_chapter_triplet_audit_and_heal(NOVEL_DIR, end_ch, script_dir=SCRIPT_DIR, log_func=log)

    elif cmd == "chapters":
        validate_and_heal_core_triplet(NOVEL_DIR, script_dir=SCRIPT_DIR, log_func=log)
        start_ch = int(sys.argv[2])
        end_ch = int(sys.argv[3])
        vol_num = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        tw = CFG.get("project", {}).get("target_words", 2700000)
        target_ch_words = CFG.get("quality", {}).get("target_chinese_chars", 2400)
        total_ch = int(sys.argv[5]) if len(sys.argv) > 5 else max(50, tw // target_ch_words)

        # 若中观块级施工图尚未生成，自动触发中观块级规划生成
        block_file = os.path.join(OUTLINE_DIR, f"第{vol_num}卷_块级施工图.md")
        if not os.path.exists(block_file):
            _, v_start, v_end = get_volume_info(start_ch, total_ch, tw)
            master_md = os.path.join(NOVEL_DIR, "大纲.md")
            master_text = open(master_md, "r", encoding="utf-8").read() if os.path.exists(master_md) else ""
            model_name = CFG.get("models", {}).get("planner", {}).get("name", "gemini-3.7-flash-tiered")
            generate_volume_blocks(
                vol_num, v_start, v_end, master_text, tw, CLIENT, model_name, CFG, output_path=block_file, log_func=log
            )

        res = generate_chapter_outlines(start_ch, end_ch, vol_num, total_chapters_book=total_ch)
        
        # 0ms 在线细纲质检与红线拦截
        try:
            lint_report = lint_chapter_outlines(res)
            if not lint_report.get("passed", True):
                fatal_list = lint_report.get("fatal_issues", [])
                log(f"[Auto-Outline] ⚠️ 细纲生成触发叙事红线拦截 ({len(fatal_list)} 项违规):", level="WARN")
                for fit in fatal_list:
                    log(f"  - {fit}", level="WARN")
            else:
                log(f"[Auto-Outline] ✅ 细纲 0ms 叙事质检通过 (得分: {lint_report.get('score', 100)})")
        except Exception:
            pass

        # 将生成的细纲原子级去重合并到分卷细纲文件
        target_file = os.path.join(OUTLINE_DIR, f"第{vol_num}卷_章节细纲.md")
        merge_chapter_outlines_deduplicated(target_file, res)
        log(f"[Auto-Outline] ✅ 第 {start_ch} ~ {end_ch} 章细纲已去重合并至: {target_file}")

        # 将细纲中的实体与物象状态增量织入知识图谱与状态文件
        try:
            from outline.kg_weaver import weave_outlines_into_graph_v5, sync_outlines_with_state
            weave_outlines_into_graph_v5(OUTLINE_DIR, NOVEL_DIR, log_func=log)
            state_p = os.path.join(NOVEL_DIR, "state_file.json")
            sync_outlines_with_state(OUTLINE_DIR, state_p, log_func=log)
        except Exception:
            pass

        # 后置三要素强校验与即时自愈审计
        post_chapter_triplet_audit_and_heal(NOVEL_DIR, end_ch, script_dir=SCRIPT_DIR, log_func=log)

    elif cmd == "master":
        genre_text = sys.argv[2] if len(sys.argv) > 2 else "玄幻爽文逆袭"
        target_w = int(sys.argv[3]) if len(sys.argv) > 3 else 300000
        root_base = CFG.get("project", {}).get("root_dir", "~/Desktop/生成的小说")
        root_base = os.path.abspath(os.path.expanduser(root_base))
        target_ch_words = CFG.get("quality", {}).get("target_chinese_chars", 2400)
        new_proj_dir = create_new_project_dir(root_base, target_w, target_ch_words=target_ch_words)
        out_master_path = os.path.join(new_proj_dir, "大纲.md")
        try:
            generate_master_outline(genre_text, target_w, output_path=out_master_path)
            # 刷新活动配置与日志刷盘
            new_log = os.path.join(new_proj_dir, "日志.log")
            if new_log:
                flushed = LogMemoryBuffer.flush_to_file(new_log)
                if flushed > 0:
                    log(f"[Bootstrap] 📥 已自动将前置启动日志 ({flushed} 条) 刷盘至新书日志: {os.path.basename(new_log)}")
            # 后置三要素强校验与即时自愈审计
            post_chapter_triplet_audit_and_heal(new_proj_dir, 0, script_dir=SCRIPT_DIR, log_func=log)
        except Exception as e:
            log(f"[Auto-Outline] [ERROR] 构思全书总纲失败: {e}", level="ERROR")
            sys.exit(1)



    elif cmd == "lint":
        res = deep_narrative_lint(OUTLINE_DIR)
        print(yaml.dump(res, allow_unicode=True))

    elif cmd == "projects":
        root_base = CFG.get("project", {}).get("root_dir", "~/Desktop/生成的小说")
        root_base = os.path.abspath(os.path.expanduser(root_base))
        projs = list_projects(root_base)
        print("📂 当前已发现的小说项目列表:")
        for p in projs:
            cur_marker = " (当前绑定)" if p == NOVEL_DIR else ""
            print(f"  - {os.path.basename(p)}{cur_marker}")

    elif cmd == "switch" and len(sys.argv) > 2:
        switch_project(sys.argv[2], log_func=log)


if __name__ == "__main__":
    main()

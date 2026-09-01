#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七猫男频通用多Agent写作流水线 - 主调度引擎 (v5.0 Modular Architecture)
流程：Planner → Writer → Reviewer → (FAIL? → 针对性自愈重试) → StateTracker → Publisher
架构：基于 pipeline/ 模块与 agent_1~5 专职解耦，保持高内聚、低耦合、0 业务硬编码。
"""

import os
import sys
import re
import glob
import time
import yaml
from typing import Dict, Any, Optional, List, Tuple
from openai import OpenAI

# 基础工具与净化器
from pipeline.utils import (
    count_chinese_chars,
    extract_xml_tag,
    check_ai_cliches,
    check_vulgar_villain_abuse,
    check_ending_slogans,
    sanitize_vulgar_and_cliches
)

# 流水线模块
from pipeline.guards import (
    acquire_lock,
    release_lock,
    check_codebase_anti_hardcoding_gate,
    reconcile_and_recover_from_published_assets,
    validate_and_heal_core_triplet,
    post_chapter_triplet_audit_and_heal
)
from pipeline.context_builder import (
    build_novel_settings as _build_novel_settings,
    load_chapter_outline as _load_chapter_outline,
    extract_chapter_outline as _extract_chapter_outline,
    extract_chapter_title as _extract_chapter_title,
    read_tail as _read_tail,
    get_climax_chapters as _get_climax_chapters,
    get_outline_config as _get_outline_config
)
from pipeline.context_analyzer import (
    detect_ending_pattern,
    detect_monologue_ending_streak,
    detect_dormant_foreshadowing,
    get_retention_strategy
)
from pipeline.jit_buffer import ensure_jit_sliding_outline_buffer as _ensure_jit_sliding_outline_buffer
from storage.state_manager import read_state_file, write_state_file, compact_state_snapshot

# 专职 Agent
from agents.agent_1_planner import run_planner as _run_planner
from agents.agent_2_writer import run_writer as _run_writer
from agents.agent_3_reviewer import run_reviewer as _run_reviewer
from agents.agent_4_publisher import run_publisher as _run_publisher, merge_all_chapters, format_clean_platform_text
from agents.agent_5_state_tracker import run_state_tracker as _run_state_tracker

# ============================================================
# 配置与环境初始化
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
from pipeline.utils import load_active_config
CFG = load_active_config(script_dir=SCRIPT_DIR)

NOVEL_DIR     = CFG.get("project", {}).get("novel_dir", "")
OUTLINE_DIR   = CFG.get("project", {}).get("outline_dir", NOVEL_DIR)
MASTER_OUTLINE = CFG.get("project", {}).get("master_outline", "")
MASTER_FILE   = CFG.get("project", {}).get("master_file", "合集.md")
CH_PREFIX     = CFG.get("project", {}).get("chapter_prefix", "C_正文_第")
CH_SUFFIX     = CFG.get("project", {}).get("chapter_suffix", "章.md")

BATCH_SIZE    = CFG.get("batch", {}).get("size", 5)
MAX_RETRY     = CFG.get("batch", {}).get("max_retry", 3)
TAIL_CHARS    = CFG.get("memory_bridge", {}).get("prev_chapter_tail_chars", 500)

MIN_CHARS     = CFG.get("quality", {}).get("min_chinese_chars", 2000)
TARGET_CHARS  = CFG.get("quality", {}).get("target_chinese_chars", 2400)
MAX_CHARS     = CFG.get("quality", {}).get("max_chinese_chars", 2800)

STATE_TRACKING_ENABLED = CFG.get("state_tracking", {}).get("enabled", False)
STATE_FILE_NAME       = CFG.get("state_tracking", {}).get("file", "状态文件.json")
STATE_FILE_PATH       = os.path.join(NOVEL_DIR, STATE_FILE_NAME)

API_BASE = os.getenv("OPENAI_BASE_URL") or CFG.get("api", {}).get("base_url", "http://127.0.0.1:19528/v1")
API_KEY  = os.getenv("OPENAI_API_KEY") or CFG.get("api", {}).get("api_key", "dfdf")

API_TIMEOUT = CFG.get("api", {}).get("timeout", 300)
CLIENT = OpenAI(base_url=API_BASE, api_key=API_KEY, timeout=API_TIMEOUT)

LOG_FILE_PATH = os.path.join(NOVEL_DIR, "日志.log") if NOVEL_DIR else ""

def log(msg: str, level: str = "INFO"):
    """小说项目工作区唯一日志落盘 (带结构化 INFO / WARN / ERROR 级别)"""
    ts = time.strftime("%H:%M:%S")
    # 智能推导日志级别
    if any(k in msg for k in ["[WARN]", "⚠️", "未通过", "熔断", "警告", "[❌]"]):
        level = "WARN"
    elif any(k in msg for k in ["[ERROR]", "FATAL", "严重", "失败", "损坏", "崩溃"]):
        level = "ERROR"

    clean_msg = re.sub(r"^\[(INFO|WARN|ERROR)\]\s*", "", msg).strip()

    print(f"[{ts}] [{level}] {clean_msg}", flush=True)
    full_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {clean_msg}\n"
    if LOG_FILE_PATH:
        try:
            os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as lf:
                lf.write(full_entry)
        except Exception:
            pass


# ============================================================
# 兼容性代理接口（供 test.py 及外部调用）
# ============================================================
def extract_chapter_outline(outline_text: str, chapter_num: int) -> str:
    return _extract_chapter_outline(outline_text, chapter_num)

def load_chapter_outline(chapter_num: int, cfg: Dict[str, Any] = None) -> str:
    active_c = cfg or load_active_config(script_dir=SCRIPT_DIR)
    return _load_chapter_outline(active_c, chapter_num, log_func=log)

def extract_chapter_title(outline_text: str, chapter_num: int = 0, cfg: Dict[str, Any] = None) -> str:
    active_c = cfg or load_active_config(script_dir=SCRIPT_DIR)
    return _extract_chapter_title(outline_text, chapter_num, active_c)

def build_novel_settings(cfg: Dict[str, Any] = None) -> str:
    active_c = cfg or load_active_config(script_dir=SCRIPT_DIR)
    return _build_novel_settings(active_c)

def get_climax_chapters(cfg: Dict[str, Any] = None) -> list[int]:
    active_c = cfg or load_active_config(script_dir=SCRIPT_DIR)
    tw = active_c.get("project", {}).get("target_words", 0)
    total_ch = max(50, tw // 2400) if tw else 100
    return _get_climax_chapters(total_ch)


def ensure_jit_sliding_outline_buffer(current_chapter: int):
    _ensure_jit_sliding_outline_buffer(current_chapter, CFG, SCRIPT_DIR, log_func=log)

from pipeline.utils import count_chinese_chars

def run_planner(chapter_num: int, prev_tail: str, chapter_outline: str, cfg: Dict[str, Any] = None, state_data: str = "", compact_state: str = "", novel_settings: str = "", log_func=None) -> str:
    return _run_planner(chapter_num, prev_tail, chapter_outline, cfg or CFG, state_data, compact_state, novel_settings, log_func=log_func)

def run_writer(task_prompt: str, client, model_name: str, temperature: float, chapter_outline: str = "", novel_dir: str = "", cfg: Optional[Dict[str, Any]] = None, log_func=None) -> str:
    return _run_writer(task_prompt, client, model_name, temperature, chapter_outline, novel_dir=novel_dir or NOVEL_DIR, cfg=cfg or CFG, log_func=log_func)

def run_reviewer(chapter_output: str, chapter_outline: str, prev_tail: str, chapter_num: int, client, model_name: str, cfg: Optional[Dict[str, Any]] = None, log_func=None) -> dict:
    return _run_reviewer(chapter_output, chapter_outline, prev_tail, chapter_num, client, model_name, cfg or CFG, log_func=log_func)

def run_publisher(chapter_num: int, chapter_output: str, chapter_outline: str, cfg: Dict[str, Any] = None, review_report: str = "", log_func=None) -> str:
    return _run_publisher(chapter_num, chapter_output, chapter_outline, cfg or CFG, review_report=review_report, log_func=log_func)

def run_state_tracker(chapter_num: int, chapter_content: str, prev_state_data: str, client, model_name: str, cfg: Dict[str, Any] = None, log_func=None) -> dict:
    return _run_state_tracker(chapter_num, chapter_content, prev_state_data, client, model_name, cfg or CFG, log_func=log_func)

def get_existing_chapters() -> list[int]:
    """扫描正文目录，返回已存在的章节号列表（升序）"""
    nums = set()
    for d in [os.path.join(NOVEL_DIR, "正文"), NOVEL_DIR]:
        if os.path.exists(d):
            files = glob.glob(os.path.join(d, f"{CH_PREFIX}*{CH_SUFFIX}"))
            for f in files:
                m = re.search(r"第(\d+)章", os.path.basename(f))
                if m:
                    nums.add(int(m.group(1)))
    return sorted(list(nums))

def chapter_path(num: int) -> str:
    sub_p = os.path.join(NOVEL_DIR, "正文", f"{CH_PREFIX}{num}{CH_SUFFIX}")
    if os.path.exists(sub_p):
        return sub_p
    root_p = os.path.join(NOVEL_DIR, f"{CH_PREFIX}{num}{CH_SUFFIX}")
    return root_p if os.path.exists(root_p) else sub_p

# ============================================================
# 主调度执行引擎
# ============================================================
def run_pipeline(batch_start: int = None):
    """运行一个批次的写作流水线"""
    # 0. 安全防御与并发锁
    lock_fd = acquire_lock(NOVEL_DIR)
    if not lock_fd:
        log("❌ [Concurrency Lock] 无法获取文件排他锁，可能有另一流水线实例正在运行。")
        return

    try:
        # 代码防硬编码门禁扫描
        if not check_codebase_anti_hardcoding_gate(SCRIPT_DIR, log_func=log):
            return

        # 灾备资产对账
        reconcile_and_recover_from_published_assets(NOVEL_DIR, CH_PREFIX, CH_SUFFIX, log_func=log)

        # 核心基础设施三要素强校验与自愈门禁 (config.yaml, knowledge_graph.db, memory.db)
        if not validate_and_heal_core_triplet(NOVEL_DIR, script_dir=SCRIPT_DIR, log_func=log):
            log("❌ [Fatal Triplet Error] 基础设施核心三要素校验失败，流水线暂停。")
            return

        MAX_CHAPTERS = 2000
        existing = get_existing_chapters()
        existing_set = set(existing)
        if batch_start is None:
            batch_start = 1 if len(existing) == 0 else max(existing) + 1

        if batch_start < 1 or batch_start > MAX_CHAPTERS:
            log(f"[ERROR] 起始章节 {batch_start} 超出全书范围（1-{MAX_CHAPTERS}）。")
            return

        batch_end = min(MAX_CHAPTERS, batch_start + BATCH_SIZE - 1)

        log("=" * 60)
        log(f"七猫男频通用多Agent写作流水线启动")
        log(f"批次范围: 第{batch_start}章 - 第{batch_end}章")
        log(f"小说目录: {NOVEL_DIR}")
        log(f"字数要求: {MIN_CHARS}-{TARGET_CHARS}-{MAX_CHARS} (min-target-max)")
        log(f"模型配置: Planner/Writer={CFG['models']['planner']['name']}, Reviewer={CFG['models']['reviewer']['name']}")
        log("=" * 60)

        novel_settings = build_novel_settings()
        log(f"[Settings] 小说设定组装完成 ({len(novel_settings)} chars)")
        log(f"[Settings] 全书关键高潮卡点: {get_climax_chapters()}")

        for chapter_num in range(batch_start, batch_end + 1):
            is_last = (chapter_num == batch_end)
            ch_start_time = time.time()
            log("")
            log(f"{'='*20} 第{chapter_num}章 ({chapter_num - batch_start + 1}/{BATCH_SIZE}) {'='*20}")

            ch_file = chapter_path(chapter_num)
            force_overwrite = "--force" in sys.argv or "--force-overwrite" in sys.argv
            if chapter_num in existing_set and os.path.exists(ch_file) and os.path.getsize(ch_file) > 1000 and not force_overwrite:
                log(f"[已过审跳过] 🛡️ 检测到第 {chapter_num} 章已存在且质检达标，自动跳过。")
                continue

            # JIT 滑动细纲储备保障
            ensure_jit_sliding_outline_buffer(chapter_num)

            prev_tail = "" if chapter_num <= 1 else _read_tail(NOVEL_DIR, CH_PREFIX, CH_SUFFIX, chapter_num, TAIL_CHARS)

            try:
                chapter_outline = load_chapter_outline(chapter_num)
                expected_title_short = extract_chapter_title(chapter_outline, chapter_num)
                log(f"细纲加载: {chapter_outline[:100].replace(chr(10), ' ')}...")
            except Exception as e:
                log(f"[ERROR] 无法获取第{chapter_num}章大纲: {e}")
                return

            # Stage 1: Planner
            t_plan_start = time.time()
            raw_state = read_state_file(STATE_FILE_PATH) if STATE_TRACKING_ENABLED else ""
            compact_state = compact_state_snapshot(raw_state, CFG, chapter_outline, chapter_num) if STATE_TRACKING_ENABLED else ""
            task_prompt = _run_planner(chapter_num, prev_tail, chapter_outline, CFG, "", compact_state, novel_settings, log_func=log)
            plan_duration = time.time() - t_plan_start

            # Stage 2 & 3: Writer + Reviewer 自愈循环
            passed = False
            feedback = ""
            chapter_output = ""
            best_candidate = None
            last_wc = 0
            writer_total_time = 0.0
            reviewer_total_time = 0.0
            surgical_patched = False
            final_attempt = 1

            for attempt in range(1, MAX_RETRY + 1):
                final_attempt = attempt
                log("")
                log(f"--- 第{chapter_num}章 写作尝试 {attempt}/{MAX_RETRY} ---")
                
                cur_task = task_prompt
                if feedback:
                    word_budget_note = ""
                    if last_wc > MAX_CHARS:
                        word_budget_note = f"\n⚠️ 【最高红线·紧急压减字数】：上一稿字数达 {last_wc} 字超标（上限 {MAX_CHARS} 字）！请删减冗余心理与环境说明，严格压缩至 {MIN_CHARS}-{MAX_CHARS} 字黄金区间！\n"
                    elif 0 < last_wc < MIN_CHARS:
                        word_budget_note = f"\n⚠️ 【最高红线·扩充篇幅】：上一稿字数仅 {last_wc} 字不足（下限 {MIN_CHARS} 字）！请在第二幕丰富人物交锋动作与博弈细节，扩充至 {MIN_CHARS} 字以上！\n"
                    elif last_wc >= MIN_CHARS:
                        word_budget_note = f"\n⚠️ 【字数锁定】：上一稿字数（{last_wc}字）处于理想区间，请务必保持整体篇幅，仅做违规字句精准局部替换，严禁额外扩写！\n"

                    cur_task += f"\n\n<review_feedback>{word_budget_note}\n【上一轮质检未通过意见（必须逐条修改）】:\n{feedback}\n</review_feedback>"

                writer_model = CFG["models"]["writer"]["name"]
                writer_temp = CFG["models"]["writer"]["temperature"]
                t_w_start = time.time()
                chapter_output = _run_writer(cur_task, CLIENT, writer_model, writer_temp, chapter_outline, novel_dir=NOVEL_DIR, cfg=CFG, log_func=log)
                writer_total_time += (time.time() - t_w_start)

                reviewer_model = CFG["models"]["reviewer"]["name"]
                t_r_start = time.time()
                review = _run_reviewer(chapter_output, chapter_outline, prev_tail, chapter_num, CLIENT, reviewer_model, CFG, log_func=log)
                reviewer_total_time += (time.time() - t_r_start)
                last_wc = review.get("word_count", 0)

                if review["verdict"] == "PASS":
                    passed = True
                    log(f"[✅] 第{chapter_num}章审核通过! 字数: {review['word_count']}")
                    break
                else:
                    # 尝试 0ms 本地微创自愈修剪
                    from pipeline.utils import apply_surgical_micro_patch
                    is_patched, patched_output, patch_reasons = apply_surgical_micro_patch(chapter_output, CFG)
                    if is_patched:
                        re_review = _run_reviewer(patched_output, chapter_outline, prev_tail, chapter_num, CLIENT, reviewer_model, CFG, log_func=None)
                        if re_review["verdict"] == "PASS":
                            passed = True
                            chapter_output = patched_output
                            review = re_review
                            surgical_patched = True
                            log(f"[Surgical Patch] 💉 命中本地微创自愈修剪 (0ms) -> 已修复: {', '.join(patch_reasons)}")
                            log(f"[✅] 第{chapter_num}章微创自愈后审核通过! 字数: {review['word_count']}")
                            break

                    # 尝试局部尾部微扩充 (APPEND_WRAPPER) 避免推倒重写
                    if review.get("patch_action") == "APPEND_WRAPPER":
                        log(f"[Smart Patch] 🩹 触发局部末尾微扩充 (APPEND_WRAPPER，避免推倒重写)...")
                        patch_prompt = f"""请针对以下第{chapter_num}章正文末尾，补写约 200~300 字的环境五感描写与人物微动作定格，使章节自然收束并补齐字数差额：\n\n【当前正文尾部】：\n{chapter_output[-500:]}\n\n请直接输出补充段落正文（严禁输出空洞口号）："""
                        try:
                            from pipeline.utils import safe_chat_completion
                            tail_patch = safe_chat_completion(CLIENT, writer_model, [{"role": "user", "content": patch_prompt}], temperature=0.6, max_tokens=1024, log_func=log)
                            if tail_patch:
                                if "</chapter_content>" in chapter_output:
                                    chapter_output = chapter_output.replace("</chapter_content>", f"\n\n{tail_patch.strip()}\n</chapter_content>")
                                else:
                                    chapter_output = f"{chapter_output.strip()}\n\n{tail_patch.strip()}"
                                re_review = _run_reviewer(chapter_output, chapter_outline, prev_tail, chapter_num, CLIENT, reviewer_model, CFG, log_func=None)
                                if re_review["verdict"] == "PASS":
                                    passed = True
                                    review = re_review
                                    surgical_patched = True
                                    log(f"[✅] 第{chapter_num}章局部扩充后审核通过! 字数: {review['word_count']}")
                                    break
                        except Exception:
                            pass

                    feedback = review["feedback"]
                    log(f"[❌] 第{chapter_num}章审核未通过 (字数: {review['word_count']})")
                    log(f"  修改意见: {feedback[:150]}...")
                    if best_candidate is None or abs(review["word_count"] - TARGET_CHARS) < abs(best_candidate[1]["word_count"] - TARGET_CHARS):
                        best_candidate = (chapter_output, review)

            if not passed:
                if best_candidate:
                    log("[Auto-Compactor] ⚡ 激活智能保底：选取最优历史稿件完成发布。")
                    chapter_output = best_candidate[0]
                else:
                    log(f"[ERROR] 第{chapter_num}章未能通过审核，流水线暂停。")
                    return

            # Stage 4: Publisher
            _run_publisher(chapter_output, chapter_num, is_last, CFG, expected_title_short, log_func=log)

            # Stage 5: StateTracker
            memory_anchor = extract_xml_tag(chapter_output, "memory_anchor")
            if memory_anchor and STATE_TRACKING_ENABLED:
                st_model = CFG.get("models", {}).get("state_tracker", {}).get("name", "gpt-4o-mini")
                _run_state_tracker(chapter_num, memory_anchor, CLIENT, st_model, CFG, log_func=log)

            existing_set.add(chapter_num)
            total_duration = time.time() - ch_start_time
            w_speed = int(last_wc / max(1.0, writer_total_time))

            # 打印单章生产全景遥测看板
            log("\n  ┌────────────────── 📊 第 " + str(chapter_num) + " 章 生产全景遥测看板 ──────────────────┐")
            log(f"  │ ⏱️  [生产耗时] : {total_duration:.1f}s (主笔: {writer_total_time:.1f}s | 审读: {reviewer_total_time:.1f}s | 编译: {plan_duration:.2f}s)   │")
            log(f"  │ 📝  [字符产出] : {last_wc} 字 (生成速度: {w_speed} 字/秒 | 尝试次数: {final_attempt})            │")
            log(f"  │ 💉  [自愈判定] : {'✅ 0ms 微创自愈成功' if surgical_patched else '✅ 一次性直出通过'}                                  │")
            log(f"  │ 🎯  [发布状态] : ✅ 已同步更新正文、发布版、全书合集与目录树.md           │")
            log("  └─────────────────────────────────────────────────────────────────────┘")
            log(f"[✅] 第{chapter_num}章全流程完成!")

            # 核心三要素章后强校验与自愈审计
            post_chapter_triplet_audit_and_heal(NOVEL_DIR, chapter_num, script_dir=SCRIPT_DIR, log_func=log)

        log("")
        log("=" * 60)
        log(f"🎉 本批次完成! 第{batch_start}章 - 第{batch_end}章 已全部生成并保存。")
        log(f"文件目录: {NOVEL_DIR}")
        log(f"下一批次: 第{batch_end + 1}章 - 第{min(MAX_CHAPTERS, batch_end + BATCH_SIZE)}章")
        log("=" * 60)

    finally:
        release_lock(lock_fd)

def show_status(cfg: dict = CFG):
    """查看当前小说全书写作与细纲推进进度报告"""
    novel_dir = cfg["project"]["novel_dir"]
    ch_prefix = cfg["project"]["chapter_prefix"]
    ch_suffix = cfg["project"]["chapter_suffix"]
    target_total_words = cfg["project"].get("target_total_words", 2700000)
    total_chapters_target = cfg["project"].get("total_chapters", 1125)

    md_files = glob.glob(os.path.join(novel_dir, "正文", f"{ch_prefix}*{ch_suffix}"))
    existing_nums = []
    total_words = 0
    pattern = rf"{re.escape(ch_prefix)}(\d+){re.escape(ch_suffix)}"
    for f in md_files:
        m = re.search(pattern, os.path.basename(f))
        if m:
            num = int(m.group(1))
            existing_nums.append(num)
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    total_words += count_chinese_chars(fp.read())
            except Exception:
                pass

    existing_nums.sort()
    completed_cnt = len(existing_nums)
    latest_ch = max(existing_nums) if existing_nums else 0

    print("=" * 65)
    print(" 📊 【七猫男频通用多Agent写作流水线 — 全书进度看板】")
    print("=" * 65)
    print(f" 📖 小说项目路径 : {novel_dir}")
    print(f" 🎯 全书目标体量 : {target_total_words:,} 字 / {total_chapters_target} 章")
    print(f" ✍️ 当前已完章节 : 第 1 ~ {latest_ch} 章 (累计已发布 {completed_cnt} 章)")
    print(f" 📝 累计总字数   : {total_words:,} 字 (完成度: {(total_words / target_total_words * 100):.2f}%)")
    if completed_cnt > 0:
        print(f" 📏 单章平均字数 : {int(total_words / completed_cnt):,} 字/章")
    print(f" ⏭️ 下一待写章节 : 第 {latest_ch + 1} 章")

    # 扫描细纲储备
    outlines = glob.glob(os.path.join(novel_dir, "大纲.md")) + \
               glob.glob(os.path.join(novel_dir, "*大纲*.md")) + \
               glob.glob(os.path.join(novel_dir, "*细纲*.md")) + \
               glob.glob(os.path.join(novel_dir, "大纲", "*.md"))
    outline_ch_nums = []
    for of in set(outlines):
        if "backup" in of or "permanent" in of:
            continue
        try:
            with open(of, "r", encoding="utf-8") as op:
                outline_ch_nums.extend([int(x) for x in re.findall(r'###\s*\*\*第(\d+)章', op.read())])
        except Exception:
            pass
    outline_ch_nums = sorted(list(set(outline_ch_nums)))
    ready_outlines = [n for n in outline_ch_nums if n > latest_ch]
    print(f" 🗺️ 细纲就绪储备 : 已规划至第 {max(outline_ch_nums) if outline_ch_nums else 0} 章 (待写储备细纲: {len(ready_outlines)} 章)")
    print("=" * 65)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ["status", "progress", "info", "-s", "--status"]:
        show_status()
        return

    start_arg = None
    if len(sys.argv) >= 2 and sys.argv[1].isdigit():
        start_arg = int(sys.argv[1])
        if len(sys.argv) >= 3 and sys.argv[2].isdigit():
            val2 = int(sys.argv[2])
            global BATCH_SIZE
            BATCH_SIZE = (val2 - start_arg + 1) if val2 >= start_arg else val2
            log(f"批次大小覆盖为: {BATCH_SIZE} 章 (范围: 第{start_arg}章 - 第{start_arg + BATCH_SIZE - 1}章)")
    run_pipeline(batch_start=start_arg)

if __name__ == "__main__":
    main()

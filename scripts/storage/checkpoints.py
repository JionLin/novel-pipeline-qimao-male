#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph 架构思想落地：持久化执行与时间旅行（Checkpoints & Time Travel）
支持：
  1. save_checkpoint(chapter_num, state_data, chapter_content, review_report) -> 创建不可变快照
  2. list_checkpoints() -> 列出所有历史检查点
  3. rollback_to(target_chapter, create_backup=True) -> 时光倒流至指定章节，自动对齐正文、状态与合集
  4. branch_from(source_chapter, branch_name) -> 基于指定章节创建平行剧情分支
"""

import os, sys, json, shutil, glob, re, time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from pipeline.utils import count_chinese_chars, load_active_config

import yaml
CFG = load_active_config(script_dir=SCRIPT_DIR)
NOVEL_DIR = CFG.get("project", {}).get("novel_dir", "")
CHECKPOINT_DIR = os.path.join(NOVEL_DIR, "checkpoints")

def ensure_checkpoint_dir():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

def save_checkpoint(chapter_num: int, state_data: dict, chapter_content: str, review_report: str = "", metadata: dict = None) -> str:
    """在每一章审核通过、状态更新并落盘后，自动创建原子检查点"""
    ensure_checkpoint_dir()
    cp_path = os.path.join(CHECKPOINT_DIR, f"chapter_{chapter_num:03d}")
    os.makedirs(cp_path, exist_ok=True)

    # 1. 保存状态快照
    state_file = os.path.join(cp_path, "state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f, ensure_ascii=False, indent=2)

    # 2. 保存正文快照
    chapter_file = os.path.join(cp_path, "chapter.md")
    with open(chapter_file, "w", encoding="utf-8") as f:
        f.write(chapter_content)

    # 3. 保存审查报告快照
    if review_report:
        report_file = os.path.join(cp_path, "review_report.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(review_report)

    # 4. 元数据清单
    meta = {
        "chapter_num": chapter_num,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "word_count": count_chinese_chars(chapter_content),
        "branch": "main"
    }
    if metadata:
        meta.update(metadata)

    meta_file = os.path.join(cp_path, "meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return cp_path

def list_checkpoints() -> list:
    """列出所有可用检查点"""
    ensure_checkpoint_dir()
    dirs = sorted(glob.glob(os.path.join(CHECKPOINT_DIR, "chapter_*")))
    checkpoints = []
    for d in dirs:
        meta_file = os.path.join(d, "meta.json")
        if os.path.exists(meta_file):
            try:
                meta = json.load(open(meta_file, encoding="utf-8"))
                checkpoints.append(meta)
            except Exception:
                pass
    return checkpoints

def _glob_chapter_files(base_dir: str) -> list:
    """扫描正文章节文件（兼容 正文/ 子目录与根目录两种归档方式），按章节号升序"""
    files = []
    for d in [os.path.join(base_dir, "正文"), base_dir]:
        if os.path.exists(d):
            files.extend(glob.glob(os.path.join(d, "C_正文_第*章.md")))
    return sorted(files, key=lambda x: int(re.search(r'第(\d+)章', x).group(1)) if re.search(r'第(\d+)章', x) else 0)


def rollback_to(target_chapter: int, create_backup: bool = True) -> dict:
    """
    【时间旅行核心实现】
    将流水线时光倒流回滚至 target_chapter 节点：
    1. 还原 状态文件.json 为 target_chapter 结束时的精确状态；
    2. 将 target_chapter 之后的所有章节文件归档至备份目录并移除；
    3. 重新合并更新 合集.md 至 target_chapter；
    4. 下一次启动流水线将精准从 target_chapter + 1 开始续写！
    """
    ensure_checkpoint_dir()
    target_cp = os.path.join(CHECKPOINT_DIR, f"chapter_{target_chapter:03d}")
    
    if not os.path.exists(target_cp):
        raise FileNotFoundError(f"未找到第 {target_chapter} 章的检查点 ({target_cp})！")

    state_snap = os.path.join(target_cp, "state.json")
    if not os.path.exists(state_snap):
        raise FileNotFoundError(f"检查点中缺失 state.json: {state_snap}")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(NOVEL_DIR), f"正文_时间旅行回滚备份_第{target_chapter+1}章起_{timestamp_str}")

    # 1. 查找所有 > target_chapter 的章节并归档备份（兼容 正文/ 子目录与根目录）
    all_chapters = _glob_chapter_files(NOVEL_DIR)
    
    removed_chapters = []
    for cf in all_chapters:
        m = re.search(r'第(\d+)章', cf)
        if m:
            cnum = int(m.group(1))
            if cnum > target_chapter:
                if create_backup:
                    os.makedirs(backup_dir, exist_ok=True)
                    shutil.move(cf, os.path.join(backup_dir, os.path.basename(cf)))
                    rep_file = os.path.join(NOVEL_DIR, f"第{cnum:03d}章_自检清单分析报告.md")
                    if os.path.exists(rep_file):
                        shutil.move(rep_file, os.path.join(backup_dir, os.path.basename(rep_file)))
                    # 新架构质检报告位于 checkpoints/chapter_XXX/review_report.md
                    cp_rep = os.path.join(CHECKPOINT_DIR, f"chapter_{cnum:03d}", "review_report.md")
                    if os.path.exists(cp_rep):
                        os.makedirs(os.path.join(backup_dir, f"chapter_{cnum:03d}"), exist_ok=True)
                        shutil.move(cp_rep, os.path.join(backup_dir, f"chapter_{cnum:03d}", "review_report.md"))
                else:
                    os.remove(cf)
                removed_chapters.append(cnum)

    # 2. 还原 状态文件.json
    active_state_file = os.path.join(NOVEL_DIR, "状态文件.json")
    shutil.copy2(state_snap, active_state_file)

    # 3. 重新聚合 合集.md
    from run_pipeline import merge_all_chapters
    merge_all_chapters()

    return {
        "status": "SUCCESS",
        "target_chapter": target_chapter,
        "next_chapter": target_chapter + 1,
        "removed_chapters": removed_chapters,
        "backup_dir": backup_dir if removed_chapters and create_backup else "无后续章节需备份",
        "restored_state_file": active_state_file
    }

def branch_from(source_chapter: int, branch_name: str) -> dict:
    """
    【平行世界分支创建】
    基于某一历史章节创建全新平行剧情分支（如：branch_ch30_dark_ending）
    """
    ensure_checkpoint_dir()
    src_cp = os.path.join(CHECKPOINT_DIR, f"chapter_{source_chapter:03d}")
    if not os.path.exists(src_cp):
        raise FileNotFoundError(f"未找到第 {source_chapter} 章检查点！")

    branch_novel_dir = os.path.join(os.path.dirname(NOVEL_DIR), f"正文_分支_{branch_name}")
    branch_archive_dir = os.path.join(branch_novel_dir, "正文")
    os.makedirs(branch_archive_dir, exist_ok=True)

    # 复制 1 到 source_chapter 的章节（兼容 正文/ 子目录与根目录）
    all_chapters = _glob_chapter_files(NOVEL_DIR)
    
    copied = []
    for cf in all_chapters:
        m = re.search(r'第(\d+)章', cf)
        if m and int(m.group(1)) <= source_chapter:
            shutil.copy2(cf, os.path.join(branch_archive_dir, os.path.basename(cf)))
            copied.append(int(m.group(1)))

    # 复制状态文件
    shutil.copy2(os.path.join(src_cp, "state.json"), os.path.join(branch_novel_dir, "状态文件.json"))

    return {
        "status": "SUCCESS",
        "branch_name": branch_name,
        "source_chapter": source_chapter,
        "branch_dir": branch_novel_dir,
        "copied_chapters_count": len(copied)
    }

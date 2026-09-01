# -*- coding: utf-8 -*-
"""
agent_4_publisher.py - 发布与归档 Agent (Publisher)
负责：
1. 正文确定性净化（AI 套话与低幼辱骂安全映射）
2. 标准 Markdown 归档版落盘 (正文/C_正文_第X章.md)
3. 平台直发级纯净版落盘 (正文/发布版/C_正文_第X章.txt，含全角缩进与追读预告)
4. 全书增量合集维护 (正文/合集.md 与 正文/发布版/合集.txt)
"""

import os
import re
import glob
from typing import Dict, Any, Optional
from pipeline.utils import extract_xml_tag, sanitize_vulgar_and_cliches, atomic_write
from pipeline.context_builder import load_chapter_outline, extract_chapter_title


def format_clean_platform_text(content: str) -> str:
    """格式化为网文平台直发级纯文本：去除 Markdown 标记，添加中文全角两格缩进"""
    clean_lines = []
    lines = content.strip().split("\n")
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            clean_lines.append("")
            continue
        # 去除 Markdown 标题 # 号
        line_clean = re.sub(r"^#+\s*", "", line_clean)
        # 去除粗体和斜体
        line_clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", line_clean)
        line_clean = re.sub(r"\*([^*]+)\*", r"\1", line_clean)
        # 首行增加中文全角两空格 (标题行不缩进)
        if i == 0:
            clean_lines.append(line_clean)
        else:
            clean_lines.append(f"　　{line_clean}")
    return "\n".join(clean_lines)


def generate_novel_toc_and_volume_packages(novel_dir: str, cfg: Dict[str, Any], log_func=None) -> str:
    """
    分卷发布包与全书目录树生成器 (Multi-Format Exporter & TOC):
    1. 生成全书标准 Markdown 目录树 (目录.md)，带章节锚点与字数统计；
    2. 根据 config.yaml 中的 volume_routing 自动将章节打包至分卷合集目录。
    """
    import time
    novel_dir = os.path.abspath(novel_dir)
    md_dir = os.path.join(novel_dir, "正文")
    if not os.path.exists(md_dir):
        return ""

    files = glob.glob(os.path.join(md_dir, "C_正文_第*章.md"))
    if not files:
        return ""

    def get_ch_num(p):
        m = re.search(r"第(\d+)章", os.path.basename(p))
        return int(m.group(1)) if m else 999999

    files.sort(key=get_ch_num)

    # 1. 生成 目录.md
    book_title = cfg.get("project", {}).get("title", "小说作品")
    toc_lines = [f"# {book_title} · 章节总目录\n", f"> 累计收录：{len(files)} 章 | 自动生成于：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
    
    routes = cfg.get("volume_routing", [])
    current_vol_idx = 0

    for fpath in files:
        ch_idx = get_ch_num(fpath)
        first_line = ""
        try:
            with open(fpath, "r", encoding="utf-8") as rf:
                first_line = rf.readline().strip().lstrip("#").strip()
        except Exception:
            first_line = f"第{ch_idx}章"

        # 检查是否进入新卷
        if routes and current_vol_idx < len(routes):
            r = routes[current_vol_idx]
            if ch_idx == r.get("start_ch"):
                toc_lines.append(f"\n## 📚 第{r.get('volume')}卷：{r.get('name', '未命名分卷')} (第{r.get('start_ch')}~{r.get('end_ch')}章)\n")
                current_vol_idx += 1

        rel_path = os.path.relpath(fpath, novel_dir)
        toc_lines.append(f"- [{first_line}]({rel_path})")

    toc_content = "\n".join(toc_lines) + "\n"
    toc_path = os.path.join(novel_dir, "目录.md")
    atomic_write(toc_path, toc_content)

    if log_func:
        log_func(f"[Publisher] 📚 已生成全书目录树: {toc_path}")

    return toc_path


def merge_published_text_chapters(novel_dir: str, log_func=None) -> int:
    """增量或全量聚合所有发布版单章纯文本至 正文/发布版/合集.txt (排除自身，按章节数字排序，纯双空行自然连接)"""
    clean_dir = os.path.join(novel_dir, "正文", "发布版")
    if not os.path.exists(clean_dir):
        return 0

    heji_txt_path = os.path.join(clean_dir, "合集.txt")
    txt_files = glob.glob(os.path.join(clean_dir, "*.txt"))
    if not txt_files:
        return 0

    def extract_num(f_path):
        fname = os.path.basename(f_path)
        if fname == "合集.txt":
            return 999999
        m = re.search(r"第?(\d+)章?", fname)
        return int(m.group(1)) if m else 999999

    # 排除自身并按章节数字序号升序排序
    valid_files = [f for f in txt_files if os.path.basename(f) != "合集.txt"]
    valid_files.sort(key=extract_num)

    if not valid_files:
        return 0

    merged_parts = []
    seen_chapters = set()
    for tf in valid_files:
        ch_num = extract_num(tf)
        if ch_num in seen_chapters or ch_num == 999999:
            continue
        seen_chapters.add(ch_num)
        try:
            with open(tf, "r", encoding="utf-8") as f:
                ch_text = f.read().strip()
            if ch_text:
                merged_parts.append(ch_text)
        except Exception:
            pass

    full_heji_txt = "\n\n".join(merged_parts) + "\n"
    atomic_write(heji_txt_path, full_heji_txt)

    if log_func:
        log_func(f"[Publisher] 纯文本合集已更新: {heji_txt_path} (累计 {len(seen_chapters)} 章)")

    return len(seen_chapters)


def merge_all_chapters(novel_dir: str, ch_prefix: str, ch_suffix: str, master_file: str, cfg: Optional[Dict[str, Any]] = None, log_func=None) -> int:
    """增量追加或全量聚合所有章节至 正文/合集.md，并同步更新 目录.md"""
    heji_dir = os.path.join(novel_dir, "正文")
    os.makedirs(heji_dir, exist_ok=True)
    heji_path = os.path.join(heji_dir, master_file)

    chapter_files = glob.glob(os.path.join(novel_dir, "正文", f"{ch_prefix}*{ch_suffix}"))
    if not chapter_files:
        chapter_files = glob.glob(os.path.join(novel_dir, f"{ch_prefix}*{ch_suffix}"))

    def extract_num(f_path):
        fname = os.path.basename(f_path)
        m = re.search(r"第?(\d+)章?", fname)
        return int(m.group(1)) if m else 999999

    chapter_files.sort(key=extract_num)
    if not chapter_files:
        return 0

    # 聚合去重合并
    merged_parts = []
    seen_chapters = set()
    for cf in chapter_files:
        ch_num = extract_num(cf)
        if ch_num in seen_chapters or ch_num == 999999:
            continue
        seen_chapters.add(ch_num)
        try:
            with open(cf, "r", encoding="utf-8") as f:
                ch_text = f.read().strip()
            merged_parts.append(ch_text)
        except Exception:
            pass

    full_heji = "\n\n---\n\n".join(merged_parts) + "\n"
    atomic_write(heji_path, full_heji)

    # 同步生成 目录.md
    if cfg:
        try:
            generate_novel_toc_and_volume_packages(novel_dir, cfg, log_func=log_func)
        except Exception:
            pass

    return len(seen_chapters)


def run_publisher(
    chapter_output: str,
    chapter_num: int,
    is_last: bool,
    cfg: Dict[str, Any],
    expected_title_full: str = "",
    log_func=None
) -> str:
    """落盘发布 Agent（保存至 正文/ 目录，自动更新 合集.md）"""
    if log_func:
        log_func(f"[Publisher] 保存第{chapter_num}章...")

    novel_dir = cfg["project"]["novel_dir"]
    ch_prefix = cfg["project"]["chapter_prefix"]
    ch_suffix = cfg["project"]["chapter_suffix"]
    master_file = cfg["project"]["master_file"]

    content = extract_xml_tag(chapter_output, "chapter_content")
    if not content:
        content = chapter_output

    # 确定性文本净化（过滤低幼叫骂与AI套话）
    content = sanitize_vulgar_and_cliches(content)

    # 发布层 0 字与安全报错硬性拦截门禁
    pure_chinese = re.findall(r"[\u4e00-\u9fff]", content)
    if len(pure_chinese) < 1000 or any(bk in content.lower() for bk in ["blocked by", "policies.google.com", "safety filter"]):
        err_msg = f"[Publisher FATAL] 第{chapter_num}章内容残废或命中上游安全阻断 (仅{len(pure_chinese)}中文)，禁止落盘发布！"
        if log_func:
            log_func(err_msg, level="ERROR")
        raise ValueError(err_msg)

    # 标题自愈：保证写入标准七猫爆款钩子标题
    lines = content.strip().split("\n")
    if expected_title_full:
        if lines[0].startswith("#"):
            lines[0] = f"# 第{chapter_num}章：{expected_title_full}"
        else:
            lines.insert(0, f"# 第{chapter_num}章：{expected_title_full}\n")
        content = "\n".join(lines)
    elif not lines[0].startswith(f"# 第{chapter_num}章") and not lines[0].startswith(f"#第{chapter_num}章"):
        title_tag = extract_xml_tag(chapter_output, "chapter_title")
        if title_tag:
            content = f"# {title_tag}\n\n" + content.lstrip()

    # 保存标准 Markdown 归档版于 正文/ 目录
    md_dir = os.path.join(novel_dir, "正文")
    os.makedirs(md_dir, exist_ok=True)
    path = os.path.join(md_dir, f"{ch_prefix}{chapter_num}{ch_suffix}")
    atomic_write(path, content)
    if log_func:
        log_func(f"[Publisher] 已保存: {path}")

    # 同步生成平台直发纯净版 (100% 纯净正文，无任何尾部预告标记)
    try:
        final_clean_text = format_clean_platform_text(content)
        clean_dir = os.path.join(novel_dir, "正文", "发布版")
        os.makedirs(clean_dir, exist_ok=True)
        clean_path = os.path.join(clean_dir, f"{ch_prefix}{chapter_num}章.txt")
        atomic_write(clean_path, final_clean_text)
        if log_func:
            log_func(f"[Publisher] 纯净版已保存: {clean_path}")
    except Exception as ce:
        if log_func:
            log_func(f"[Publisher 警告] 纯净版生成异常: {ce}")

    # 增量追加至合集文件并更新目录树
    total_in_heji = merge_all_chapters(novel_dir, ch_prefix, ch_suffix, master_file, cfg=cfg, log_func=log_func)
    if log_func:
        log_func(f"[Publisher] 合集增量追加: +1 章 (累计 {total_in_heji} 章)")

    # 同步增量聚合发布版纯文本合集 (合集.txt)
    total_in_txt_heji = merge_published_text_chapters(novel_dir, log_func=log_func)
    if log_func:
        log_func(f"[Publisher] 发布版合集.txt 同步更新: 累计 {total_in_txt_heji} 章")

    return path

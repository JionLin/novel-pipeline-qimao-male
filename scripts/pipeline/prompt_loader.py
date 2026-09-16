# -*- coding: utf-8 -*-
"""
prompt_loader.py - 智能两级 Prompt 模板加载与缓存引擎
支持：
1. 优先加载小说项目工作区内的个性化提示词: {novel_dir}/prompts/{prompt_name}.md
2. 回退加载全局默认标准提示词: scripts/prompts/{prompt_name}.md
3. 内存缓存 (Memory Caching) 与零开销热重载
"""

import os
from typing import Optional, Dict

_PROMPT_CACHE: Dict[str, str] = {}


def load_prompt(prompt_name: str, custom_dir: Optional[str] = None, reload: bool = False, log_func=None) -> str:
    """
    智能加载指定名称的 Prompt 模板内容。
    
    :param prompt_name: 提示词文件名（不含扩展名，如 'writer', 'reviewer', 'block_blueprint'）
    :param custom_dir: 当前小说项目目录（若提供，优先检查项目目录下的 prompts/{prompt_name}.md）
    :param reload: 是否强制绕过缓存重新从磁盘读取
    :param log_func: 日志记录回调函数
    :return: 完整的提示词字符串
    """
    cache_key = f"{custom_dir or 'global'}::{prompt_name}"
    if not reload and cache_key in _PROMPT_CACHE:
        return _PROMPT_CACHE[cache_key]

    # 1. 检查工作区自定义提示词
    if custom_dir:
        local_path = os.path.join(custom_dir, "prompts", f"{prompt_name}.md")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    _PROMPT_CACHE[cache_key] = content
                    if log_func:
                        log_func(f"[Prompt Loader] ✅ 已加载项目专属定制提示词: {os.path.basename(local_path)}")
                    return content
            except Exception as e:
                if log_func:
                    log_func(f"[Prompt Loader] [WARN] 读取项目专属提示词失败 [{local_path}]: {e}，回退至全局模板", level="WARN")

    # 2. 回退到全局标准提示词 (scripts/prompts/)
    script_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    global_dir = os.path.join(script_root, "prompts")
    global_path = os.path.join(global_dir, f"{prompt_name}.md")
    if os.path.exists(global_path):
        try:
            with open(global_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                _PROMPT_CACHE[cache_key] = content
                if custom_dir and log_func:
                    log_func(f"[Prompt Loader] ℹ️ 未发现项目专属定制提示词 [{prompt_name}.md]，已加载系统全局母版: {os.path.basename(global_path)}")
                return content
        except Exception as e:
            if log_func:
                log_func(f"[Prompt Loader] [ERROR] 读取全局提示词文件失败 [{global_path}]: {e}", level="ERROR")
            raise IOError(f"读取全局提示词文件失败 [{global_path}]: {e}")

    err_msg = f"未找到指定的提示词文件: {prompt_name}.md (搜索路径: {global_path})"
    if log_func:
        log_func(f"[Prompt Loader] [ERROR] {err_msg}", level="ERROR")
    raise FileNotFoundError(err_msg)


def load_genre_prose_card(
    genre_name: str,
    stage: Optional[str] = None,
    custom_dir: Optional[str] = None,
    script_dir: Optional[str] = None,
    reload: bool = False,
    log_func=None
) -> str:
    """
    智能加载题材专属文风卡 (Genre Prose Card)：
    支持单文件 (.md) 与三维模块化目录包模式，并支持根据 stage (L1-L5) 进行阶段感知精准提取。
    """
    if not genre_name:
        return "（采用通用文学力学文风，无特定题材禁令）"

    mapping = [
        (["种田", "甜宠", "边关种田", "农女", "荒原"], "female_frontier_farming"),
        (["古言", "古代言情", "言情", "宅斗", "宫斗", "真假千金", "重生", "王妃", "主母"], "ancient_romance_palace"),
        (["历史", "藩王", "就藩", "军工", "古代", "大明", "大秦", "大唐", "朝堂", "三国"], "history_military"),
        (["仙侠", "修仙", "修真", "玄幻", "宗门", "飞升", "洪荒", "道尊"], "xianxia_cultivation"),
        (["都市", "神豪", "战神", "赘婿", "脑洞", "逆袭", "职场", "商战"], "urban_face_slap"),
        (["末世", "避难所", "求生", "丧尸", "废土", "科幻", "机甲"], "apocalypse_shelter"),
    ]

    card_key = None
    for keywords, card_name in mapping:
        if any(k in genre_name for k in keywords):
            card_key = card_name
            break

    if not card_key:
        card_key = "history_military" if "军" in genre_name else None

    if not card_key:
        return "（采用通用文学力学文风，无特定题材禁令）"

    script_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if not script_dir else script_dir
    cards_dir = os.path.join(script_root, "prompts", "genre_cards")

    # 1. 优先检查是否存在多文件模块目录 (如 genre_cards/history_military/)
    pkg_dir = os.path.join(cards_dir, card_key)
    if os.path.isdir(pkg_dir):
        try:
            subfiles = sorted([f for f in os.listdir(pkg_dir) if f.endswith(".md")])
            # 根据 stage 阶段精准筛选
            selected_files = []
            if stage in ["L1", "L2", "master", "block"]:
                # L1/L2 仅加载硬性度量衡与术语 (1_measures_and_terms.md)
                selected_files = [f for f in subfiles if "1_" in f or "measures" in f]
            elif stage in ["L5", "reviewer", "review"]:
                # L5 审读阶段加载 1 (禁词/代差) 与 3 (声线红线)
                selected_files = [f for f in subfiles if ("1_" in f or "3_" in f or "measures" in f or "voice" in f)]
            else:
                # L3/L4 或未指定阶段：全量加载 1 + 2 + 3
                selected_files = subfiles

            if not selected_files:
                selected_files = subfiles

            parts = []
            for sf in selected_files:
                sf_path = os.path.join(pkg_dir, sf)
                with open(sf_path, "r", encoding="utf-8") as f:
                    parts.append(f.read().strip())

            content = "\n\n".join(parts)
            if log_func:
                stage_tag = f" [{stage}]" if stage else ""
                log_func(f"[Prompt Loader] 🎭 已挂载题材专属文风包{stage_tag}: {card_key}/ ({len(selected_files)} 个模块文件)")
            return content
        except Exception as e:
            if log_func:
                log_func(f"[Prompt Loader] [WARN] 读取题材文风包失败 [{pkg_dir}]: {e}", level="WARN")

    # 2. 回退降级检查单文件 (如 genre_cards/history_military.md)
    card_file = os.path.join(cards_dir, f"{card_key}.md")
    if os.path.exists(card_file):
        try:
            with open(card_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if log_func:
                    log_func(f"[Prompt Loader] 🎭 已挂载题材专属文风卡: {os.path.basename(card_file)}")
                return content
        except Exception as e:
            if log_func:
                log_func(f"[Prompt Loader] [WARN] 读取题材文风卡失败 [{card_file}]: {e}", level="WARN")

    return "（采用通用文学力学文风，无特定题材禁令）"




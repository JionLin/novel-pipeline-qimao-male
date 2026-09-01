# -*- coding: utf-8 -*-
"""
pipeline/jit_buffer.py - JIT 准实时滑动细纲视距保障器
负责：
检查前瞻章节（如 current_chapter + 3）细纲是否就绪。
若未就绪，自动派发异步/即时滑动生成任务，确保写手前方永远拥有 3 章滑动储备。
"""

import os
import sys
import subprocess
from typing import Dict, Any
from pipeline.context_builder import load_chapter_outline, get_outline_config


def ensure_jit_sliding_outline_buffer(
    current_chapter: int,
    cfg: Dict[str, Any],
    script_dir: str,
    log_func=None
) -> None:
    """
    JIT 准实时滑动细纲视距保障机制：
    1. 若当前章节 current_chapter 细纲未就绪，立即同步阻塞生成 [current_chapter, current_chapter + 3] 细纲；
    2. 若当前章节已就绪但前瞻 target_ch = current_chapter + 3 细纲未就绪，异步派发滑动生成任务。
    """
    target_ch = current_chapter + 3
    vol_info = get_outline_config(cfg, current_chapter)
    vol_num = vol_info.get("volume", 1)
    tw = cfg.get("project", {}).get("target_words", 2700000)
    target_ch_words = cfg.get("quality", {}).get("target_chinese_chars", 2400)
    total_ch = max(50, tw // target_ch_words)

    # 1. 检查当前章节是否缺失
    curr_missing = False
    try:
        load_chapter_outline(cfg, current_chapter)
    except ValueError:
        curr_missing = True

    if curr_missing:
        msg = f"[JIT滑动细纲] 探测到当前第 {current_chapter} 章细纲未就绪，立即同步生成滑动细纲 (第 {current_chapter} ~ {target_ch} 章)..."
        if log_func:
            log_func(msg, level="INFO")
        else:
            print(f"[INFO] {msg}", flush=True)

        cmd = [
            sys.executable,
            os.path.join(script_dir, "auto_outline.py"),
            "chapters",
            str(current_chapter),
            str(target_ch),
            str(vol_num),
            str(total_ch)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            err_msg = f"[JIT滑动细纲] [WARN] 同步生成当前细纲异常: {e}"
            if log_func:
                log_func(err_msg, level="WARN")
            else:
                print(f"[WARN] {err_msg}", flush=True)
        return

    # 2. 当前章节就绪，前瞻检查 target_ch
    try:
        load_chapter_outline(cfg, target_ch)
    except ValueError:
        msg = f"[JIT滑动细纲] 探测到前瞻第 {target_ch} 章细纲未就绪，异步派发滑动细纲生成任务 (第 {current_chapter + 1} ~ {target_ch} 章)..."
        if log_func:
            log_func(msg, level="INFO")
        else:
            print(f"[INFO] {msg}", flush=True)

        cmd = [
            sys.executable,
            os.path.join(script_dir, "auto_outline.py"),
            "chapters",
            str(current_chapter + 1),
            str(target_ch),
            str(vol_num),
            str(total_ch)
        ]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            err_msg = f"[JIT滑动细纲] [WARN] 异步派发细纲生成任务异常: {e}"
            if log_func:
                log_func(err_msg, level="WARN")
            else:
                print(f"[WARN] {err_msg}", flush=True)
    except Exception as ex:
        err_msg = f"[JIT滑动细纲] [WARN] 检查第 {target_ch} 章细纲状态异常: {ex}"
        if log_func:
            log_func(err_msg, level="WARN")
        else:
            print(f"[WARN] {err_msg}", flush=True)


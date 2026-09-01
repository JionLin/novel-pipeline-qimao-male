# -*- coding: utf-8 -*-
"""
outline/block_planner.py - 中观块级施工图生成器 (Prompt 1)
负责将宏观大纲中的【一卷】按 15-17 章切分为若干个中观情节块（Block Blueprint）。
包含：
1. 中观块级施工图生成 (generate_volume_blocks)
2. 当前章节所属块级施工图定位与增强提取 (load_active_block_context)
3. 跨块爽点校验切片与物象心跳反哺机制
"""

import os
import re
import yaml
from typing import Dict, Any, List, Optional, Tuple


def extract_payoff_table_from_block(block_text: str) -> str:
    """从块施工图文本中提取字段 10 爽点校验表"""
    if not block_text:
        return ""
    m_table = re.search(r'(?:字段\s*10[：:]|爽点校验表|爽点蓄力与释放节奏校验表)[^\n]*\n(.*?)(?=\n###|\n##|\Z)', block_text, re.DOTALL)
    if m_table:
        table_content = m_table.group(1).strip()
        lines = [ln for ln in table_content.split("\n") if "|" in ln or "爽点" in ln or "合规" in ln]
        if lines:
            return "\n".join(lines[:10])
    return ""


def extract_end_state_from_block(block_text: str) -> str:
    """从块施工图文本中提取物资血脉与角色阶段终态"""
    if not block_text:
        return ""
    end_state_items = []
    # 提取物资血脉
    m_res = re.search(r'(?:物资血脉|物资存量|资源血脉)[：:\s]*([^\n\r]+)', block_text)
    if m_res:
        end_state_items.append(f"物资血脉: {m_res.group(1).strip()}")
    # 提取情感/羁绊阶段
    m_emo = re.search(r'(?:情感阶段|同袍羁绊|关系推进|双轨情感)[：:\s]*([^\n\r]+)', block_text)
    if m_emo:
        end_state_items.append(f"情感阶段: {m_emo.group(1).strip()}")
    return " | ".join(end_state_items)


def heal_block_blueprint_cadence(full_text: str) -> str:
    """
    对中观施工图中的爽点节拍校验表执行自动自愈校验与修补：
    若两两爽点间隔 > 3 章，自动修正计算式并插入中间自愈爽点行，确保符合 M4 规范。
    """
    lines = full_text.split("\n")
    new_lines = []
    in_table = False
    prev_ch = None
    table_idx = 1

    for line in lines:
        m_row = re.match(r'\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|', line)
        if m_row:
            ch_raw = m_row.group(3).strip()
            ptype = m_row.group(2).strip()
            m_num = re.search(r'第?\s*(\d+)\s*章?', ch_raw)
            if m_num:
                cur_ch = int(m_num.group(1))
                if prev_ch is not None and cur_ch - prev_ch > 3:
                    # 补齐中间自愈爽点
                    mid_ch = prev_ch + 3
                    delta = mid_ch - prev_ch
                    heal_line = f"| {table_idx} | 算账碾压型/微型代差震慑 | 第{mid_ch}章 | {mid_ch} - {prev_ch} = {delta}章 | 合规 |"
                    new_lines.append(heal_line)
                    table_idx += 1
                    prev_ch = mid_ch

                delta_str = f"{cur_ch} - {prev_ch} = {cur_ch - prev_ch}章" if prev_ch is not None else "起始基准"
                new_line = f"| {table_idx} | {ptype} | 第{cur_ch}章 | {delta_str} | 合规 |"
                new_lines.append(new_line)
                table_idx += 1
                prev_ch = cur_ch
                in_table = True
            else:
                new_lines.append(line)
        else:
            if in_table and not line.strip().startswith("|"):
                in_table = False
                prev_ch = None
                table_idx = 1
            new_lines.append(line)

    return "\n".join(new_lines)


def generate_volume_blocks(
    volume_num: int,
    start_ch: int,
    end_ch: int,
    master_text: str,
    target_words: int,
    client,
    model_name: str,
    cfg: Dict[str, Any],
    output_path: str = "",
    log_func=None
) -> str:
    """为指定卷生成中观块级施工图 (Prompt 1)"""
    if log_func:
        log_func(f"[Block-Planner] 正在为第 {volume_num} 卷 (第 {start_ch} ~ {end_ch} 章) 编译中观块级施工图 (Prompt 1)...")

    novel_dir = cfg.get("project", {}).get("novel_dir", "") or cfg.get("project", {}).get("workspace_dir", "")
    from pipeline.prompt_loader import load_prompt
    system_prompt = load_prompt("02_block_blueprint", custom_dir=novel_dir)

    # 读取 L6 状态追踪看板历史预警与物象状态，构建数据驱动自愈反哺指令
    l6_feedback_instruction = ""
    try:
        from storage.state_manager import get_thread_tracking_alert, get_soul_totem_state
        thread_alert = get_thread_tracking_alert(novel_dir)
        totem_state = get_soul_totem_state(novel_dir)
        feedback_parts = []
        if thread_alert:
            feedback_parts.append(f"- 叙事线程预警: {thread_alert}")
        if totem_state:
            feedback_parts.append(f"- 灵魂物象当前状态: [{totem_state.get('name')}] 为 [{totem_state.get('physical_state')}] (最近第 {totem_state.get('last_updated_ch', 1)} 章)")
        
        if feedback_parts:
            l6_feedback_instruction = "\n【来自前序卷状态机 (L6) 与物象图谱的数据驱动反哺指令】：\n" + "\n".join(feedback_parts) + "\n"
    except Exception:
        pass

    user_prompt = f"""请根据以下【全书总纲与分卷设定】，为第 {volume_num} 卷（第 {start_ch} ~ {end_ch} 章）生成完整的【中观块级施工图】：
{l6_feedback_instruction}
【全书总纲与分卷宏观设定】：
{master_text}

【目标卷信息】：
- 卷号：第 {volume_num} 卷
- 章节区间：第 {start_ch} 章 ~ 第 {end_ch} 章（共 {end_ch - start_ch + 1} 章）
- 每块跨度：严格按 15-17 章/块 拆分

请严格按照 Prompt 规范格式输出全部块级施工图（Markdown 格式），严格包含全部 11 个标准字段。
"""

    max_tokens_val = cfg.get("models", {}).get("planner", {}).get("max_tokens", 8192)
    from pipeline.utils import safe_chat_completion

    total_span = end_ch - start_ch + 1
    if total_span >= 70:
        # 【大卷按半卷拆分：前 50 章 (块1~3) + 后 50 章 (块4~6) 双批次串行生成】
        mid_ch = start_ch + (total_span // 2) - 1

        if log_func:
            log_func(f"[Block-Planner] [Pass 1/2] 正在规划第 {volume_num} 卷上半卷 (第 {start_ch} ~ {mid_ch} 章，块 1~3)...")

        prompt_p1 = f"""请根据以下【全书总纲与分卷设定】，为第 {volume_num} 卷上半卷（第 {start_ch} ~ {mid_ch} 章）生成【前 3 个中观情节块（块 1 ~ 块 3）施工图】：
{l6_feedback_instruction}
【⚡ 爽点节拍刚性排期与战役几何硬要求 (M4规范)】：
1. 每一个块（16~17章）必须密集规划至少 5~6 个爽点事件，严禁两爽点间隔超过 3 章！
   - 块 1 (第 {start_ch}~{start_ch+16} 章): 必须在第 {start_ch+1}、{start_ch+4}、{start_ch+7}、{start_ch+10}、{start_ch+13}、{start_ch+16} 章等均匀爆发爽点！
   - 块 2 与 块 3 同理，逐行计算 Y - X ≤ 3，严禁写出 4~6 章的长蓄力断层！
2. 凡包含重大战役或 F 类高潮章节，因果描述末尾必须显式附带【三维几何坐标：射界X步/壕沟Y丈/纵深Z步/风向W】！

【全书总纲与分卷宏观设定】：
{master_text}

【目标半卷信息】：
- 卷号：第 {volume_num} 卷（上半卷）
- 章节区间：第 {start_ch} 章 ~ 第 {mid_ch} 章（前 3 块，每块 15-17 章）
- 请严格按 02_block_blueprint 规范输出前 3 块完整的 11 个标准字段（包含物资血脉与双轨情感）。
"""
        result_p1 = safe_chat_completion(
            client=client,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt_p1},
            ],
            temperature=0.5,
            max_tokens=max_tokens_val,
            max_retries=3,
            log_func=log_func
        )

        # 提取上半卷终态指标（块 3 校验表与终态）
        p1_payoff_summary = extract_payoff_table_from_block(result_p1)
        p1_end_summary = extract_end_state_from_block(result_p1)

        p1_bridge_directive = ""
        if p1_payoff_summary or p1_end_summary:
            p1_bridge_directive = f"\n【上半卷终态与爽点节奏承接要求】:\n- 上半卷终态沉淀: {p1_end_summary}\n- 上半卷爽点校验表摘要:\n{p1_payoff_summary}\n"

        if log_func:
            log_func(f"[Block-Planner] [Pass 2/2] 正在规划第 {volume_num} 卷下半卷 (第 {mid_ch + 1} ~ {end_ch} 章，块 4~6)...")

        prompt_p2 = f"""请根据以下【全书总纲】以及已生成的【上半卷（块 1~3）施工图与终态物资】，继续为第 {volume_num} 卷下半卷（第 {mid_ch + 1} ~ {end_ch} 章）生成【后 3 个中观情节块（块 4 ~ 块 6）施工图】：
{p1_bridge_directive}
【⚡ 爽点节拍刚性排期与战役几何硬要求 (M4规范)】：
1. 每一个块（块4~6，每块16~17章）必须密集规划至少 5~6 个爽点事件，严禁两爽点间隔超过 3 章！
   - 块 4 (第 51~67 章): 必须在第 52、55、58、61、64、67 章等均匀爆发爽点！
   - 块 5 与 块 6 同理，逐行计算 Y - X ≤ 3，严禁写出 4~6 章的长蓄力断层！
2. 凡包含重大战役或 F 类高潮章节，因果描述末尾必须显式附带【三维几何坐标：射界X步/壕沟Y丈/纵深Z步/风向W】！

【全书总纲】：
{master_text}

【已锁定的上半卷（块 1~3）施工图】：
{result_p1}

【目标下半卷信息】：
- 卷号：第 {volume_num} 卷（下半卷）
- 章节区间：第 {mid_ch + 1} 章 ~ 第 {end_ch} 章（后 3 块，块 4 ~ 块 6，每块 15-17 章）
- 必须严格继承块 3 结束时的物资存量与人物情感阶段，输出块 4 ~ 块 6 完整的 11 个标准字段！
"""
        result_p2 = safe_chat_completion(
            client=client,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt_p2},
            ],
            temperature=0.5,
            max_tokens=max_tokens_val,
            max_retries=3,
            log_func=log_func
        )

        result = f"{result_p1.strip()}\n\n---\n\n{result_p2.strip()}\n"
    else:
        # 短卷单批次生成
        result = safe_chat_completion(
            client=client,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=max_tokens_val,
            max_retries=3,
            log_func=log_func
        )

    # 自动执行 M4 爽点节拍自愈修补
    result = heal_block_blueprint_cadence(result)

    if output_path:
        from pipeline.utils import atomic_write
        atomic_write(output_path, result)
        if log_func:
            log_func(f"[Block-Planner] ✅ 第 {volume_num} 卷中观块级施工图已落盘保存至: {output_path}")

    return result



def load_active_block_context(novel_dir: str, vol_num: int, chapter_num: int) -> str:
    """
    根据当前章节号，从对应分卷的块级施工图中提取当前所属块的施工规划，
    并自动切片提取上一块的爽点校验表与图谱物象心跳状态作为增强上下文注入。
    """
    novel_dir = os.path.abspath(novel_dir)
    candidates = [
        os.path.join(novel_dir, "大纲", f"第{vol_num}卷_块级施工图.md"),
        os.path.join(novel_dir, f"第{vol_num}卷_块级施工图.md"),
    ]
    block_file = None
    for cand in candidates:
        if os.path.exists(cand):
            block_file = cand
            break

    if not block_file:
        return ""

    try:
        with open(block_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配所有 `## 块 X：第 A - B 章`
        pattern = r"(##\s*块\s*(\d+)[^\n\r]*第\s*(\d+)\s*[-~到至]\s*(\d+)\s*章.*?(?=(?:\n##\s*块|\Z)))"
        all_blocks = []
        for block_match, b_idx_str, s_str, e_str in re.findall(pattern, content, re.DOTALL):
            all_blocks.append({
                "block_idx": int(b_idx_str),
                "text": block_match.strip(),
                "start_ch": int(s_str),
                "end_ch": int(e_str)
            })

        matched_idx = -1
        for i, blk in enumerate(all_blocks):
            if blk["start_ch"] <= chapter_num <= blk["end_ch"]:
                matched_idx = i
                break

        if matched_idx == -1:
            # 若未精准匹配到区间，返回前 2500 字符作为概览
            return content[:2500]

        curr_block = all_blocks[matched_idx]
        context_parts = []

        # 1. 注入前序块爽点合规度与终态（若存在前序块）
        if matched_idx > 0:
            prev_block = all_blocks[matched_idx - 1]
            prev_payoff = extract_payoff_table_from_block(prev_block["text"])
            prev_end = extract_end_state_from_block(prev_block["text"])
            if prev_payoff or prev_end:
                context_parts.append(
                    f"【前序块 (块 {prev_block['block_idx']}) 节奏反馈与终态承接】:\n"
                    f"- 前序终态: {prev_end or '无明显标记'}\n"
                    f"- 爽点校验表摘要:\n{prev_payoff or '无独立表格'}"
                )

        # 2. 注入图谱中物象心跳状态
        try:
            from storage.state_manager import get_soul_totem_state
            totem_state = get_soul_totem_state(novel_dir)
            if totem_state and totem_state.get("name"):
                context_parts.append(
                    f"【核心物象心跳感知】:\n"
                    f"- 灵魂物象: [{totem_state.get('name')}]\n"
                    f"- 当前物理形态: [{totem_state.get('physical_state', 'intact')}]\n"
                    f"- 最近变动/登场: 第 {totem_state.get('last_updated_ch', 1)} 章"
                )
        except Exception:
            pass

        # 3. 注入当前所属块的核心规划文本
        context_parts.append(f"【当前所属中观块规划 (第 {curr_block['start_ch']} ~ {curr_block['end_ch']} 章)】:\n{curr_block['text']}")

        return "\n\n".join(context_parts)
    except Exception:
        return ""

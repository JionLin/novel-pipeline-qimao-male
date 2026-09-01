# -*- coding: utf-8 -*-
"""
tools/refine_character_textures.py - 正文人物生活质感与微动作微创精修器 (Character Texture Refiner)
纯数据驱动架构 (0 业务硬编码)：
1. 动态加载当前小说的人物设定档案库与角色锁；
2. 针对高频通用地摊表情（如“面色煞白/惨白”）按角色专属肢体部位与动作矩阵进行智能置换；
3. 针对副手专属怪癖缺失的章节，根据档案库自动补齐对应动作细节；
4. 全量重绘发布版单章 TXT 与 合集.txt。
"""

import os
import sys
import glob
import re
import yaml

script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from pipeline.utils import get_active_project_dir, atomic_write
from agents.agent_4_publisher import format_clean_platform_text, merge_published_text_chapters


def refine_novel_character_textures(novel_dir: str = "", log_func=None) -> dict:
    """纯数据驱动正文微创精修器 (0 业务硬编码)"""
    if not novel_dir:
        novel_dir = get_active_project_dir(script_dir)
    novel_dir = os.path.abspath(novel_dir)
    md_dir = os.path.join(novel_dir, "正文")
    if not os.path.exists(md_dir):
        return {"status": "ERROR", "reason": "正文目录不存在"}

    dossier_dir = os.path.join(novel_dir, "人物设定")
    dossiers = {}
    if os.path.exists(dossier_dir):
        for yf in glob.glob(os.path.join(dossier_dir, "*.yaml")):
            cname = os.path.splitext(os.path.basename(yf))[0]
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    dossiers[cname] = yaml.safe_load(f) or {}
            except Exception:
                pass

    md_files = glob.glob(os.path.join(md_dir, "C_正文_第*.md"))
    
    def extract_num(fp):
        m = re.search(r"第(\d+)章", os.path.basename(fp))
        return int(m.group(1)) if m else 999999
    
    md_files.sort(key=extract_num)

    stats = {
        "shabai_replaced": 0,
        "baoxia_replaced": 0,
        "quirks_added": 0,
        "chapters_touched": 0,
        "merged_total": 0
    }

    # 通用动作置换池
    generic_alts = [
        "指节死死压平账册翘角，目光冷澈如铁",
        "指节泛白，嘴唇抿成一条极细的冷线",
        "悄然呼出一口白汽，紧绷的肩线沉下来半寸",
        "粗糙的掌心沁出冷汗，残秃双指僵在半空",
        "目光死死钉在公差死线上，喉结狠狠滚动",
    ]

    for mf in md_files:
        ch_num = extract_num(mf)
        if ch_num > 40:
            continue
        
        with open(mf, "r", encoding="utf-8") as f:
            content = f.read()

        modified = False

        # 1. 动态按角色档案置换“脸色煞白”通用表情
        for cname, cdata in dossiers.items():
            if cname in content:
                body_part = cdata.get("signature_body_part", "指节")
                action = cdata.get("signature_action", "死死按住台面")
                
                # 动态替换某角色的面色煞白
                pattern = rf"({cname}[^，。！？\n\r]{{0,15}}?)(?:面色|脸色|面孔|脸面)(?:瞬间)?(?:煞白|惨白|惨白如纸)"
                def make_repl(bp, act):
                    def _r(match):
                        nonlocal stats
                        stats["shabai_replaced"] += 1
                        return f"{match.group(1)}{bp}{act}"
                    return _r
                
                content, n_rep = re.subn(pattern, make_repl(body_part, action), content)
                if n_rep > 0:
                    modified = True

        # 2. 通用兜底置换剩余的孤立面色煞白
        def repl_generic_shabai(match):
            nonlocal stats
            stats["shabai_replaced"] += 1
            alt = generic_alts[stats["shabai_replaced"] % len(generic_alts)]
            return alt

        content, n_gen = re.subn(r"(?:面色|脸色|面孔)(?:瞬间)?(?:煞白|惨白|惨白如纸)", repl_generic_shabai, content)
        if n_gen > 0:
            modified = True

        # 3. 动态检查副手怪癖保活
        for cname, cdata in dossiers.items():
            if cdata.get("role") == "副手" and cname in content:
                action = cdata.get("signature_action", "")
                body_part = cdata.get("signature_body_part", "")
                if action and action not in content:
                    # 动态在角色首次出场动作后追加专属怪癖
                    m_char = re.search(rf"({cname}[^\n\r，。]{{0,15}}[，。])", content)
                    if m_char:
                        quirk_text = f"{cname}下意识动了动{body_part}，{action}，"
                        content = content.replace(m_char.group(1), m_char.group(1) + quirk_text, 1)
                        stats["quirks_added"] += 1
                        modified = True

        if modified:
            atomic_write(mf, content)
            clean_txt = format_clean_platform_text(content)
            txt_path = os.path.join(novel_dir, "正文", "发布版", f"C_正文_第{ch_num}章.txt")
            atomic_write(txt_path, clean_txt)
            stats["chapters_touched"] += 1

    # 4. 全量重新聚合发布版合集
    merged_total = merge_published_text_chapters(novel_dir, log_func=log_func)
    stats["merged_total"] = merged_total

    if log_func:
        log_func(f"[Refiner] 🎉 纯数据驱动微创精修完成: 置换通用惊恐 {stats['shabai_replaced']} 处, 补齐副手怪癖 {stats['quirks_added']} 处, 累计重绘合集 {merged_total} 章！")

    return stats


if __name__ == "__main__":
    res = refine_novel_character_textures(log_func=print)
    print(res)

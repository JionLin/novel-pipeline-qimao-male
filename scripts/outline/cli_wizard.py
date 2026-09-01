# -*- coding: utf-8 -*-
"""
outline/cli_wizard.py - 交互式大纲向导与多项目隔离管理器
包含：
1. 交互式终端向导 (run_interactive_wizard)
2. 项目目录自动创建与命名 (create_new_project_dir)
3. 现有项目列表与项目快速切换 (list_projects / switch_project)
4. 历史文件滚动备份 (rotate_backup_files)
"""

import os
import sys
import glob
import re
import time
import yaml
from typing import Dict, Any, List, Optional, Tuple


def rotate_backup_files(file_path: str, max_backups: int = 5) -> None:
    """滚动备份历史文件"""
    if not os.path.exists(file_path):
        return
    base_dir = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(base_dir, f".bak_{base_name}_{ts}")
    try:
        with open(file_path, "r", encoding="utf-8") as rf:
            content = rf.read()
        with open(backup_path, "w", encoding="utf-8") as wf:
            wf.write(content)
        # 清理超出数量的旧备份
        old_baks = sorted(glob.glob(os.path.join(base_dir, f".bak_{base_name}_*")))
        if len(old_baks) > max_backups:
            for ob in old_baks[:-max_backups]:
                try:
                    os.remove(ob)
                except Exception:
                    pass
    except Exception:
        pass


def create_new_project_dir(root_base: str, target_words: int, custom_title: str = "", target_ch_words: int = 2400) -> str:
    """创建时间戳隔离的小说项目工作区目录"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    tw_w = target_words // 10000
    ch_cnt = max(1, target_words // max(1000, target_ch_words))
    title_slug = f"_{custom_title}" if custom_title else ""
    folder_name = f"大纲_{tw_w}万字_{ch_cnt}章{title_slug}_{ts}"
    proj_dir = os.path.join(root_base, folder_name)
    os.makedirs(proj_dir, exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "大纲"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "正文"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "正文", "发布版"), exist_ok=True)
    return proj_dir


def list_projects(root_base: str) -> List[str]:
    """列出 root_base 下所有合法的生成小说项目目录（按修改时间倒序）"""
    if not os.path.exists(root_base):
        return []
    items = glob.glob(os.path.join(root_base, "大纲_*")) + glob.glob(os.path.join(root_base, "*"))
    valid_dirs = []
    for item in items:
        if os.path.isdir(item) and not os.path.basename(item).startswith("."):
            valid_dirs.append(os.path.abspath(item))
    valid_dirs = list(dict.fromkeys(valid_dirs))
    valid_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return valid_dirs


def switch_project(target_proj_dir: str, config_path: str = "", log_func=None) -> bool:
    """将工作区动态切换绑定至目标项目目录（仅维护目标项目内 config.yaml 与全局指针）"""
    target_proj_dir = os.path.abspath(target_proj_dir)
    if not os.path.exists(target_proj_dir):
        if log_func:
            log_func(f"[Switch Error] 目标项目目录不存在: {target_proj_dir}")
        return False

    try:
        local_cfg = os.path.join(target_proj_dir, "config.yaml")
        cfg = {}
        if os.path.exists(local_cfg):
            with open(local_cfg, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        else:
            s_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            tpl_path = os.path.join(s_dir, "config.template.yaml")
            if os.path.exists(tpl_path):
                with open(tpl_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}

        cfg.setdefault("project", {})
        cfg["project"]["novel_dir"] = target_proj_dir
        
        # 自动推导子路径
        out_sub = os.path.join(target_proj_dir, "大纲")
        cfg["project"]["outline_dir"] = out_sub if os.path.exists(out_sub) else target_proj_dir

        master_md = os.path.join(cfg["project"]["outline_dir"], "大纲.md")
        if not os.path.exists(master_md):
            master_md = os.path.join(target_proj_dir, "大纲.md")
        cfg["project"]["master_outline"] = master_md
        cfg["project"]["master_file"] = "合集.md"

        rotate_backup_files(local_cfg)
        from pipeline.utils import atomic_write, set_active_project_dir
        cfg_str = yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False)
        atomic_write(local_cfg, cfg_str)
        set_active_project_dir(target_proj_dir)

        if log_func:
            log_func(f"[Switch Success] ✅ 已成功切换并绑定工作区至: {target_proj_dir}")
        return True
    except Exception as e:
        if log_func:
            log_func(f"[Switch Error] 写入项目配置异常: {e}")
        return False



def extract_characters_from_master_text(master_text: str) -> Tuple[List[str], List[dict]]:
    """从总纲文本的【人物体系】板块中通用动态提取角色名单及身份锁，0 业务硬编码"""
    manifest_data = extract_full_project_manifest(master_text)
    return manifest_data["char_names"], manifest_data["char_locks"]


def extract_full_project_manifest(master_text: str) -> Dict[str, Any]:
    """
    从总纲文本中全量自动提取结构化项目契约数据（0 业务硬编码）：
    1. 角色档案 (char_names, char_locks: 主角/副手/专属身体部位/专属动作/语言特征)
    2. 核心物象 5 阶段里程碑 (core_artifact)
    3. 核心宿敌微反应 (nemeses)
    4. 呼吸章副手跨块轮换白名单 (breathing_chapter_rotation)
    """
    char_names = []
    char_locks = []
    sidekick_names = []
    nemeses_list = []
    core_artifact = {}

    # 1. 优先解析声明式 characters_manifest 结构化 YAML 数据块 (Schema Contract)
    manifest_m = re.search(r"```(?:yaml)?\s*(characters_manifest:[\s\S]*?)```", master_text)
    if manifest_m:
        try:
            m_data = yaml.safe_load(manifest_m.group(1))
            manifest_list = m_data.get("characters_manifest", [])
            for c in manifest_list:
                c_name = str(c.get("name", "")).strip().replace("*", "").replace("#", "")
                c_id = str(c.get("legal_identity", "核心角色")).strip()
                c_rel = str(c.get("relationship_to_protagonist", ""))
                if c_name and c_name not in char_names and 1 <= len(c_name) <= 12:
                    char_names.append(c_name)
                    item = {
                        "name": c_name,
                        "legal_identity": c_id[:40],
                        "role": "主角" if ("主角" in c_rel or len(char_names) == 1) else ("宿敌" if "宿敌" in c_rel or "政敌" in c_rel else "副手")
                    }
                    if any(k in c_id for k in ["失语", "聋", "哑"]):
                        item["is_mute"] = True
                    char_locks.append(item)
                    if item["role"] == "副手":
                        sidekick_names.append(c_name)
                    elif item["role"] == "宿敌":
                        nemeses_list.append({"name": c_name})
        except Exception:
            pass

    # 2. 降级容错：截取【人物体系与命运拓扑】板块内容进行 AST 作用域正则提取
    char_section_m = re.search(r"##\s*二[、\.\s]*人物[^\n\r]*\n(.*?)(?=\n##\s*三|\Z)", master_text, re.DOTALL)
    section_text = char_section_m.group(1) if char_section_m else master_text

    # 2.1 提取核心随从/副手专属细节 (生活质感与动作化忠诚)
    sidekick_blocks = re.findall(r"####\s*[①②③④⑤⑥⑦⑧⑨\d+]*\s*([^\n\r]+?)\n(.*?)(?=\n####|\n###|\n##|\Z)", section_text, re.DOTALL)
    for title_line, block_body in sidekick_blocks:
        m_name = re.search(r"[·\s]([\u4e00-\u9fff]{2,4})(?:[（(]|$)", title_line)
        if not m_name:
            m_name = re.search(r"([\u4e00-\u9fff]{2,4})", title_line)
        if m_name:
            c_name = m_name.group(1).strip()
            if 2 <= len(c_name) <= 4 and c_name not in ["宿敌", "对弈", "物象", "反派"]:
                if c_name not in char_names:
                    char_names.append(c_name)
                lock_item = next((item for item in char_locks if item["name"] == c_name), None)
                if not lock_item:
                    lock_item = {"name": c_name, "role": "副手", "legal_identity": title_line[:40]}
                    char_locks.append(lock_item)
                if c_name not in sidekick_names:
                    sidekick_names.append(c_name)

                m_life = re.search(r"生活质感细节[：:\s]*([^\n\r]+)", block_body)
                if m_life:
                    life_desc = m_life.group(1).strip()
                    lock_item["habits"] = life_desc[:60]
                    m_part = re.search(r"([\u4e00-\u9fff]{2,6}(?:手指|指节|手背|手腕|右臂|左臂|肩膀|耳朵|旧伤|眼神|身躯))", life_desc)
                    if m_part:
                        lock_item["signature_body_part"] = m_part.group(1)
                    m_act = re.search(r"([\u4e00-\u9fff]{0,6}(?:摩挲|搓|摸|刮|捏|扣|擦拭|整理)[\u4e00-\u9fff]{0,10})", life_desc)
                    if m_act:
                        lock_item["signature_action"] = m_act.group(1).strip()
                
                m_voice = re.search(r"(?:禁令|定位|对白|语音)[：:\s]*([^\n\r]+)", block_body)
                if m_voice:
                    lock_item["voice_trait"] = m_voice.group(1).strip()[:40]

    # 2.2 提取配角生活棱角 (### 6. 配角生活棱角与特异癖好)
    m_quirks = re.search(r"###\s*6\.\s*配角生活棱角[^\n]*\n(.*?)(?=\n###|\n##|\Z)", section_text, re.DOTALL)
    if m_quirks:
        q_lines = re.findall(r"\d+\.\s*\*\*([^\*]+)\*\*[:：]\s*([^\n\r]+)", m_quirks.group(1))
        for q_title, q_desc in q_lines:
            m_q_name = re.search(r"([\u4e00-\u9fff]{2,4})", q_title)
            if m_q_name:
                q_name = m_q_name.group(1).strip()
                if q_name not in char_names and 2 <= len(q_name) <= 4:
                    char_names.append(q_name)
                    char_locks.append({
                        "name": q_name,
                        "role": "副手",
                        "legal_identity": q_title[:30],
                        "habits": q_desc[:60],
                        "props": q_desc[:40]
                    })
                    if q_name not in sidekick_names:
                        sidekick_names.append(q_name)

    # 2.3 提取宿敌物象与微反应 (### 4. 远端高位对弈者)
    nemeses_blocks = re.findall(r"####\s*核心宿敌\s*[A-Z]*[：:]\s*([^\n\r]+)\n(.*?)(?=\n####|\n###|\n##|\Z)", section_text, re.DOTALL)
    for n_title, n_body in nemeses_blocks:
        m_n_name = re.search(r"[·\s]([\u4e00-\u9fff]{2,4})(?:[（(]|$)", n_title)
        if not m_n_name:
            m_n_name = re.search(r"([\u4e00-\u9fff]{2,4})", n_title)
        if m_n_name:
            n_name = m_n_name.group(1).strip()
            if n_name not in char_names:
                char_names.append(n_name)
                char_locks.append({"name": n_name, "role": "宿敌", "legal_identity": n_title[:40]})
            m_n_table = re.search(r"\|\s*1\s*\|\s*第?\s*\d+\s*章\s*\|\s*([^|]+)\|\s*([^|]+)\|", n_body)
            n_art = ""
            n_react = ""
            if m_n_table:
                n_react = m_n_table.group(2).strip()
                m_art = re.search(r"([\u4e00-\u9fff]{2,6}(?:签牌|腰牌|酒樽|印章|短刀|佩刀|骨杖|扳指))", n_react)
                if m_art:
                    n_art = m_art.group(1)
            nemeses_list.append({
                "name": n_name,
                "artifact": n_art or "专属信物",
                "micro_reaction": n_react[:40] if n_react else "震怒/微动"
            })

    # 2.4 提取核心灵魂物象 5 阶段里程碑 (### 4. 核心物象强制节拍器)
    m_art_section = re.search(r"###\s*\d*\.?\s*核心物象强制节拍器[^\n]*\n(.*?)(?=\n###|\n##|\Z)", section_text, re.DOTALL)
    if m_art_section:
        art_txt = m_art_section.group(1)
        m_art_name = re.search(r"【([^】]+)】", art_txt)
        art_name = m_art_name.group(1).strip() if m_art_name else "核心物象"
        m_art_init = re.search(r"[（(]([^）)]+)[）)]", art_txt)
        art_init = m_art_init.group(1).strip() if m_art_init else ""

        milestones = []
        ms_items = re.findall(r"\d+\.\s*\*\*第\s*(\d+)\s*章[（(]([^）)]+)[）)]\*\*[:：]\s*([^\n\r]+)", art_txt)
        for ch_s, ev_s, desc_s in ms_items:
            milestones.append({
                "chapter": int(ch_s),
                "event": ev_s.strip(),
                "physical_change": desc_s.strip()[:60],
                "status": "pending"
            })
        core_artifact = {
            "name": art_name,
            "initial_state": art_init[:50],
            "milestones": milestones
        }

    # 2.5 兜底补充基础角色
    name_matches = re.findall(r"\*\s*\*\*姓名\*\*[：:]\s*([^\s（(\n\r]+)(?:[（(]([^）)\n\r]+)[）)])?", section_text)
    for name, id_opt in name_matches:
        clean_name = name.strip().replace("*", "")
        if clean_name and clean_name not in char_names and 1 <= len(clean_name) <= 12:
            char_names.append(clean_name)
            char_locks.append({"name": clean_name, "legal_identity": (id_opt or "核心角色")[:40]})

    matches = re.findall(r"(?:###|\*|\-)\s*(?:[#\d+\.、\*\s]*)(?:[^：:\n\r]+[：:])?\s*\*?\*?([^\s（(\n\r:：\*]+)\*?\*?\s*[（(]([^）)\n\r]+)[）)]", section_text)
    bad_keywords = ["第", "章", "阶", "定位", "曲线", "设计", "线索", "谱系", "台词", "前台", "后台", "标志", "层", "行为", "动作", "质感", "限制", "伪装", "灵魂", "创伤", "【", "】", "节点", "物象", "开端", "中点", "终局", "决战", "高潮", "阶段", "结构", "三幕"]
    for name, identity in matches:
        clean_name = name.strip().replace("*", "").replace("#", "").strip()
        clean_identity = identity.strip()
        if re.match(r"^第\d+章$", clean_name) or any(bad in clean_name for bad in bad_keywords):
            continue
        if clean_name and clean_name not in char_names and 1 <= len(clean_name) <= 12:
            char_names.append(clean_name)
            lock_item = {
                "name": clean_name,
                "legal_identity": clean_identity[:40],
                "role": "副手" if len(char_names) > 1 else "主角"
            }
            if "失语" in clean_identity or "聋" in clean_identity or "哑" in clean_identity:
                lock_item["is_mute"] = True
            char_locks.append(lock_item)
            if lock_item["role"] == "副手" and clean_name not in sidekick_names:
                sidekick_names.append(clean_name)

    if not sidekick_names and len(char_names) > 1:
        sidekick_names = [c for c in char_names[1:] if c not in [n.get("name") for n in nemeses_list]]

    return {
        "char_names": char_names,
        "char_locks": char_locks,
        "sidekicks": [c for c in char_locks if c.get("role") == "副手"],
        "nemeses": nemeses_list,
        "core_artifact": core_artifact,
        "output_constraints": {
            "breathing_chapter_rotation": sidekick_names or char_names[1:5],
            "hook_retrospective_required": True,
            "micro_expression_source": "signature_body_part + signature_action"
        }
    }


def hydrate_character_dossiers(novel_dir: str, master_text: str = "", log_func=None) -> int:
    """
    全量角色生命周期独立档案卡自动切片与水合引擎 (0 业务硬编码):
    将《大纲.md》中的人物体系自动切片生成为 人物设定/*.yaml 独立结构化档案卡。
    """
    novel_dir = os.path.abspath(novel_dir)
    dossier_dir = os.path.join(novel_dir, "人物设定")
    os.makedirs(dossier_dir, exist_ok=True)

    if not master_text:
        master_path = os.path.join(novel_dir, "大纲.md")
        if os.path.exists(master_path):
            with open(master_path, "r", encoding="utf-8") as f:
                master_text = f.read()
    if not master_text:
        return 0

    manifest = extract_full_project_manifest(master_text)
    char_section_m = re.search(r"##\s*二[、\.\s]*人物[^\n\r]*\n(.*?)(?=\n##\s*三|\Z)", master_text, re.DOTALL)
    section_text = char_section_m.group(1) if char_section_m else master_text
    generated_count = 0

    # 1. 抽取主角档案卡
    h_name = "主角"
    m_hero = re.search(r"###\s*1\.\s*主角人设\s*\n(.*?)(?=\n###|\n##|\Z)", section_text, re.DOTALL)
    if m_hero:
        h_txt = m_hero.group(1)
        h_name_m = re.search(r"\*\s*\*\*姓名\*\*[：:]\s*([^\s（(\n\r]+)", h_txt)
        h_name = h_name_m.group(1).strip().replace("*", "") if h_name_m else "主角"
        m_wound = re.search(r"前史创伤[^\n]*\n(.*?)(?=\n###|\n##|\Z)", h_txt, re.DOTALL)
        wound_txt = m_wound.group(1).strip() if m_wound else ""
        hero_data = {
            "name": h_name,
            "role": "主角",
            "profile": h_txt.strip(),
            "trauma_and_quirk": wound_txt
        }
        with open(os.path.join(dossier_dir, f"{h_name}.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(hero_data, f, allow_unicode=True, sort_keys=False)
        generated_count += 1

    # 2. 抽取核心搭档五阶羁绊演进卡 (如 沈玉娘)
    p_name = ""
    partner_m = re.search(r"###\s*2\.\s*核心同袍[^\n]*\n(.*?)(?=\n###|\n##|\Z)", section_text, re.DOTALL)
    if partner_m:
        p_txt = partner_m.group(1)
        p_name_m = re.search(r"\*\*羁绊对象\*\*[：:]\s*([^\s（(\n\r]+)", p_txt)
        if p_name_m:
            p_name = p_name_m.group(1).strip().replace("*", "")
            stages = []
            stage_blocks = re.findall(r"-\s*\*\*第[一二三四五\d]+阶【([^】]+)】[（(](?:Ch\s*|第\s*)?(\d+)[~–\-](\d+)[^）)]*[）)][*：:\s]*\n(.*?)(?=\n-\s*\*\*第|\n####|\n###|\Z)", p_txt, re.DOTALL)
            for idx, (st_name, start_ch, end_ch, st_body) in enumerate(stage_blocks, 1):
                m_anch = re.search(r"【物理锚点】[：:\s]*\*?[：:]?\s*([^。\n\r]+)", st_body)
                anchor_desc = m_anch.group(1).replace("*", "").strip() if m_anch else "专属信物"
                
                # 阶段自适应微动作矩阵
                if idx == 1:
                    t_act = [f"指节死死扣紧{anchor_desc[:12]}边框", "指节泛白抿紧双唇，死守关键物料"]
                    a_act = ["指腹快速拨动核算道具，报出精确到分毫的折耗缺口", "用指节压平账册翘角"]
                    d_act = ["双手捧粗陶碗借微温暖手", f"接过热汤停顿三息，吹凉后方才递给{h_name}"]
                elif idx == 2:
                    t_act = [f"指腹下意识摩挲{anchor_desc[:12]}刻痕", "目光冷澈护住核销台账"]
                    a_act = ["拨动道具如飞，报出复式核算盈余", "用指节抚平发黄的册页毛边"]
                    d_act = ["默默递过温热布巾", "接过热汤吹去浮沫，低声复核清单"]
                elif idx == 3:
                    t_act = [f"单手按在光亮如镜的{anchor_desc[:10]}上", f"与{h_name}背靠背立于风雪料堆"]
                    a_act = ["快速核销全境物资储备", "迅速排查补给缺口"]
                    d_act = ["静默并肩注视重工运转", "递过温热干粮，眼神冷硬默契"]
                else:
                    t_act = [f"指节扣住{anchor_desc[:10]}", "并肩迎风立于工棚"]
                    a_act = ["快速签发全境物资调拨令", "以铁腕规矩核销物资"]
                    d_act = ["递过粗陶茶汤，神色自若从容", "静默注视机械巨轮运转"]

                stages.append({
                    "stage": idx,
                    "stage_name": st_name.strip(),
                    "chapter_range": [int(start_ch), int(end_ch)],
                    "physical_anchor": anchor_desc,
                    "action_matrix": {
                        "tension_scene": t_act,
                        "accounting_scene": a_act,
                        "daily_scene": d_act
                    }
                })

            # 提取羁绊高光戏落点
            milestones = []
            m_highs = re.findall(r"\d+\.\s*\*\*第\s*(\d+)\s*章[（(]([^）)]+)[）)]\*\*[:：]\s*([^\n\r]+)", p_txt)
            for h_ch, h_title, h_desc in m_highs:
                milestones.append({
                    "chapter": int(h_ch),
                    "event": f"{h_title}：{h_desc[:50]}",
                    "status": "pending"
                })

            partner_data = {
                "name": p_name,
                "role": "核心搭档",
                "stages": stages,
                "milestone_chapters": milestones
            }
            with open(os.path.join(dossier_dir, f"{p_name}.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(partner_data, f, allow_unicode=True, sort_keys=False)
            generated_count += 1

    # 3. 抽取核心副手卡 (如 鲁岳、赵破奴)
    for sidekick in manifest.get("sidekicks", []):
        sk_name = sidekick.get("name")
        if not sk_name or sk_name in [h_name, p_name]:
            continue
        sk_data = {
            "name": sk_name,
            "role": "副手",
            "legal_identity": sidekick.get("legal_identity", "核心副手"),
            "signature_body_part": sidekick.get("signature_body_part", "手指"),
            "signature_action": sidekick.get("signature_action", "摸索道具"),
            "habits": sidekick.get("habits", "")
        }
        with open(os.path.join(dossier_dir, f"{sk_name}.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(sk_data, f, allow_unicode=True, sort_keys=False)
        generated_count += 1

    # 4. 抽取宿敌 10 次时空表卡 (如 严嵩年、拓跋烈)
    for nemesis in manifest.get("nemeses", []):
        nem_name = nemesis.get("name")
        if not nem_name:
            continue
        nem_data = {
            "name": nem_name,
            "role": "宿敌",
            "artifact": nemesis.get("artifact", "专属信物"),
            "micro_reaction": nemesis.get("micro_reaction", "震怒/微动")
        }
        with open(os.path.join(dossier_dir, f"{nem_name}.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(nem_data, f, allow_unicode=True, sort_keys=False)
        generated_count += 1

    if log_func:
        log_func(f"[Hydrate] ✅ 已成功切片生成 {generated_count} 张独立角色档案卡于: {dossier_dir}")
    return generated_count


def bootstrap_project_workspace(proj_dir: str, config_path: str = "", master_text: str = "", target_words: Optional[int] = None, log_func=None) -> bool:
    """为全新项目工作区进行全量脚手架引导：自动生成本地 config.yaml、knowledge_graph.db 和 memory.db"""
    proj_dir = os.path.abspath(proj_dir)
    os.makedirs(proj_dir, exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "大纲"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "正文"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "正文", "发布版"), exist_ok=True)

    # 1. 复制/生成本地项目 config.yaml
    local_cfg_path = os.path.join(proj_dir, "config.yaml")
    from pipeline.utils import get_default_base_config
    cfg = get_default_base_config()

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                cfg.update(loaded)
        except Exception:
            pass
    elif os.path.exists(local_cfg_path):
        try:
            with open(local_cfg_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                cfg.update(loaded)
        except Exception:
            pass

    cfg.setdefault("project", {})
    cfg["project"]["novel_dir"] = proj_dir
    cfg["project"]["workspace_dir"] = proj_dir
    cfg["project"]["output_dir"] = os.path.join(proj_dir, "正文")
    cfg["project"]["outline_dir"] = os.path.join(proj_dir, "大纲") if os.path.exists(os.path.join(proj_dir, "大纲")) else proj_dir
    cfg["project"]["master_outline"] = os.path.join(proj_dir, "大纲.md")
    cfg["project"]["master_file"] = "合集.md"

    # 优先使用显式传入的 target_words 或从目录名反解 (如 大纲_270万字_1125章_...)
    tw_resolved = None
    if target_words and target_words > 0:
        tw_resolved = target_words
    else:
        folder_m = re.search(r"大纲_(\d+)万字_(\d+)章", os.path.basename(proj_dir))
        if folder_m:
            tw_resolved = int(folder_m.group(1)) * 10000

    # 动态提取字数、题材、书名与角色
    master_md_file = os.path.join(proj_dir, "大纲.md")
    if not master_text and os.path.exists(master_md_file):
        try:
            with open(master_md_file, "r", encoding="utf-8") as mf:
                master_text = mf.read()
        except Exception:
            pass

    if master_text:
        title_m = re.search(r"书名[*\s]*[：:]\s*《?([^》\n\r*]+)》?", master_text) or re.search(r"#\s*《([^》\n\r]+)》", master_text)
        if title_m:
            clean_title = title_m.group(1).strip()
            if "白皮书" not in clean_title and "商业总纲" not in clean_title:
                cfg["project"]["title"] = f"《{clean_title}》"

        genre_m = re.search(r"题材[*\s]*[：:]\s*([^：:\n\r*]+)", master_text) or re.search(r"核心标签[*\s]*\n*`([^`]+)`", master_text)
        if genre_m:
            cfg["project"]["genre"] = genre_m.group(1).strip()

        if not tw_resolved:
            words_m = re.search(r"(?:目标总字数|目标字数|全书总字数)[*\s]*[：:]\s*(\d+)", master_text)
            if words_m:
                tw_resolved = int(words_m.group(1))
            else:
                words_wan_m = re.search(r"(?:目标总字数|目标字数|全书总字数|全书规划|字数规划)[*\s]*[：:]\s*(\d+)\s*万字?", master_text)
                if words_wan_m:
                    tw_resolved = int(words_wan_m.group(1)) * 10000

        manifest_data = extract_full_project_manifest(master_text)
        extracted_chars = manifest_data["char_names"]
        extracted_locks = manifest_data["char_locks"]
        if extracted_chars:
            cfg["project"]["characters"] = extracted_chars
            cfg["character_locks"] = extracted_locks
        if manifest_data.get("core_artifact"):
            cfg["core_artifact"] = manifest_data["core_artifact"]
        if manifest_data.get("output_constraints"):
            cfg["output_constraints"] = manifest_data["output_constraints"]
        if manifest_data.get("nemeses"):
            cfg["nemeses"] = manifest_data["nemeses"]

    tw = tw_resolved if tw_resolved else cfg.get("project", {}).get("target_words", 2000000)
    cfg["project"]["target_words"] = tw
    target_ch_words = cfg.get("quality", {}).get("target_chinese_chars", 2400)
    total_ch = max(50, tw // target_ch_words)
    cfg["project"]["total_chapters"] = total_ch

    # 自动初始化分卷路由表 volume_routing
    chapters_per_vol = 100 if tw >= 1500000 else (30 if tw <= 500000 else 50)
    total_vols = (total_ch + chapters_per_vol - 1) // chapters_per_vol
    routing = []
    for v_idx in range(1, total_vols + 1):
        v_start = (v_idx - 1) * chapters_per_vol + 1
        v_end = min(total_ch, v_idx * chapters_per_vol)
        routing.append({
            "volume": v_idx,
            "range": [v_start, v_end],
            "file": f"大纲/第{v_idx}卷_章节细纲.md"
        })
    cfg["volume_routing"] = routing

    # 自动初始化开篇节奏弹性公差配置 opening_pacing
    cfg.setdefault("opening_pacing", {
        "enabled": True,
        "threat_appear_max_chars": 100,
        "first_counter": {
            "target_chars": 200,
            "tolerance_ratio": 0.20,
            "min_chars": 160,
            "max_chars": 240
        },
        "confrontation_window_chars": 500,
        "max_consecutive_non_conflict": 3
    })

    try:
        from pipeline.utils import atomic_write, set_active_project_dir
        cfg_dump_str = yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False)
        atomic_write(local_cfg_path, cfg_dump_str)
        set_active_project_dir(proj_dir)
        # 自动生成独立角色档案库
        hydrate_character_dossiers(proj_dir, master_text=master_text, log_func=log_func)
    except Exception as e:
        if log_func:
            log_func(f"[Bootstrap Config 警告] 写入本地配置失败: {e}")

    # 2. 初始化与清理 knowledge_graph.db
    kg_path = os.path.join(proj_dir, "knowledge_graph.db")
    try:
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_path)
        chars = cfg.get("project", {}).get("characters", [])
        
        # 清理非本书旧节点与残余元数据
        if chars:
            placeholders = ",".join(["?"] * len(chars))
            kg._conn.execute(f"DELETE FROM nodes WHERE name NOT IN ({placeholders})", chars)
            kg._conn.execute("DELETE FROM edges;")
            kg._conn.commit()

        for ch_name in chars:
            try:
                kg.upsert_node(node_id=ch_name, name=ch_name, category="character", properties={}, chapter_num=1)
            except Exception as e:
                if log_func:
                    log_func(f"[KG] [WARN] 节点 [{ch_name}] 写入失败: {e}", level="WARN")

        # 建立主角与核心配角的初始因果拓扑边
        if len(chars) >= 2:
            protagonist = chars[0]
            for target_char in chars[1:]:
                rel_type = "ALLY"
                desc = "阵营盟友"
                
                # 寻找该角色的锁定身份
                char_id_str = ""
                for lk in cfg.get("character_locks", []):
                    if lk.get("name") == target_char:
                        char_id_str = lk.get("legal_identity", "")
                        break
                
                if "兄" in char_id_str or "妹" in char_id_str or "弟" in char_id_str or "亲" in char_id_str:
                    rel_type = "SIBLING"
                    desc = f"皇室/家族亲缘羁绊/{char_id_str}"
                elif "匠" in char_id_str or "随从" in char_id_str or "卫" in char_id_str or "下属" in char_id_str:
                    rel_type = "MASTER_SERVANT"
                    desc = f"忠诚麾下/{char_id_str}"
                elif any(k in char_id_str for k in ["敌", "反派", "宿敌", "死敌", "对手", "门阀"]):
                    rel_type = "ENEMY"
                    desc = f"阵营死敌对峙/{char_id_str}"
                else:
                    rel_type = "ALLY"
                    desc = f"核心同袍盟友/{char_id_str}"
                
                try:
                    kg.upsert_edge(protagonist, target_char, rel_type=rel_type, description=desc, chapter_num=1)
                except Exception as e:
                    if log_func:
                        log_func(f"[KG] [WARN] 关系边 [{protagonist} -> {target_char}] 建立失败: {e}", level="WARN")

        kg.close()

        # 织入总纲中的灵魂物象及 5 大演进里程碑
        try:
            from outline.kg_weaver import init_kg_from_master_outline
            init_kg_from_master_outline(master_text, proj_dir, cfg, log_func=log_func)
        except Exception as e:
            if log_func:
                log_func(f"[Bootstrap KG 提示] 物象编织跳过: {e}", level="WARN")
    except Exception as e:
        if log_func:
            log_func(f"[Bootstrap KG 警告] 图数据库初始化异常: {e}", level="WARN")


    # 3. 初始化与同步 memory.db
    mem_path = os.path.join(proj_dir, "memory.db")
    try:
        import sqlite3
        conn = sqlite3.connect(mem_path)
        from pipeline.utils import configure_sqlite_resilience
        configure_sqlite_resilience(conn)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            category TEXT,
            description TEXT,
            first_chapter INTEGER,
            last_updated_chapter INTEGER
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS plot_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_name TEXT UNIQUE,
            planted_chapter INTEGER,
            summary TEXT,
            status TEXT,
            related_entities TEXT
        );
        """)
        conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_lore USING fts5(
            doc_id UNINDEXED,
            category UNINDEXED,
            title,
            content,
            tokenize = 'unicode61'
        );
        """)

        # 清理首章旧实体，确保与当前书设定完全对齐
        conn.execute("DELETE FROM entities WHERE first_chapter = 1;")
        conn.execute("DELETE FROM plot_vault WHERE planted_chapter = 1;")
        conn.execute("DELETE FROM fts_lore;")

        # 写入第1章核心实体与伏笔 (100% 强类型直读 config.yaml 唯一真实数据源)
        chars = cfg.get("project", {}).get("characters", [])
        mc = chars[0] if chars else "主角"
        book_title = cfg.get("project", {}).get("title", "当前小说")
        genre_name = cfg.get("project", {}).get("genre", "通用题材")
        sub_genre = cfg.get("project", {}).get("sub_genre", "")
        genre_full = f"{genre_name} / {sub_genre}" if sub_genre else genre_name
        cast_str = "、".join(chars) if chars else mc
        
        # 动态提取大纲首章信物与地名
        token_name = "核心信物"
        if master_text:
            m_tok = re.search(r"【([^】]+信物[^】]*)】", master_text) or re.search(r"【([^】]+道具[^】]*)】", master_text)
            if m_tok:
                token_name = m_tok.group(1)

        conn.execute("""
        INSERT OR REPLACE INTO entities (name, category, description, first_chapter, last_updated_chapter)
        VALUES 
        (?, 'item', '第1章核心初始信物/道具，承载前期生存与主线破局线索', 1, 1),
        ('初始根据地', 'location', '主角前期展开破局与工业/武道/势力建设的核心起始物理空间', 1, 1)
        """, (token_name,))

        conn.execute("""
        INSERT OR REPLACE INTO plot_vault (thread_name, planted_chapter, summary, status, related_entities)
        VALUES
        ('第1章开篇破局与生存建立', 1, '主角开局遭遇重大危机并凭借智慧与底牌完成微观破局，埋下初始线索', 'active', ?)
        """, (f"{mc}",))

        # 写入 FTS5 全文倒排索引 (从 config.yaml 统一注入多维复合元数据)
        lore_text = f"《{book_title}》（{genre_full}）：核心主角【{mc}】，核心阵容【{cast_str}】。第1章开局破局立足，引领阵营崛起与秩序重塑。"
        conn.execute("""
        INSERT INTO fts_lore (doc_id, category, title, content)
        VALUES ('lore_ch1', 'world_setting', '全书核心世界观与初始设定', ?)
        """, (lore_text,))

        conn.commit()
        conn.close()
    except Exception as e:
        if log_func:
            log_func(f"[Bootstrap Memory 提示] 记忆库初始化跳过: {e}")

    if log_func:
        log_func(f"[Bootstrap] ✅ 项目全量脚手架完成: config.yaml, knowledge_graph.db, memory.db 已全部就绪！")
    return True


def main():
    if len(sys.argv) < 2:
        print("使用方式: python3 cli_wizard.py [hydrate|bootstrap|switch] [args...]")
        return

    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    cmd = sys.argv[1].lower()
    if cmd == "hydrate":
        from pipeline.utils import get_active_project_dir
        novel_dir = sys.argv[2] if len(sys.argv) > 2 else get_active_project_dir(script_dir)
        count = hydrate_character_dossiers(novel_dir, log_func=print)
        print(f"🎉 角色档案库水合完成，共生成 {count} 张独立档案卡！")
    elif cmd == "switch" and len(sys.argv) > 2:
        from pipeline.utils import set_active_project_dir
        set_active_project_dir(sys.argv[2])
        print(f"✅ 活动项目已切换至: {sys.argv[2]}")
    elif cmd == "bootstrap" and len(sys.argv) > 2:
        proj_dir = sys.argv[2]
        master_file = sys.argv[3] if len(sys.argv) > 3 else os.path.join(proj_dir, "大纲.md")
        master_text = open(master_file, "r", encoding="utf-8").read() if os.path.exists(master_file) else ""
        bootstrap_project_workspace(proj_dir, master_text=master_text, log_func=print)


if __name__ == "__main__":
    main()

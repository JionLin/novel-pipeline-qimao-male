# -*- coding: utf-8 -*-
"""
outline/master_generator.py - 全书总纲生成与题材矩阵引擎
包含：
1. 题材矩阵加载与扩展扫描 (load_genre_matrix)
2. 总纲核心上下文与三幕沙盘提取 (extract_targeted_master_context / extract_macro_phase_anchor)
3. 灵魂黑夜与因果钩子提取 (extract_dark_night_prelude_chapter / extract_fallback_hooks_from_master)
4. 白金总纲生成引擎 (generate_master_outline)
5. 大纲至 config.yaml 安全回写同步 (safe_patch_config_from_outline)
"""

import os
import glob
import re
import yaml
from typing import Dict, Any, List, Optional, Tuple


def load_genre_matrix(script_dir: str = "", log_func=None) -> Dict[str, Any]:
    """加载内置商业题材矩阵，并自动热扫描合并 scripts/genres/*.yaml 扩展包"""
    if not script_dir:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    matrix = {

        "1": {
            "name": "玄幻修仙 / 东方幻想",
            "subgenres": {
                "1": {
                    "name": "万倍暴击 / 授徒返还底层逆袭流",
                    "recommended_words": 300000,
                    "target_chapters": 125,
                    "formula": "【高冲突动作/强反差身份】+【万倍暴击/颠覆反转】",
                    "core_appeal": "底层草芥装孙子与翻脸反差、相依为命情感羁绊、信息差降维打击",
                    "specific_rules": "- 必须严格遵守【暴击时序延时】与主角自身的打坐自修打磨协议；\n- 关键赌注/宝物必须承载反派命门死穴；\n- 随从展现天赋时必须安排第三方巨擘重金利诱试金石；\n- A类章节双绳索绑定生存危机与救赎羁绊，B类章节重在温情沉淀与暗线布局。",
                    "default_idea": "杂役开局阳寿只剩3月，误打误撞强喂走火入魔女掌门一颗泥丸，触发万倍返还！"
                },
                "2": {
                    "name": "苟道长生 / 稳健幕后种田流",
                    "recommended_words": 600000,
                    "target_chapters": 250,
                    "formula": "【隐忍苟道/幕后寿命】+【岁月熬敌/暴富打脸】",
                    "core_appeal": "无限寿命谨慎发育、幕后培育神树灵脉、熬死仇敌三代后再去上坟",
                    "specific_rules": "- 绝不轻易涉险，遇事谋定后动，重点描写时间流逝下的沧海桑田；\n- 幕后布局打脸，绝不在人前暴露全貌；\n- 每次破境必须付出具体的岁月磨砺代价。",
                    "default_idea": "穿越获得长生不老道果，只要不作死就能永生，在修仙界杂役院低调种田三万年。"
                }
            }
        },
        "2": {
            "name": "都市生活 / 异能神豪",
            "subgenres": {
                "1": {
                    "name": "神豪返现 / 极速装逼打脸流",
                    "recommended_words": 200000,
                    "target_chapters": 80,
                    "formula": "【阶层降维/现世装逼】+【万亿神豪/绝对反杀】",
                    "core_appeal": "极致花钱返现、社会阶层降维打击、现世恶人光速破防",
                    "specific_rules": "- 每章必须规划具体的现实消费物件、社会关系蔑视与现世打脸；\n- 狠话必须落在具体资产与合同上；\n- 挥霍必须伴随实体产业吞并与阶层颠覆。",
                    "default_idea": "被拜金女友分手当天，觉醒万亿神豪返现系统，给高颜值异性花钱十倍暴击返现！"
                }
            }
        }
    }

    # 热扫描 genres 扩展目录
    genres_dir = os.path.join(script_dir, "genres")
    if os.path.exists(genres_dir):
        ext_files = glob.glob(os.path.join(genres_dir, "*.yaml"))
        for ef in ext_files:
            try:
                with open(ef, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and "category_id" in data and "subgenre_id" in data:
                    cat_id = str(data["category_id"])
                    sub_id = str(data["subgenre_id"])
                    if cat_id not in matrix:
                        matrix[cat_id] = {"name": data.get("category_name", "自定义分类"), "subgenres": {}}
                    matrix[cat_id]["subgenres"][sub_id] = data
            except Exception as e:
                if log_func:
                    log_func(f"[Genre Matrix] [WARN] 题材配置文件 [{os.path.basename(ef)}] 解析失败: {e}，跳过加载", level="WARN")

    return matrix



def extract_targeted_master_context(master_text: str, start_ch: int, end_ch: int, target_words: int) -> str:
    """从全书总纲中通用自适应提取当前章节批次的核心设定、人物谱系与对应分卷梗概，0 业务硬编码"""
    if not master_text:
        return "（无总纲）"

    extracted_blocks = []

    # 1. 提取前言与核心设定（前 120 行）
    top_lines = master_text.splitlines()[:100]
    extracted_blocks.append("\n".join(top_lines))

    # 2. 智能定位当前章节所属的分卷梗概
    # 匹配 `### 【卷X...】（第 A ~ B 章）` 或 `## 卷X`
    vol_matches = list(re.finditer(r"(?:###?\s*【?卷[一二三四五六七八九十\d]+[^】\n\r]*】?|##\s*分卷梗概)[^\n\r]*", master_text))
    matched_vol_text = ""
    for i, vm in enumerate(vol_matches):
        start_idx = vm.start()
        end_idx = vol_matches[i + 1].start() if i + 1 < len(vol_matches) else len(master_text)
        block = master_text[start_idx:end_idx]

        # 检查该卷是否覆盖 start_ch
        range_m = re.search(r"第\s*(\d+)\s*[-~至到]\s*(\d+)\s*章", block)
        if range_m:
            v_start, v_end = int(range_m.group(1)), int(range_m.group(2))
            if v_start <= start_ch <= v_end:
                matched_vol_text = block.strip()
                break
        elif f"第 1 " in block or "卷一" in block or "第一卷" in block:
            if start_ch <= 85:
                matched_vol_text = block.strip()
                break

    if matched_vol_text:
        extracted_blocks.append(f"\n【🎯 当前批次所属分卷核心剧情与战役】：\n{matched_vol_text}")

    # 3. 提取人物档案
    char_match = re.search(r"(?:##\s*三[、\.]|##\s*人物|##\s*核心人物)[^\n]*\n(.*?)(?=\n##|\Z)", master_text, re.DOTALL)
    if char_match:
        extracted_blocks.append(f"\n【👥 核心人物档案与声线】：\n{char_match.group(1)[:1500].strip()}")

    return "\n\n".join(extracted_blocks)


def extract_macro_phase_anchor(master_text: str, current_start: int, total_chapters: int) -> str:
    """提取当前章节批次在总纲三幕大纲中的宏观定位"""
    if not master_text:
        return "第一幕：常规推进"
    act1_end = int(total_chapters * 0.15)
    act2_end = int(total_chapters * 0.80)

    if current_start <= act1_end:
        return f"【第一幕·开端（第1-{act1_end}章）】：打破日常、生存危机与初始根据地建立"
    elif current_start <= act2_end:
        mid_point = int((act1_end + act2_end) / 2)
        if current_start < mid_point:
            return f"【第二幕前段·发展上升（第{act1_end+1}-{mid_point}章）】：工商业布局、小规模冲突与技术质押"
        else:
            return f"【第二幕后段·中点反转与绝境（第{mid_point+1}-{act2_end}章）】：宿敌全面反扑、至暗时刻与灵魂黑夜"
    else:
        return f"【第三幕·终局决战（第{act2_end+1}-{total_chapters}章）】：大高潮反杀、旧秩序覆灭与最终加冕"


def extract_dark_night_prelude_chapter(master_text: str, total_chapters: int) -> Optional[int]:
    """从总纲三幕九拍中提取灵魂黑夜引用的前奏错误决策章节号"""
    m = re.search(r'灵魂黑夜.*?第\s*(\d+)\s*章', master_text, re.DOTALL)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return None


def extract_fallback_hooks_from_master(master_text: str) -> List[str]:
    """从总纲第九板块提取因果钩子"""
    hooks = []
    lines = master_text.splitlines()
    for l in lines:
        if "|" in l and not l.startswith("|-") and not l.startswith("| 道具") and not l.startswith("| 表面"):
            parts = [p.strip() for p in l.split("|") if p.strip()]
            if len(parts) >= 3:
                hooks.append(f"【总纲伏笔】道具/事件: {parts[0]} (命门: {parts[1]}, 回收: {parts[2]})")
    return hooks[:10]


def generate_master_outline(
    genre_prompt: str,
    target_words: int,
    client,
    model_name: str,
    cfg: Dict[str, Any],
    output_path: str = "",
    log_func=None
) -> str:
    """生成全书白金总纲（严格按 2400字/章 推导总章数与三幕沙盘，max_tokens=16384）"""
    target_ch_words = cfg.get("quality", {}).get("target_chinese_chars", 2400)
    total_chapters = max(50, target_words // target_ch_words)
    
    macro_ratios = cfg.get("structure", {}).get("macro_three_act_ratio", {})
    r1 = macro_ratios.get("act1", 0.15)
    r2 = macro_ratios.get("act2", 0.65)
    r3 = macro_ratios.get("act3", 0.20)

    act1_end = max(15, int(total_chapters * r1))
    act2_end = max(act1_end + 30, int(total_chapters * (r1 + r2)))
    act3_start = act2_end + 1
    act2_span = act2_end - act1_end

    # 动态自适应推导：第二幕清算步长、节点数与宿敌互动频次
    checkpoint_step = max(15, int(total_chapters * 0.06))
    checkpoint_step_min = max(10, checkpoint_step - 5)
    checkpoint_step_max = checkpoint_step + 10
    act2_min_checkpoints = max(3, int(act2_span / checkpoint_step_max))

    nemesis_max_gap = max(20, int(total_chapters * 0.10))
    nemesis_min_count = max(4, int(total_chapters / nemesis_max_gap))

    vol_count = max(2, round(total_chapters / 85))
    vol1_end = act1_end

    if log_func:
        log_func(f"[Auto-Outline] 开始构思全书总纲: {genre_prompt[:40]}... (目标: {target_words}字 ➔ {total_chapters}章, 第二幕清算步长: {checkpoint_step_min}~{checkpoint_step_max}章, 宿敌最大间隔: ≤{nemesis_max_gap}章)")

    axioms = cfg.get("gravity_axioms", [])
    axioms_text = "\n".join([f"- {a}" for a in axioms]) if axioms else "遵循通用文学因果守恒定律"

    math_sand_table = f"""【🎯 严格章节沙盘规划（必须 100% 遵守，严禁使用 300 章模板！）】：
- 全书目标总字数：{target_words} 字
- 严格标准单章字数：{target_ch_words} 字/章
- 🎯 全书总章数：整整【{total_chapters}】章（建议分卷：约 {vol_count} 卷）
- 篇幅三幕沙盘分布：
  * 第一幕（开端）：第 1 章 ~ 第 {act1_end} 章（占{int(r1*100)}%）
  * 第二幕（对抗）：第 {act1_end + 1} 章 ~ 第 {act2_end} 章（占{int(r2*100)}%，中点大反转位于第 {int((act1_end + act2_end) / 2)} 章左右）
    - 第二幕清算密度：每隔 {checkpoint_step_min} ~ {checkpoint_step_max} 章必须设 1 个清算节点（全幕不少于 {act2_min_checkpoints} 个）
  * 第三幕（决战）：第 {act3_start} 章 ~ 第 {total_chapters} 章（占{int(r3*100)}%，终局收官于第 {total_chapters} 章）
- 核心宿敌跨时空互动：全书不少于 {nemesis_min_count} 次，任意两节点间隔 ≤ {nemesis_max_gap} 章"""

    novel_dir = cfg.get("project", {}).get("novel_dir", "")
    from pipeline.prompt_loader import load_prompt
    raw_prompt = load_prompt("01_master_outline", custom_dir=novel_dir, log_func=log_func)
    user_prompt = raw_prompt.format(
        book_title=cfg.get("project", {}).get("title", "未命名"),
        genre_name=genre_prompt[:30],
        core_selling_point=cfg.get("project", {}).get("selling_point", "工业降维碾压"),
        core_idea=genre_prompt,
        target_words=target_words,
        total_chapters=total_chapters,
        genre_prompt=genre_prompt,
        math_sand_table=math_sand_table,
        act1_end=act1_end,
        act2_start=act1_end + 1,
        act2_end=act2_end,
        act2_span=act2_span,
        checkpoint_step_min=checkpoint_step_min,
        checkpoint_step_max=checkpoint_step_max,
        act2_min_checkpoints=act2_min_checkpoints,
        nemesis_max_gap=nemesis_max_gap,
        nemesis_min_count=nemesis_min_count,
        vol1_end=vol1_end
    )

    max_tokens_val = cfg.get("models", {}).get("planner", {}).get("max_tokens", 8192)
    from pipeline.utils import safe_chat_completion

    # 【两段式 Pass 1 + Pass 2 串行生成与无损合并】
    if log_func:
        log_func("[Auto-Outline] [Pass 1/2] 正在编译全案大纲底层设定基座 (板块一 ~ 四)...")

    prompt_pass1 = user_prompt + "\n\n【本阶段执行指令】：本次为 [Pass 1/2]，请全力精雕【板块一·商业定位】、【板块二·人物体系与羁绊】、【板块三·工业/体系进化树与物资守恒】、【板块四·势力图谱与利益拓扑】前四大底层设定基座，暂不输出分卷与战役。\n"

    result_pass1 = safe_chat_completion(
        client=client,
        model=model_name,
        messages=[
            {"role": "system", "content": "你是一位顶级商业网文总策划。请输出高质量前四大底层设定板块。"},
            {"role": "user",   "content": prompt_pass1},
        ],
        temperature=0.7,
        max_tokens=max_tokens_val,
        max_retries=3,
        log_func=log_func
    )

    if log_func:
        log_func("[Auto-Outline] [Pass 2/2] 正在基于设定基座编译全书时间线沙盘与分卷大纲 (板块五 ~ 八)...")

    prompt_pass2 = f"""请根据以下已确立的【前四大底层设定基座】，继续输出剩余的【板块五·三幕结构沙盘】、【板块六·第1~8卷分卷节奏与爽点编排】、【板块七·五感意象与物价表】、【板块八·三大里程碑高潮战役工程参数卡】！

【已锁定的前四大底层设定基座】：
{result_pass1}

【严格格式与分卷约束】：
- 第1卷（前50章）按单/双章级精密节点展开；
- 第2卷至终卷严格按每 10~15 章一个独立进阶单元编排，绝不偷工减料；
- 第八板块三大战役必须严格按 7 维高浓度战役工程参数卡输出，严禁输出大段散文正文！
"""

    result_pass2 = safe_chat_completion(
        client=client,
        model=model_name,
        messages=[
            {"role": "system", "content": "你是一位顶级商业网文总策划。请基于前文设定输出后半部分分卷与战役大纲。"},
            {"role": "user",   "content": prompt_pass2},
        ],
        temperature=0.7,
        max_tokens=max_tokens_val,
        max_retries=3,
        log_func=log_func
    )

    # 内存自动无缝合并
    result = f"{result_pass1.strip()}\n\n---\n\n{result_pass2.strip()}\n"

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        from pipeline.utils import atomic_write
        atomic_write(output_path, result)
        if log_func:
            log_func(f"[Auto-Outline] ✅ 全书总纲已成功落盘保存: {output_path}")

        # 自动脚手架全量初始化 (config.yaml, knowledge_graph.db, memory.db)
        try:
            from outline.cli_wizard import bootstrap_project_workspace
            bootstrap_project_workspace(out_dir, master_text=result, target_words=target_words, log_func=log_func)
        except Exception as e:
            if log_func:
                log_func(f"[Bootstrap 警告] 自动脚手架初始化异常: {e}", level="WARN")


    return result



def safe_patch_config_from_outline(master_text: str, config_path: str, log_func=None) -> None:
    """从生成的大纲中安全提取关键设定与分卷路由，写回 config.yaml"""
    if not os.path.exists(config_path):
        return
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        # 提取书名
        title_m = re.search(r"书名[*\s]*[：:]\s*《?([^》\n\r*]+)》?", master_text) or re.search(r"#\s*《([^》\n\r]+)》", master_text)
        if title_m:
            clean_title = title_m.group(1).strip()
            if "白皮书" not in clean_title and "商业总纲" not in clean_title:
                cfg.setdefault("project", {})["title"] = f"《{clean_title}》"

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        if log_func:
            log_func(f"[Config Patch] ✅ 已同步大纲核心参数至 {os.path.basename(config_path)}")
    except Exception as e:
        if log_func:
            log_func(f"[Config Patch 警告] 同步配置失败: {e}")

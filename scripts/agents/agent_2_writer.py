# ============================================================
# Agent 2: 核心主笔 Agent (Writer) — v7.0 情绪心流自由版 (Emotion Flow Engine)
# 彻底解除死板四幕与固定字数捆绑，由大纲情绪驱动，0 业务硬编码
# ============================================================

import time
import random
from typing import Optional

try:
    from pipeline.utils import sanitize_vulgar_and_cliches, sanitize_fictional_props
except ImportError:
    from .utils import sanitize_vulgar_and_cliches, sanitize_fictional_props

from pipeline.prompt_loader import load_prompt


def run_writer(
    task_prompt: str,
    client,
    model_name: str,
    base_temp: float = 0.55,
    chapter_outline: str = "",
    system_prompt: str = "",
    novel_dir: Optional[str] = None,
    cfg: Optional[dict] = None,
    log_func=None
) -> str:
    """Writer 深度精写单章（洋葱分层 System Prompt + 动态控温 + 流式自适应降级）"""
    genre_name = (cfg.get("project", {}).get("genre") or cfg.get("novel", {}).get("genre") or cfg.get("genre", "")) if cfg else ""
    if not system_prompt:
        base_writer_prompt = load_prompt("04_writer", custom_dir=novel_dir)
        from pipeline.prompt_loader import load_genre_prose_card
        genre_card = load_genre_prose_card(genre_name, custom_dir=novel_dir, log_func=log_func)
        sys_prompt = base_writer_prompt.replace("{genre_prose_card_content}", genre_card)
    else:
        sys_prompt = system_prompt

    # 动态读取 max_tokens 配置
    max_tokens_val = 8192
    if cfg and isinstance(cfg, dict):
        max_tokens_val = cfg.get("models", {}).get("writer", {}).get("max_tokens", 8192)

    # 章节类型自适应动态控温 (Adaptive Temperature Annealing)
    temp = base_temp
    if chapter_outline:
        if any(k in chapter_outline for k in ["A类", "智斗", "算账", "C类", "工业", "造物", "冶炼", "制药", "锻造"]):
            temp = max(0.45, base_temp - 0.10)  # 智斗与工业攻关：严谨精密、公差优先
        elif any(k in chapter_outline for k in ["B类", "动作", "生死一线", "代差碾压", "F类", "复合高潮", "死战", "决战", "全歼", "斩杀"]):
            temp = max(0.40, base_temp - 0.15)  # 单场动作与复合高潮：快攻凌厉、短句密集
        elif any(k in chapter_outline for k in ["D类", "人物关系", "冷硬默契", "温存", "E类", "过渡", "呼吸", "休整", "分食", "小酌"]):
            temp = min(0.75, base_temp + 0.10)  # 人物关系与战后呼吸：升温释放、微动作与生活五感更丰富

    channel = (cfg.get("project", {}).get("channel") or cfg.get("novel", {}).get("channel") or "") if cfg else ""
    is_female = (channel == "female" or "female" in genre_name or "言情" in genre_name or "种田" in genre_name or "甜宠" in genre_name)

    # 针对 C 类工业制造/造物章节，追加工业首次验证 3 步失效链强提醒 (防止长窗口规则稀释，女频频道豁免)
    final_task_prompt = sanitize_fictional_props(task_prompt)
    if not is_female and chapter_outline and any(k in chapter_outline for k in ["C类", "工业", "造物", "试制", "研发", "冶炼", "制药", "锻造", "图纸"]):
        failure_chain_reminder = (
            "\n\n【⚠️ 工业造物/首次验证 3 步失效链强制提醒】：\n"
            "本章涉及工业研发、造物试制或新技术首次验证，正文严禁一试即成的无尘工业！\n"
            "必须严格遵循三步失效链推进：①【首次尝试与初始参数设定】➔ ②【出现物理偏差/公差失误/材料裂损/阻滞】➔ ③【分析微观机理并改用方案调整修正】。\n"
        )
        if "3 步失效链" not in final_task_prompt and "三步失效链" not in final_task_prompt:
            final_task_prompt = final_task_prompt.rstrip() + failure_chain_reminder

    # 针对 B/F 类动作高潮及重大破局章节，追加远端对弈者情绪心电图与打脸闭环强提醒 (女频生活流豁免)
    if not is_female and chapter_outline and any(k in chapter_outline for k in ["B类", "F类", "大捷", "反杀", "破局", "大胜", "试射成功", "公差反杀"]):
        remote_echo_reminder = (
            "\n\n【⚠️ 远端对弈者情绪心电图与打脸闭环强制提醒】：\n"
            "本章若完成前线破局/大捷/反杀，正文必须在适当位置（或章末收束前）嵌入不多于 150 字的远端高位宿敌（如帝王/幕后主谋）同步反应镜头！\n"
            "必须包含：①专属灵魂物象微观状态（如玉圭铜绿/御案密折）、②生理/环境温差微动作（如朱砂笔洇墨/茶盏捏裂）、③符合人设的克制震荡台词。\n"
        )
        if "情绪心电图" not in final_task_prompt:
            final_task_prompt = final_task_prompt.rstrip() + remote_echo_reminder

    if log_func:
        log_func(f"[Writer] 开始深度精写... (模型: {model_name} 自适应temp={temp:.2f} max_tokens={max_tokens_val})")

    max_stream_attempts = 3
    last_result = ""
    for attempt in range(1, max_stream_attempts + 1):
        try:
            is_stream = (attempt < max_stream_attempts)
            if is_stream:
                resp = client.chat.completions.create(
                    model=model_name,
                    temperature=temp,
                    max_tokens=max_tokens_val,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user",   "content": final_task_prompt},
                    ],
                    stream=True
                )
                full_text = []
                for chunk in resp:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_text.append(content)
                result = "".join(full_text)
            else:
                if log_func:
                    log_func(f"[Writer] ⚡ 启用阻塞式降级拉取 (Blocking Fallback, 稳定性100%)...")
                resp = client.chat.completions.create(
                    model=model_name,
                    temperature=temp,
                    max_tokens=max_tokens_val,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user",   "content": final_task_prompt},
                    ],
                    stream=False
                )
                result = resp.choices[0].message.content or ""

            last_result = result
            blocked_keywords = ["blocked by", "safety filter", "content moderation", "policies.google.com", "unable to process this request due to safety"]
            if not result or len(result) < 1800 or any(bk in result.lower() for bk in blocked_keywords):
                raise ValueError(f"输出异常/过短/触发安全策略截断 ({len(result)} 字符)")

            # 0ms 直出确定性平滑净化（提前剔除微小套话与粗口，降低质检误伤重试率）
            result = sanitize_vulgar_and_cliches(result)

            if log_func:
                log_func(f"[Writer] 写作完成 (生成 {len(result)} 字符)")
            return result
        except Exception as e:
            # 自动注入文学脱敏修辞指引
            literary_euphemism_reminder = (
                "\n\n【⚠️ 纯文学虚构安全修辞提醒】：\n"
                "请注意：本章中涉及的所有化学反应、药物提纯、爆破或物理冶炼，必须使用古代工匠/玄奇小说的虚构文学修辞进行表述（如‘寒潭析晶/明矾凝露/矿盐结晶’）！"
                "绝对严禁输出任何现实危险品、有毒化合物的具体真实化学名称、分子式、真实配比参数或现代工业化学制备流程，以纯文学剧情与艺术效果为主！"
            )
            if literary_euphemism_reminder not in final_task_prompt:
                final_task_prompt = final_task_prompt.rstrip() + literary_euphemism_reminder

            if attempt == max_stream_attempts:
                if log_func:
                    log_func(f"[Writer] ⚠️ 写作连续 {max_stream_attempts} 次失败: {e}")
                if any(bk in last_result.lower() for bk in ["blocked by", "safety filter", "policies.google.com"]):
                    raise RuntimeError(f"主笔连续触发上游模型安全策略拦截，已阻断残篇落盘: {e}")
                return last_result
            backoff = min(20.0, (2 ** attempt) + random.uniform(0.5, 1.5))
            if log_func:
                log_func(f"[Writer] ⚠️ 写作异常 (第{attempt}次): {e}，安全退避 {backoff:.1f}s 后重试...")
            time.sleep(backoff)
    return last_result

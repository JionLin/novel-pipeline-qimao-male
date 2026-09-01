# 📚 genres 目录：商业热门文体特征配方库

`genres` 目录收录了 16 种针对主流网文平台（七猫中文网、番茄小说、起点中文网）调优的商业爆款文体特征配方文件（YAML 格式）。

---

## 📂 包含的 16 种商业文体配方

```
genres/
├── qimao_history_fief_prince.yaml         # 七猫·历史架空·就藩封王争霸流
├── qimao_industrial_military_era.yaml     # 七猫·工业革命·近代军工种田流
├── qimao_game_lord.yaml                   # 七猫·第四天灾·领主建设流
├── qimao_martial_slave_warrior.yaml       # 七猫·高武玄幻·死士奴隶逆袭流
├── qimao_urban_dragon_exwife.yaml         # 七猫·都市战神·逆袭打脸流
├── qimao_villain_heart_steal.yaml         # 七猫·反派逆袭·夺笋气运之子流
├── fanqie_apocalypse_hoard_shelter.yaml   # 番茄·末日天灾·百亿物资安全屋流
├── fanqie_heart_mind_voice_emperor.yaml   # 番茄·心声暴露·女帝/文武百官偷听流
├── fanqie_god_slayer_urban.yaml           # 番茄·都市高武·斩神异能流
├── fanqie_infinity_death_game.yaml        # 番茄·无限惊悚·规则怪谈生死游戏流
├── fanqie_sever_family_money.yaml         # 番茄·断绝关系·全家后悔莫及流
├── qidian_clan_xuanjian_cultivation.yaml  # 起点·家族修仙·玄鉴仙族群像流
├── qidian_mystic_potion_sequence.yaml     # 起点·诡秘克苏鲁·魔药途径序列流
├── qidian_proficiency_martial_god.yaml    # 起点·熟练度面板·苟道长生武圣流
├── qidian_corpse_retriever_folk.yaml      # 起点·民俗悬疑·捞尸缝尸九流禁忌
└── qidian_era_restaurant_life.yaml        # 起点·年代年代文·国营小饭馆日常烟火
```

---

## ⚙️ 配方 YAML 结构规范与自定义扩展

每个文体配方均包含以下标准化字段，支持随时新增自定义配方：

```yaml
name: "文体显示名称"
platform: "qimao" # qimao / fanqie / qidian
core_selling_point: "核心商业爽点一句话概述"
pacing:
  opening_chapters: "前3章黄金破局约束"
  three_act_ratio: "推荐三幕宏观比例"
style_keywords:
  - "特色物候比喻"
  - "时代俚语与口语规范"
```

---

## 🚀 如何在开书时调用文体配方？

在命令行生成总纲时，可通过 `auto_outline.py` 传入文体描述或直接引用配方特征：
```bash
python3 auto_outline.py master "根据 genres/qimao_industrial_military_era.yaml 进行工业争霸大纲设计" 2700000
```

# F1 Dashboard

一个基于 [FastF1](https://github.com/theOehrly/Fast-F1) 数据的本地 F1 赛季仪表盘

## 功能

- **赛程总览**：2026 赛季全部分站，自动识别当前 / 下一站大奖赛
- **积分榜**：车手 / 车队积分实时累计（含冲刺赛积分与分站冠军数）
- **排位赛 / 正赛成绩**：Q1–Q3 分段成绩、与杆位差距、正赛完赛时间与差距
- **杆位圈 / 最快圈卡片**：三段计时、尾速、与去年同站对比
- **WDC 理论夺冠分析**：剩余赛程最高可得积分、谁仍有理论夺冠可能
- **AI 预测**：输入自己的 DeepSeek 或 Kimi API Key，生成登台 / 总冠军 / 看点车手预测

## 开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 拉取最新赛季数据（首次较慢，会在 .fastf1_cache/ 建立缓存）
python fetch_f1_data.py

# 3. 启动本地服务
python f1-server.py
```

然后打开 http://127.0.0.1:5500/f1-dashboard.html

Windows 下也可以直接双击：

- `update.bat` — 更新数据
- `start-server.bat` — 启动服务并自动打开浏览器

> 拉其他年份的数据：`python fetch_f1_data.py 2025`

## 项目结构

```
├── f1-dashboard.html    # 仪表盘主页面（单文件前端）
├── f1-server.py         # 本地 HTTP 服务 + /api/current + /api/ai-predict
├── fetch_f1_data.py     # FastF1 数据抓取 → data.json
├── data.json            # 最近一次抓取的数据快照
├── f1-logo.svg          # 页面图标
└── analysis/            # 遥测分析脚本（matplotlib 出图）
    ├── track_speed_map.py
    ├── gear_shifts_on_track.py
    ├── lap_distribution.py
    └── q3_speed_compare.py
```

## 说明

- `fonts/` 未包含在仓库中（Google Sans / Formula 1 Black 为商业授权字体）。缺失时回到系统字体；如有授权可自行放入 `fonts/` 。
- `.fastf1_cache/` 为 FastF1 本地缓存，首次运行自动生成。
- AI 预测的 API Key 仅在浏览器端输入,不会被保存。

## 免责

本项目为个人学习项目，与 Formula 1、FIA 及各车队无任何隶属或授权关系。数据来自 FastF1 提供的公开计时数据。

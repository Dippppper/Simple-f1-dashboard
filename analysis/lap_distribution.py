#!/usr/bin/env python3
"""
F1 车手圈速分布可视化 (官方风格)
- 小提琴图 + 蜂群散点
- 散点按轮胎类型着色（SOFT 红 / MEDIUM 黄 / HARD 白）
- 小提琴体按车队色着色
- 车手名下方显示最快/最慢圈速
- 深色背景

用法:
  python lap_distribution.py 2024 Bahrain Q VER LEC NOR
  python lap_distribution.py 2023 Azerbaijan R
  python lap_distribution.py 2024 Monaco R --drivers all
"""

import argparse
import os
import sys

import fastf1
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# FastF1 cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".fastf1_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

# 轮胎颜色 (官方颜色)
COMPOUND_COLORS = {
    "SOFT": "#ff3333",
    "MEDIUM": "#ffd700",
    "HARD": "#ffffff",
    "INTERMEDIATE": "#39b54a",
    "WET": "#00aaff",
}


def get_lap_data(session, drivers):
    """获取所有车手的有效计时圈"""
    if len(drivers) == 1 and drivers[0].upper() == "ALL":
        laps = session.laps.copy()
    else:
        laps = session.laps.pick_drivers(drivers).copy()

    # 只保留有效计时圈
    laps = laps.loc[laps["LapTime"].notna()].copy()
    laps["LapTimeSec"] = laps["LapTime"].dt.total_seconds()

    # 找出每个车手的最快圈
    fastest = []
    for drv in laps["Driver"].unique():
        drv_laps = laps[laps["Driver"] == drv]
        if len(drv_laps) > 0:
            best = drv_laps.loc[drv_laps["LapTimeSec"].idxmin()]
            fastest.append(best)
    fastest_df = pd.DataFrame(fastest)

    return laps, fastest_df


def plot_lap_distribution(session, laps, fastest_df, save_path=None):
    """绘制官方风格的圈速分布图"""
    # 按最快圈速排序
    fastest_df = fastest_df.sort_values("LapTimeSec").reset_index(drop=True)
    drivers = fastest_df["Driver"].tolist()
    n = len(drivers)

    # 准备每个车手的数据
    driver_data = {}
    for d in drivers:
        times = laps.loc[laps["Driver"] == d, "LapTimeSec"].dropna().values
        compounds = laps.loc[laps["Driver"] == d, "Compound"].fillna("HARD").values
        driver_data[d] = {"times": times, "compounds": compounds}

    # 颜色
    driver_colors = {}
    for d in drivers:
        try:
            driver_colors[d] = fastf1.plotting.get_driver_color(d, session)
        except Exception:
            driver_colors[d] = "#888888"

    # 暗色主题
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(max(10, n * 1.5), 7), facecolor="#1a1a1a")
    ax.set_facecolor("#1a1a1a")

    # -----------------------------
    # 1. 小提琴图（按车队色）
    # -----------------------------
    data = [driver_data[d]["times"] for d in drivers]
    positions = list(range(1, n + 1))

    vp = ax.violinplot(
        data, positions=positions,
        widths=0.7, showextrema=False, showmedians=False,
    )
    for body, d in zip(vp["bodies"], drivers):
        body.set_facecolor(driver_colors[d])
        body.set_edgecolor("none")
        body.set_alpha(0.7)

    # -----------------------------
    # 2. 蜂群散点（按轮胎颜色）
    # -----------------------------
    np.random.seed(42)
    for i, d in enumerate(drivers):
        times = driver_data[d]["times"]
        compounds = driver_data[d]["compounds"]
        for compound in COMPOUND_COLORS.keys():
            mask = np.array([str(c).upper() == compound for c in compounds])
            if not mask.any():
                continue
            x = np.full(mask.sum(), i + 1) + np.random.uniform(-0.18, 0.18, mask.sum())
            ax.scatter(
                x, times[mask],
                color=COMPOUND_COLORS[compound],
                s=22, edgecolors="black", linewidths=0.3,
                alpha=0.95, zorder=5,
            )

    # -----------------------------
    # 3. 最快圈标记
    # -----------------------------
    for i, d in enumerate(drivers):
        best = fastest_df.loc[fastest_df["Driver"] == d, "LapTimeSec"].iloc[0]
        ax.hlines(best, i + 1 - 0.35, i + 1 + 0.35, color=driver_colors[d], linewidth=2, zorder=6)

    # -----------------------------
    # 4. 坐标轴 & 网格
    # -----------------------------
    ax.set_xticks(positions)
    ax.set_xticklabels(drivers, fontsize=11, fontweight="bold", color="white")
    ax.set_xlabel("Driver", fontsize=12, color="white", labelpad=15)

    # Y 轴范围——所有圈速的合理范围
    all_times = np.concatenate(data)
    if len(all_times) > 0:
        pct_lo, pct_hi = np.percentile(all_times, [1, 99])
        margin = (pct_hi - pct_lo) * 0.15
        ax.set_ylim(pct_lo - margin, pct_hi + margin)

    ax.set_ylabel("Lap Time (s)", fontsize=12, color="white")
    ax.tick_params(colors="white")
    ax.grid(True, axis="y", alpha=0.2, color="white", linestyle="--")

    # -----------------------------
    # 5. 标题
    # -----------------------------
    gp_name = session.event["EventName"]
    year = session.event["EventDate"].year if hasattr(session.event, "EventDate") else ""
    session_short = "Race" if session.name == "Race" else session.name
    ax.set_title(f"{year} {gp_name} Lap Time Distributions", fontsize=15, fontweight="bold", color="white", pad=15)

    # -----------------------------
    # 6. 车手名下方：最快/最慢 lap
    # -----------------------------
    for i, d in enumerate(drivers):
        times = driver_data[d]["times"]
        if len(times) == 0:
            continue
        best = np.min(times)
        slowest = np.max(times)
        delta = slowest - best
        # 用 ylim 下方位置插入两行
        y_lo = ax.get_ylim()[0]
        y_range = ax.get_ylim()[1] - y_lo
        ax.text(
            i + 1, y_lo - y_range * 0.05,
            f"{best:.1f}s",
            ha="center", va="top", fontsize=8, color="#00ff00",
            fontweight="bold", transform=ax.transData,
        )
        ax.text(
            i + 1, y_lo - y_range * 0.11,
            f"{slowest:.1f}s",
            ha="center", va="top", fontsize=8, color="#ff6666",
            fontweight="bold", transform=ax.transData,
        )

    # 调整 ylim 给下方文字留空间
    y_lo, y_hi = ax.get_ylim()
    ax.set_ylim(y_lo - (y_hi - y_lo) * 0.15, y_hi)

    # -----------------------------
    # 7. 轮胎颜色图例
    # -----------------------------
    from matplotlib.lines import Line2D
    legend_elements = []
    for c, color in COMPOUND_COLORS.items():
        if c in ["INTERMEDIATE", "WET"]:
            continue
        legend_elements.append(
            Line2D([0], [0], marker="o", color="w", label=c,
                   markerfacecolor=color, markersize=8, markeredgecolor="black", linewidth=0)
        )
    ax.legend(handles=legend_elements, loc="upper left", title="Compound",
              frameon=False, fontsize=10, title_fontsize=11, labelcolor="white")

    # 去掉边框
    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="#1a1a1a")
        print(f"  Saved: {save_path}")
    else:
        fname = f"LapDist_{session.event['EventDate'].year}_{gp_name.replace(' ', '_')}_{session_short}.png"
        fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor="#1a1a1a")
        print(f"  Saved: {fname}")

    plt.show()
    plt.style.use("default")  # 恢复默认主题


def main():
    parser = argparse.ArgumentParser(
        description="F1 车手圈速分布可视化 (官方风格: 小提琴 + 蜂群 + 轮胎色)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python lap_distribution.py 2024 Bahrain Q VER LEC NOR
  python lap_distribution.py 2023 Azerbaijan R
  python lap_distribution.py 2024 Monaco R --drivers all
        """,
    )
    parser.add_argument("year", type=int)
    parser.add_argument("gp", type=str)
    parser.add_argument("session_type", type=str, choices=["Q", "R", "FP1", "FP2", "FP3", "SQ", "S"])
    parser.add_argument("--drivers", type=str, nargs="+", default=["all"],
                        help="车手代码列表（默认 all = 全场）")
    parser.add_argument("--save", "-o", type=str, default=None)

    args = parser.parse_args()
    year, gp = args.year, args.gp
    drivers = [d.upper() for d in args.drivers]

    print(f"\nLoading {year} {gp} {args.session_type}...")
    try:
        session = fastf1.get_session(year, gp, args.session_type)
        session.load()
    except Exception as e:
        print(f"  Error: {e}")
        schedule = fastf1.get_event_schedule(year)
        for _, row in schedule.iterrows():
            if gp.lower() in str(row["EventName"]).lower():
                print(f"  Try: {row['EventName']}")
        return

    gp_name = session.event["EventName"]
    print(f"  {gp_name} ({args.session_type})")

    laps, fastest_df = get_lap_data(session, drivers)
    if len(laps) == 0:
        print("  No valid laps found!")
        return

    print(f"  {len(laps)} laps from {laps['Driver'].nunique()} drivers")

    plot_lap_distribution(session, laps, fastest_df, save_path=args.save)
    print("Done!\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
F1 赛道档位可视化 — 在赛道图上用颜色标注档位
用法: python gear_shifts_on_track.py 2024 Bahrain VER
      python gear_shifts_on_track.py 2024 Monaco VER HAM
"""

import argparse
import os

import fastf1
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colormaps
from matplotlib.collections import LineCollection

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".fastf1_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)


def get_fastest_lap_telemetry(session, driver_code):
    """获取车手最快圈的遥测数据（位置 + 档位）"""
    laps_driver = session.laps.pick_drivers(driver_code)
    valid = laps_driver.loc[laps_driver["LapTime"].notna()]

    if len(valid) == 0:
        return None

    best = valid.sort_values("LapTime").iloc[0]
    tel = best.get_telemetry()
    return best, tel


def plot_gear_track(tel, circuit_info, ax, title, linewidth=4, no_corners=False):
    """在赛道上绘制档位颜色图 + 弯角编号"""
    x = np.array(tel["X"].values)
    y = np.array(tel["Y"].values)
    gear = tel["nGear"].to_numpy().astype(float)

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    cmap = colormaps["Paired"]
    lc = LineCollection(segments, norm=plt.Normalize(1, cmap.N + 1), cmap=cmap)
    lc.set_array(gear)
    lc.set_linewidth(linewidth)

    ax.add_collection(lc)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title, fontsize=13, fontweight="bold", color="white")
    ax.tick_params(labelleft=False, left=False, labelbottom=False, bottom=False)

    # 起点标记
    ax.scatter(x[0], y[0], marker="o", color="white", edgecolors="lime",
               s=100, zorder=6, linewidths=2)
    ax.annotate("START", (x[0], y[0]),
                textcoords="offset points", xytext=(10, 10),
                fontsize=9, fontweight="bold", color="lime")

    # 弯角编号
    if not no_corners and circuit_info is not None and hasattr(circuit_info, "corners"):
        corners = circuit_info.corners
        for _, row in corners.iterrows():
            cn = int(row["Number"])
            cx, cy = row["X"], row["Y"]
            label = f"T{cn}"

            # 黄色圆点标记实际弯角位置
            ax.scatter(cx, cy, marker="o", color="#ffd700", s=18,
                       edgecolors="black", linewidths=0.5, zorder=5, alpha=0.9)

            # 标签贴在弯角位置上方偏右，避免遮住点
            ax.annotate(
                label,
                xy=(cx, cy),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7.5,
                fontweight="bold",
                color="white",
                ha="left",
                va="bottom",
                zorder=6,
                bbox=dict(boxstyle="round,pad=0.2",
                          facecolor="#111", alpha=0.75,
                          edgecolor="#ffd700", linewidth=0.6),
            )

    return lc


def main():
    parser = argparse.ArgumentParser(
        description="F1 赛道档位可视化 — 最快圈档位颜色图",
        epilog="""
示例:
  python gear_shifts_on_track.py 2024 Bahrain VER
  python gear_shifts_on_track.py 2024 Monaco VER HAM
        """,
    )
    parser.add_argument("year", type=int, help="赛季年份")
    parser.add_argument("gp", type=str, help="大奖赛名称")
    parser.add_argument("d1", type=str, help="车手1 代码")
    parser.add_argument("d2", type=str, nargs="?", default=None, help="车手2 代码 (可选)")
    parser.add_argument("--save", "-o", type=str, default=None)
    parser.add_argument("--session", "-s", type=str, default="Q",
                        help="Session 类型 (默认 Q，可选 R/FP1/FP2/FP3)")
    parser.add_argument("--lw", type=int, default=4, help="线宽 (默认 4)")
    parser.add_argument("--no-corners", action="store_true", help="不显示弯角编号")

    args = parser.parse_args()

    year, gp = args.year, args.gp
    d1_code = args.d1.upper()
    d2_code = args.d2.upper() if args.d2 else None
    sess_type = args.session

    print(f"\nLoading {year} {gp} {sess_type}...")
    try:
        session = fastf1.get_session(year, gp, sess_type)
        session.load()
    except Exception as e:
        print(f"  Error: {e}")
        schedule = fastf1.get_event_schedule(year)
        for _, row in schedule.iterrows():
            if gp.lower() in str(row["EventName"]).lower():
                print(f"  Try: {row['EventName']}")
        return

    gp_name = session.event["EventName"]
    print(f"  {gp_name}")

    # 获取电路信息（含弯角）
    circuit_info = None
    if not args.no_corners:
        try:
            circuit_info = session.get_circuit_info()
            n_corners = len(circuit_info.corners) if hasattr(circuit_info, "corners") else 0
            print(f"  {n_corners} corners loaded")
        except Exception as e:
            print(f"  Corner data not available: {e}")

    # 获取遥测
    print(f"Fetching fastest lap data...")
    result1 = get_fastest_lap_telemetry(session, d1_code)
    if result1 is None:
        print(f"  Driver {d1_code} has no valid laps")
        return
    lap1, tele1 = result1
    print(f"  {d1_code}: {lap1['LapTime']} (Lap #{int(lap1['LapNumber'])})  |  Gear range {int(tele1['nGear'].min())}-{int(tele1['nGear'].max())}")

    if d2_code:
        result2 = get_fastest_lap_telemetry(session, d2_code)
        if result2 is None:
            print(f"  Driver {d2_code} has no valid laps")
            d2_code = None
        else:
            lap2, tele2 = result2
            print(f"  {d2_code}: {lap2['LapTime']} (Lap #{int(lap2['LapNumber'])})  |  Gear range {int(tele2['nGear'].min())}-{int(tele2['nGear'].max())}")

    # 暗色主题
    plt.style.use("dark_background")
    ncols = 2 if d2_code else 1
    fig, axes = plt.subplots(1, ncols, figsize=(8 * ncols, 7), facecolor="#111111")
    if ncols == 1:
        axes = [axes]
    for ax in axes:
        ax.set_facecolor("#111111")

    sess_label = {"Q": "Qualifying", "R": "Race", "FP1": "FP1", "FP2": "FP2", "FP3": "FP3"}.get(sess_type, sess_type)
    fig.suptitle(f"{gp_name} — {sess_label} Gear Shift Map",
                 fontsize=15, fontweight="bold", color="white", y=0.98)

    lc1 = plot_gear_track(tele1, circuit_info, axes[0],
                          title=f"{d1_code} — {lap1['LapTime']}",
                          linewidth=args.lw, no_corners=args.no_corners)
    cbar1 = fig.colorbar(lc1, ax=axes[0], label="Gear",
                         boundaries=np.arange(1, 10), shrink=0.85, pad=0.02)
    cbar1.set_ticks(np.arange(1.5, 9.5))
    cbar1.set_ticklabels(np.arange(1, 9))
    cbar1.ax.tick_params(labelsize=8, colors="white")
    cbar1.set_label("Gear", color="white")
    cbar1.outline.set_edgecolor("#444")

    if d2_code:
        lc2 = plot_gear_track(tele2, circuit_info, axes[1],
                              title=f"{d2_code} — {lap2['LapTime']}",
                              linewidth=args.lw, no_corners=args.no_corners)
        cbar2 = fig.colorbar(lc2, ax=axes[1], label="Gear",
                             boundaries=np.arange(1, 10), shrink=0.85, pad=0.02)
        cbar2.set_ticks(np.arange(1.5, 9.5))
        cbar2.set_ticklabels(np.arange(1, 9))
        cbar2.ax.tick_params(labelsize=8, colors="white")
        cbar2.set_label("Gear", color="white")
        cbar2.outline.set_edgecolor("#444")

    plt.tight_layout(rect=[0, 0, 1, 0.94])

    if args.save:
        fig.savefig(args.save, dpi=200, bbox_inches="tight", facecolor="#111111")
        print(f"\nSaved: {args.save}")
    else:
        fname = f"GearShift_{year}_{gp.replace(' ', '_')}_{d1_code}"
        if d2_code:
            fname += f"_vs_{d2_code}"
        fname += ".png"
        fig.savefig(fname, dpi=200, bbox_inches="tight", facecolor="#111111")
        print(f"\nSaved: {fname}")

    plt.show()
    plt.style.use("default")
    print("Done!")


if __name__ == "__main__":
    main()

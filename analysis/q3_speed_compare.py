#!/usr/bin/env python3
"""
F1 Q3 遥测速度对比曲线
用法: python q3_speed_compare.py --year 2024 --gp "Bahrain" --d1 VER --d2 LEC
      python q3_speed_compare.py 2024 Monaco VER HAM [--smooth 5]

依赖: fastf1, matplotlib, numpy
"""

import argparse
import os
import sys

import fastf1
import matplotlib.pyplot as plt
import numpy as np

# ==================== 中文字体设置 ====================
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# FastF1 缓存 — 放在脚本所在目录的上级（F1 dash 根目录共享）
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".fastf1_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)


def smooth(y, window=5):
    """移动平均平滑"""
    kernel = np.ones(window) / window
    return np.convolve(y, kernel, mode="same")


def get_q3_laps(session, driver_code: str):
    """获取指定车手在 Q3 的最快圈"""
    laps_driver = session.laps.pick_drivers(driver_code)
    # Q3 在 FastF1 中对应的 session 类型需要看实际数据
    # 尝试获取 Q3 laps
    laps_q3 = laps_driver.pick_quicklaps()
    
    # 如果没有 quicklaps，尝试直接按 SessionTime 判断
    if len(laps_q3) == 0:
        # 某些赛道可能没有 Q3 track status
        print(f"  ⚠ {driver_code}: pick_quicklaps() 返回空，尝试其他方式...")
        # 直接取排位赛中最快的一圈
        laps_all = laps_driver.pick_laps()  # 所有计时圈
        if len(laps_all) == 0:
            # 回退：取该车手所有有效圈
            valid = laps_driver.loc[laps_driver["LapTime"].notna()]
            if len(valid) == 0:
                return None
            return valid.sort_values("LapTime").iloc[0]
        return laps_all.sort_values("LapTime").iloc[0]
    
    # Q3 中最快圈
    best_q3 = laps_q3.sort_values("LapTime").iloc[0]
    return best_q3


def plot_speed_comparison(session, d1_lap, d2_lap, d1_code, d2_code, smooth_window=0, gp_name=""):
    """绘制速度对比曲线"""
    # 获取遥测数据
    d1_telemetry = d1_lap.get_car_data()
    d2_telemetry = d2_lap.get_car_data()

    # FastF1 v3: 需要通过 integrate_distance() 计算赛道距离
    d1_telemetry["Distance"] = d1_telemetry.integrate_distance()
    d2_telemetry["Distance"] = d2_telemetry.integrate_distance()

    d1_dist = d1_telemetry["Distance"].values
    d1_speed = d1_telemetry["Speed"].values
    d2_dist = d2_telemetry["Distance"].values
    d2_speed = d2_telemetry["Speed"].values

    # 平滑
    if smooth_window > 1:
        d1_speed_s = smooth(d1_speed, smooth_window)
        d2_speed_s = smooth(d2_speed, smooth_window)
    else:
        d1_speed_s = d1_speed
        d2_speed_s = d2_speed

    # 速度差
    # 对齐到较短的距离
    min_len = min(len(d1_speed_s), len(d2_speed_s))
    speed_diff = d1_speed_s[:min_len] - d2_speed_s[:min_len]
    dist_diff = d1_dist[:min_len]

    # 车手颜色（车队色，若无法获取则默认）
    try:
        d1_color = fastf1.plotting.get_driver_color(d1_code, session)
    except Exception:
        d1_color = "#FF1E00"
    try:
        d2_color = fastf1.plotting.get_driver_color(d2_code, session)
    except Exception:
        d2_color = "#00D2BE"

    # 车手完整名
    try:
        d1_name = fastf1.api.driver_name(d1_code)
    except Exception:
        d1_name = d1_code
    try:
        d2_name = fastf1.api.driver_name(d2_code)
    except Exception:
        d2_name = d2_code

    # 暗色主题
    plt.style.use("dark_background")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6),
                                   gridspec_kw={"width_ratios": [3, 1.5]},
                                   facecolor="#111111")
    ax1.set_facecolor("#111111")
    ax2.set_facecolor("#111111")

    fig.suptitle(
        f"{gp_name} — Q3 Speed Telemetry\n{d1_code} vs {d2_code}",
        fontsize=16,
        fontweight="bold",
        y=0.98,
        color="white",
    )

    # ---- 左图: 速度曲线 ----
    ax1.plot(d1_dist, d1_speed_s, color=d1_color, linewidth=2, label=d1_code)
    ax1.plot(d2_dist, d2_speed_s, color=d2_color, linewidth=2, label=d2_code)
    ax1.set_xlabel("Distance (m)", fontsize=12, color="white")
    ax1.set_ylabel("Speed (km/h)", fontsize=12, color="white")
    ax1.set_title("Q3 Fastest Lap Speed", fontsize=13, color="white")
    ax1.legend(loc="upper right", fontsize=11, facecolor="#222", edgecolor="#444",
               labelcolor="white")
    ax1.grid(True, alpha=0.15, color="white")
    ax1.set_xlim(left=0)
    ax1.tick_params(colors="white")

    # 标注最高速度
    d1_max_speed = np.max(d1_speed_s)
    d2_max_speed = np.max(d2_speed_s)
    d1_max_idx = np.argmax(d1_speed_s)
    d2_max_idx = np.argmax(d2_speed_s)

    ax1.annotate(
        f"{d1_code}: {d1_max_speed:.0f} km/h",
        xy=(d1_dist[d1_max_idx], d1_max_speed),
        xytext=(d1_dist[d1_max_idx] + 200, d1_max_speed + 15),
        arrowprops=dict(arrowstyle="->", color=d1_color),
        color=d1_color,
        fontsize=10,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#111", alpha=0.7, edgecolor=d1_color),
    )
    ax1.annotate(
        f"{d2_code}: {d2_max_speed:.0f} km/h",
        xy=(d2_dist[d2_max_idx], d2_max_speed),
        xytext=(d2_dist[d2_max_idx] + 200, d2_max_speed - 25),
        arrowprops=dict(arrowstyle="->", color=d2_color),
        color=d2_color,
        fontsize=10,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#111", alpha=0.7, edgecolor=d2_color),
    )

    # ---- 右图: 速度差 (d1 - d2) ----
    ax2.fill_between(
        dist_diff, speed_diff, 0,
        where=(speed_diff > 0),
        color=d1_color, alpha=0.5,
        label=f"{d1_code}  faster",
    )
    ax2.fill_between(
        dist_diff, speed_diff, 0,
        where=(speed_diff < 0),
        color=d2_color, alpha=0.5,
        label=f"{d2_code}  faster",
    )
    ax2.axhline(y=0, color="white", linewidth=0.8, linestyle="--", alpha=0.5)
    ax2.set_xlabel("Distance (m)", fontsize=12, color="white")
    ax2.set_ylabel(f"Speed Delta (km/h)\n{d1_code} - {d2_code}", fontsize=12, color="white")
    ax2.set_title("Speed Delta", fontsize=13, color="white")
    ax2.legend(loc="upper right", fontsize=10, facecolor="#222", edgecolor="#444",
               labelcolor="white")
    ax2.grid(True, alpha=0.15, color="white")
    ax2.set_xlim(left=0)
    ax2.tick_params(colors="white")

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return fig


def main():
    parser = argparse.ArgumentParser(
        description="F1 Q3 遥测速度对比曲线 — 比较两位车手在排位赛Q3的速度曲线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python q3_speed_compare.py 2024 Bahrain VER LEC
  python q3_speed_compare.py 2024 Monaco VER HAM --smooth 8
  python q3_speed_compare.py 2024 "Abu Dhabi" VER NOR --save result.png
  python q3_speed_compare.py --list 2024
        """,
    )

    # --list 模式
    if len(sys.argv) >= 2 and sys.argv[1] == "--list":
        parser.add_argument("--list", type=int, required=True)
        args = parser.parse_args()
        year = args.list
        print(f"\n{year} 赛季可用大奖赛:\n")
        schedule = fastf1.get_event_schedule(year)
        for _, row in schedule.iterrows():
            print(f"  Round {int(row['RoundNumber']):>2} | {row['EventName']:<45} | {row['Country']}")
        print()
        return

    # 位置参数 / 可选参数
    parser.add_argument("year", type=int, help="赛季年份，如 2024")
    parser.add_argument("gp", type=str, help="大奖赛名称，如 Bahrain / Monaco")
    parser.add_argument("d1", type=str, help="车手1的三字母代码，如 VER")
    parser.add_argument("d2", type=str, help="车手2的三字母代码，如 LEC")
    parser.add_argument("--smooth", type=int, default=5, help="平滑窗口大小 (默认 5，设 1 为不平滑)")
    parser.add_argument("--save", "-o", type=str, default=None, help="保存图片路径 (可选)")

    args = parser.parse_args()

    year = args.year
    gp = args.gp
    d1_code = args.d1.upper()
    d2_code = args.d2.upper()
    smooth_window = args.smooth
    save_path = args.save

    print(f"\n🏎️  F1 Q3 遥测速度对比")
    print(f"   赛季: {year}  |  大奖赛: {gp}")
    print(f"   车手: {d1_code}  vs  {d2_code}")
    print(f"{'─' * 50}")

    # 1. 加载排位赛 Session
    print(f"📡 加载 {year} {gp} 排位赛数据...")
    try:
        session = fastf1.get_session(year, gp, "Q")
        session.load()
    except Exception as e:
        print(f"  ❌ 加载失败: {e}")
        print("  尝试模糊匹配 GP 名称...")
        schedule = fastf1.get_event_schedule(year)
        gp_lower = gp.lower()
        matches = []
        for _, row in schedule.iterrows():
            ename = str(row["EventName"]).lower()
            if gp_lower in ename:
                matches.append(row["EventName"])
        if matches:
            print(f"  可能的匹配: {matches}")
            print("  请用完整名称重试")
        else:
            print(f"  未找到匹配项。可使用 'python q3_speed_compare.py --list {year}' 查看所有大奖赛")
        return

    gp_name = session.event["EventName"]
    print(f"  ✅ 已加载: {gp_name}")

    # 2. 获取 Q3 最快圈
    print(f"\n📊 获取 Q3 最快圈...")
    d1_lap = get_q3_laps(session, d1_code)
    d2_lap = get_q3_laps(session, d2_code)

    if d1_lap is None:
        print(f"  ❌ 未找到 {d1_code} 的有效圈速")
        return
    if d2_lap is None:
        print(f"  ❌ 未找到 {d2_code} 的有效圈速")
        return

    d1_time = d1_lap["LapTime"]
    d2_time = d2_lap["LapTime"]
    delta = d1_time - d2_time
    delta_sign = "快" if delta.total_seconds() < 0 else "慢"

    def fmt_td(td):
        total_s = td.total_seconds()
        m = int(total_s // 60)
        s = total_s % 60
        return f"{m}:{s:06.3f}"

    print(f"  {d1_code}: {fmt_td(d1_time)}  (Lap #{int(d1_lap['LapNumber'])})")
    print(f"  {d2_code}: {fmt_td(d2_time)}  (Lap #{int(d2_lap['LapNumber'])})")
    print(f"  Δ: {abs(delta.total_seconds()):.3f}s — {d1_code} 比 {d2_code} {delta_sign}")

    # 3. 绘图
    print(f"\n🎨 绘制速度对比曲线...")
    fig = plot_speed_comparison(
        session, d1_lap, d2_lap, d1_code, d2_code,
        smooth_window=smooth_window, gp_name=gp_name,
    )

    # 4. 保存 / 显示
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="#111111")
        print(f"  ✅ 已保存到: {save_path}")
    else:
        default_name = f"Q3_{year}_{gp.replace(' ', '_')}_{d1_code}_vs_{d2_code}.png"
        fig.savefig(default_name, dpi=150, bbox_inches="tight", facecolor="#111111")
        print(f"  ✅ 已保存到: {default_name}")

    plt.show()
    plt.style.use("default")
    print(f"\n{'─' * 50}")
    print("完成！")


if __name__ == "__main__":
    main()

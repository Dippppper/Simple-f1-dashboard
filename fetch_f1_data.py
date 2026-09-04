#!/usr/bin/env python3
"""Fetch latest F1 data via FastF1 and output data.json for the dashboard.

Usage:
    python fetch_f1_data.py          # fetch current year, overwrite data.json
    python fetch_f1_data.py 2025     # fetch a specific year
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import fastf1

# ── helpers ──────────────────────────────────────────────────────────

DASH_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(DASH_DIR, "data.json")

MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def dt_to_utc(d):
    """Convert a pandas Timestamp or datetime to ISO UTC string."""
    if d is None:
        return None
    ts = d if isinstance(d, datetime) else d.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dt_to_date(d):
    """Extract YYYY-MM-DD string."""
    ts = d if isinstance(d, datetime) else d.to_pydatetime()
    return ts.strftime("%Y-%m-%d")


def fmt_day_label(d):
    """Format session day label like 'Aug 21'."""
    ts = d if isinstance(d, datetime) else d.to_pydatetime()
    return f"{MONTH_ABBR[ts.month]} {ts.day}"


def safe_str(val):
    """Convert pandas/numpy values to plain Python types."""
    import pandas as pd
    import numpy as np
    if isinstance(val, (pd.Timestamp,)):
        return val.isoformat() if val.tz else f"{val.isoformat()}Z"
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if pd.isna(val):
        return ""
    return str(val) if not isinstance(val, (int, float, str, bool)) else val


def safe_float(val, default=0.0):
    try:
        f = float(val)
        return f if f == f else default  # NaN check
    except (ValueError, TypeError):
        return default


# ── team name normalization (FastF1 → dashboard format) ─────────────

TEAM_MAP = {
    "Mercedes": "Mercedes",
    "Ferrari": "Ferrari",
    "McLaren": "McLaren",
    "Red Bull Racing": "Red Bull",
    "Racing Bulls": "RB F1 Team",
    "RB F1 Team": "RB F1 Team",
    "Alpine": "Alpine F1 Team",
    "Haas F1 Team": "Haas F1 Team",
    "Aston Martin": "Aston Martin",
    "Williams": "Williams",
    "Audi": "Audi",
    "Kick Sauber": "Audi",
    "Sauber": "Audi",
    "Cadillac": "Cadillac F1 Team",
    "Cadillac F1 Team": "Cadillac F1 Team",
}


def norm_team(name):
    return TEAM_MAP.get(name, name)


# ── main data collection ─────────────────────────────────────────────

def fetch_all(year: int | None = None) -> dict:
    if year is None:
        year = datetime.now().year

    fastf1.Cache.enable_cache(os.path.join(DASH_DIR, ".fastf1_cache"))

    schedule = fastf1.get_event_schedule(year)
    now = datetime.now(timezone.utc)

    # ── classify events ──
    completed_events = []
    active_events = []
    upcoming_events = []
    for _, row in schedule.iterrows():
        rd = int(row["RoundNumber"])
        edate = row["EventDate"].to_pydatetime()
        if edate.tzinfo is None:
            edate = edate.replace(tzinfo=timezone.utc)
        sessions = collect_event_sessions(year, rd, row, edate)
        ev = {
            "year": year,
            "round": str(rd),
            "eventName": row.get("EventName", ""),
            "officialName": row.get("OfficialEventName", row.get("EventName", "")),
            "country": row.get("Country", ""),
            "location": row.get("Location", ""),
            "circuit": row.get("Location", ""),  # FastF1 uses Location for circuit
            "date": dt_to_date(edate),
            "format": normalize_format(row.get("EventFormat", "conventional")),
            "sessions": sessions,
        }
        weekend_start = edate - timedelta(days=3)
        if edate < now:
            # race finished
            completed_events.append(ev)
            active_events.append(ev)
        else:
            # race not finished yet — still the upcoming "next GP"
            upcoming_events.append(ev)
            if weekend_start <= now:
                # weekend in progress: some sessions done, race not yet
                active_events.append(ev)

    # current active event (latest completed race, or in-progress weekend)
    event_data = {}
    qualifying_data = []
    race_data = []
    pole_lap_data = {}
    fastest_lap_data = {}
    quali_source = None   # set when quali data is carried over from an earlier round
    race_source = None    # set when race data is carried over from an earlier round
    if active_events:
        last = active_events[-1]
        event_data = {
            "year": last["year"],
            "round": last["round"],
            "eventName": last["eventName"],
            "officialName": last["officialName"],
            "country": last["country"],
            "location": last["location"],
            "circuit": last["circuit"],
            "date": last["date"],
            "format": last["format"],
            "weekendStart": last["sessions"].get("fp1", {}).get("date", ""),
            "weekendEnd": last.get("date", ""),
            "qualifyingEnd": last["sessions"].get("qualifying", {}).get("date", ""),
            "sessions": last["sessions"],
        }
        # Fetch results per session. Prefer the active event's own sessions, but
        # when the current weekend hasn't produced them yet (e.g. the script runs
        # in the days after a new weekend opens, or between FP1 and quali), fall
        # back to the last completed event so the RESULTS / LAP TIME / prediction
        # sections keep showing the most recent available data.
        last_round = int(last["round"])

        def resolve_results_round(stype):
            """Return the round to fetch session results from: the active round
            if it already has results, otherwise the last completed round."""
            if session_has_results(year, last_round, stype):
                return last_round
            if completed_events:
                fb = int(completed_events[-1]["round"])
                if session_has_results(year, fb, stype):
                    return fb
            return None

        def source_meta(rd):
            for e in completed_events:
                if int(e["round"]) == rd:
                    return {
                        "round": e["round"],
                        "eventName": e["eventName"],
                        "country": e["country"],
                        "location": e["location"],
                    }
            return None

        q_round = resolve_results_round("Q")
        if q_round is not None:
            try:
                qualifying_data, pole_lap_data = fetch_qualifying(year, q_round)
                if q_round != last_round:
                    quali_source = source_meta(q_round)
                    print(f"   qualifying: no results for round {last_round} yet — using round {q_round}")
            except Exception as e:
                print(f"  ⚠ qualifying: {e}")

        r_round = resolve_results_round("R")
        if r_round is not None:
            try:
                race_data, fastest_lap_data = fetch_race(year, r_round)
                if r_round != last_round:
                    race_source = source_meta(r_round)
                    print(f"   race: no results for round {last_round} yet — using round {r_round}")
            except Exception as e:
                print(f"  ⚠ race: {e}")

    # next upcoming event
    next_event_data = {}
    if upcoming_events:
        nx = upcoming_events[0]
        next_event_data = {
            "round": nx["round"],
            "eventName": nx["eventName"],
            "officialName": nx["officialName"],
            "country": nx["country"],
            "location": nx["location"],
            "circuit": nx["circuit"],
            "date": nx["date"],
            "format": nx["format"],
            "sessions": build_next_sessions(nx["round"], nx["sessions"]),
        }

    # standings
    standings_data = fetch_standings(year)

    # WDC feasibility
    wdc_feasibility = calculate_wdc_feasibility(year, standings_data.get("drivers", []), schedule)

    return {
        "event": event_data,
        "standings": standings_data,
        "qualifying": qualifying_data,
        "poleLap": pole_lap_data,
        "fastestLap": fastest_lap_data,
        "race": race_data,
        "lastUpdated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nextEvent": next_event_data,
        "wdcFeasibility": wdc_feasibility,
        # Source labels when results are carried over from an earlier round
        # (null when the data belongs to the active event itself)
        "qualiSource": quali_source,
        "raceSource": race_source,
    }


def session_has_results(year, round_num, stype):
    """Return True if a session (Q/R) has finished and has results.

    Used to decide whether to fetch qualifying/race data for an
    in-progress race weekend where only some sessions are done.
    """
    try:
        ev = fastf1.get_event(year, round_num)
        session = ev.get_session(stype)
        session.load(telemetry=False, weather=False, messages=False)
        return len(session.results) > 0
    except Exception:
        return False


def normalize_format(fmt):
    """Map FastF1 format names to dashboard convention."""
    fmt_lower = str(fmt).lower()
    if "sprint" in fmt_lower:
        return "sprint_qualifying"
    return "conventional"


def collect_event_sessions(year, rd, row, race_date):
    """Collect all session dates for an event from the schedule."""
    sessions = {}
    session_keys = {
        "Session1Date": ("fp1", "Practice 1"),
        "Session2Date": ("sq" if "sprint" in str(row.get("EventFormat", "")).lower() else "fp2", None),
        "Session3Date": ("fp3", None),
        "Session4Date": ("qualifying", "Qualifying"),
        "Session5Date": ("race", "Race"),
    }
    # Post-label override after checking format
    is_sprint = "sprint" in str(row.get("EventFormat", "")).lower()

    for col, (key, _name) in session_keys.items():
        if col in row and not pd_isna(row[col]):
            ts = row[col]
            if isinstance(ts, str):
                continue  # skip non-date values
            d = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            name = _name or key.upper()
            sessions[key] = {
                "name": name,
                "date": dt_to_utc(d),
            }

    # For non-sprint weekends, add Sprint key if sprint format
    if is_sprint:
        # FP2 becomes Sprint Qualifying on sprint weekends
        if "fp2" in sessions:
            sessions["sq"] = {
                "name": "Sprint Qualifying",
                "date": sessions["fp2"]["date"],
            }
            del sessions["fp2"]
        # Move fp3 → sprint if Session3 is the sprint
        if "fp3" in sessions:
            sessions["sprint"] = {
                "name": "Sprint",
                "date": sessions["fp3"]["date"],
            }
            del sessions["fp3"]
        # Check if there's an actual fp3 (Session4Date re-mapped)
        if "fp3" not in sessions:
            # Add quali back to its correct position
            pass

    # Re-read for sprint: Session1=fp1, Session2=SQ, Session3=Sprint, Session4=Quali, Session5=Race
    if is_sprint:
        sprint_map = [
            ("Session1Date", "fp1", "Practice 1"),
            ("Session2Date", "sq", "Sprint Qualifying"),
            ("Session3Date", "sprint", "Sprint"),
            ("Session4Date", "qualifying", "Qualifying"),
            ("Session5Date", "race", "Race"),
        ]
        sessions.clear()
        for col, key, name in sprint_map:
            if col in row and not pd_isna(row[col]):
                ts = row[col]
                if isinstance(ts, str):
                    continue
                d = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                sessions[key] = {
                    "name": name,
                    "date": dt_to_utc(d),
                }

    return sessions


def pd_isna(val):
    import pandas as pd
    return pd.isna(val)


def build_next_sessions(round_str, sessions_dict):
    """Build session list for nextEvent with label/day fields."""
    out = {}
    for key, sess in sessions_dict.items():
        d = datetime.fromisoformat(sess["date"].replace("Z", "+00:00"))
        out[key] = {
            "name": sess["name"],
            "date": sess["date"],
            "label": key.upper() if key in ("sq",) else {"fp1": "FP1", "fp2": "FP2", "fp3": "FP3",
                   "qualifying": "Qualifying", "sprint": "Sprint", "race": "Race"}.get(key, key.upper()),
            "day": fmt_day_label(d),
        }
    return out


# ── standings ────────────────────────────────────────────────────────

def _load_results(ev, stype):
    """Load a session and return its results, retrying once on transient network errors."""
    last_err = None
    for _ in range(2):
        try:
            s = ev.get_session(stype)
            s.load(telemetry=False, weather=False, messages=False)
            return s.results
        except Exception as e:
            last_err = e
    raise last_err


def _accumulate_results(drivers_dict, teams_dict, results):
    """Add points from a results dataframe into driver/team dicts (no win tracking)."""
    for _, d in results.iterrows():
        name = str(d.get("FullName", d.get("BroadcastName", "")))
        team = norm_team(str(d.get("TeamName", "")))
        pts = safe_float(d.get("Points", 0))
        if name not in drivers_dict:
            drivers_dict[name] = {"team": team, "points": 0, "wins": 0}
        drivers_dict[name]["points"] += int(pts)
        if team not in teams_dict:
            teams_dict[team] = {"points": 0, "wins": 0}
        teams_dict[team]["points"] += int(pts)


def fetch_standings(year):
    """Accumulate driver & constructor standings from completed race & sprint sessions."""
    drivers_dict = {}   # name -> {"team": ..., "points": ..., "wins": 0}
    teams_dict = {}     # team -> {"points": ..., "wins": 0}

    schedule = fastf1.get_event_schedule(year)
    now = datetime.now(timezone.utc)

    for _, row in schedule.iterrows():
        rd = int(row["RoundNumber"])
        if rd == 0:
            continue  # skip testing/pre-season
        edate = row["EventDate"].to_pydatetime()
        if edate.tzinfo is None:
            edate = edate.replace(tzinfo=timezone.utc)

        # Weekend hasn't started yet — no session can have produced points
        if (edate - timedelta(days=3)) > now:
            break

        ev = None
        try:
            ev = fastf1.get_event(year, rd)
        except Exception:
            continue

        # Sprint points (sprint weekends) — counted as soon as the sprint is done.
        if "sprint" in str(row.get("EventFormat", "")).lower():
            try:
                _accumulate_results(drivers_dict, teams_dict, _load_results(ev, "S"))
            except Exception as e:
                print(f"  ⚠ sprint round {rd}: {e}")

        # Race points — only once the race itself has finished
        if edate > now:
            continue

        try:
            results = _load_results(ev, "R")
            if len(results) == 0:
                continue
            _accumulate_results(drivers_dict, teams_dict, results)
            # Track wins (race winner only)
            first = results.iloc[0]
            wname = str(first.get("FullName", first.get("BroadcastName", "")))
            wteam = norm_team(str(first.get("TeamName", "")))
            if wname in drivers_dict:
                drivers_dict[wname]["wins"] += 1
            if wteam in teams_dict:
                teams_dict[wteam]["wins"] += 1
        except Exception as e2:
            print(f"  ⚠ standings round {rd}: {e2}")

    # Sort and assign positions
    drivers = []
    sorted_d = sorted(drivers_dict.items(), key=lambda x: (-x[1]["points"], -x[1]["wins"]))
    for i, (name, vals) in enumerate(sorted_d, 1):
        drivers.append({
            "pos": i,
            "name": name,
            "team": vals["team"],
            "points": vals["points"],
            "wins": vals["wins"],
        })

    constructors = []
    sorted_c = sorted(teams_dict.items(), key=lambda x: (-x[1]["points"], -x[1]["wins"]))
    for i, (team, vals) in enumerate(sorted_c, 1):
        constructors.append({
            "pos": i,
            "name": team,
            "points": vals["points"],
            "wins": vals["wins"],
        })

    return {"drivers": drivers, "constructors": constructors}


# ── WDC feasibility: who can still win ────────────────────────────────

def calculate_wdc_feasibility(year, drivers, schedule):
    """Calculate max remaining points and which drivers can still win WDC."""
    now = datetime.now(timezone.utc)
    completed_rounds = set()
    for _, row in schedule.iterrows():
        rd = int(row["RoundNumber"])
        if rd == 0:
            continue
        edate = row["EventDate"].to_pydatetime()
        if edate.tzinfo is None:
            edate = edate.replace(tzinfo=timezone.utc)
        if edate <= now:
            completed_rounds.add(rd)

    if not completed_rounds or not drivers:
        return None

    last_completed = max(completed_rounds)
    leader_points = drivers[0]["points"] if drivers else 0

    # Count remaining sprint and conventional events
    POINTS_PER_SPRINT_WEEKEND = 8 + 25   # sprint win + race win
    POINTS_PER_CONVENTIONAL = 25           # race win only

    sprint_count = 0
    conventional_count = 0
    for _, row in schedule.iterrows():
        rd = int(row["RoundNumber"])
        if rd == 0 or rd in completed_rounds:
            continue
        fmt = str(row.get("EventFormat", "")).lower()
        if "sprint" in fmt:
            sprint_count += 1
        else:
            conventional_count += 1

    max_remaining_points = sprint_count * POINTS_PER_SPRINT_WEEKEND + conventional_count * POINTS_PER_CONVENTIONAL

    driver_feasibility = []
    for d in drivers:
        max_possible = d["points"] + max_remaining_points
        driver_feasibility.append({
            "name": d["name"],
            "team": d["team"],
            "currentPoints": d["points"],
            "maxPossible": max_possible,
            "canWin": max_possible >= leader_points,
        })

    return {
        "lastCompletedRound": last_completed,
        "remainingRaces": sprint_count + conventional_count,
        "remainingSprints": sprint_count,
        "maxRemainingPoints": max_remaining_points,
        "leaderPoints": leader_points,
        "drivers": driver_feasibility,
    }


# ── qualifying ───────────────────────────────────────────────────────

def fetch_qualifying(year, round_num):
    import pandas as pd
    ev = fastf1.get_event(year, round_num)
    q_session = ev.get_session("Q")
    q_session.load(telemetry=False, weather=False, messages=False)
    results = q_session.results

    pole_time = None
    q_rows = []
    for _, d in results.iterrows():
        pos = int(d.get("Position", d.get("ClassifiedPosition", 0)))
        if pos == 0:
            continue
        name = str(d.get("FullName", d.get("BroadcastName", "")))
        team = norm_team(str(d.get("TeamName", "")))
        t_q1 = d.get("Q1", pd.NaT)
        t_q2 = d.get("Q2", pd.NaT)
        t_q3 = d.get("Q3", pd.NaT)
        q1 = fmt_timedelta_lap(t_q1) if not pd.isna(t_q1) else ""
        q2 = fmt_timedelta_lap(t_q2) if not pd.isna(t_q2) else ""
        q3 = fmt_timedelta_lap(t_q3) if not pd.isna(t_q3) else ""

        # Determine exit stage
        if not q1 or q1 == "":
            q1 = "Q1 exit"
        if not q2 or q2 == "":
            q2 = "Q2 exit" if q1 and q1 != "Q1 exit" else ""
        if not q3 or q3 == "":
            q3 = "Q3 exit" if q2 and q2 != "Q2 exit" else ""

        # Gap
        if pole_time is None and q3 and q3 != "Q3 exit":
            pole_time = parse_lap_time(q3)
        gap = ""
        if pole_time is not None and q3 and q3 != "Q3 exit":
            lt = parse_lap_time(q3)
            if lt is not None:
                diff = lt - pole_time
                if diff > 0:
                    gap = f"+{diff:.3f}"
                elif diff == 0:
                    gap = ""

        q_rows.append({
            "pos": pos,
            "name": name,
            "team": team,
            "q1": q1,
            "q2": q2,
            "q3": q3,
            "gap": gap,
        })

    # Pole lap data
    pole_lap = {}
    if q_rows:
        p1 = q_rows[0]
        code = p1["name"].split()[-1][:3].upper() if p1["name"] else ""
        # Get the actual driver code from results (e.g. "NOR" vs guessing from name)
        p1_abbr = str(q_session.results.iloc[0].get("Abbreviation", code))

        # Try to extract sector times and top speed from the session
        sectors = {}
        top_speed = 320
        try:
            # Get the fastest qualifying lap — use driver code, not full name
            qlaps = q_session.laps.pick_drivers(p1_abbr).pick_quicklaps()
            if len(qlaps) > 0:
                fl = qlaps.iloc[0]
                # Sector times are Timedeltas
                s1_td = fl.get("Sector1Time", pd.NaT)
                s2_td = fl.get("Sector2Time", pd.NaT)
                s3_td = fl.get("Sector3Time", pd.NaT)
                s1 = s1_td.total_seconds() if not pd.isna(s1_td) else 0
                s2 = s2_td.total_seconds() if not pd.isna(s2_td) else 0
                s3 = s3_td.total_seconds() if not pd.isna(s3_td) else 0
                sectors = {
                    "s1": f"{s1:.3f}",
                    "s2": f"{s2:.3f}",
                    "s3": f"{s3:.3f}",
                }
                ts = safe_float(fl.get("SpeedST", 0))
                if ts > 0:
                    top_speed = int(ts)
        except Exception:
            pass

        g2 = safe_float(q_rows[1]["gap"].replace("+", "")) if len(q_rows) > 1 and q_rows[1]["gap"] else 0

        pole_lap = {
            "driver": p1["name"],
            "code": code,
            "team": p1["team"],
            "time": p1["q3"],
            "gapToP2": g2,
            "tyre": "SOFT",
            "topSpeed": top_speed,
            "sectors": sectors,
            "lastYear": {},
        }
        # Try last year's pole — use event name, not round number (rounds shift between years)
        try:
            cur_name = ev.EventName
            ly_ev = fastf1.get_event(year - 1, cur_name)
            ly_q = ly_ev.get_session("Q")
            ly_q.load(telemetry=False, weather=False, messages=False)
            ly_results = ly_q.results
            if len(ly_results) > 0:
                ly_p1 = ly_results.iloc[0]
                ly_q3_td = ly_p1.get("Q3", pd.NaT)
                ly_time_str = fmt_timedelta_lap(ly_q3_td) if not pd.isna(ly_q3_td) else ""
                ly_time = parse_lap_time(ly_time_str)
                delta = 0
                if pole_time and ly_time:
                    delta = pole_time - ly_time
                pole_lap["lastYear"] = {
                    "year": year - 1,
                    "driver": str(ly_p1.get("FullName", "")),
                    "code": str(ly_p1.get("FullName", "")).split()[-1][:3].upper(),
                    "team": norm_team(str(ly_p1.get("TeamName", ""))),
                    "time": ly_time_str,
                    "delta": round(delta, 3) if delta else 0,
                }
        except Exception:
            pole_lap["lastYear"] = {}

    return q_rows, pole_lap


# ── race ─────────────────────────────────────────────────────────────

def fetch_race(year, round_num):
    ev = fastf1.get_event(year, round_num)
    r_session = ev.get_session("R")
    r_session.load(telemetry=False, weather=False, messages=False)
    results = r_session.results

    import pandas as pd

    race_rows = []
    winner_seconds = None
    for _, d in results.iterrows():
        pos = int(safe_float(d.get("Position", d.get("ClassifiedPosition", 0))))
        if pos == 0:
            continue
        name = str(d.get("FullName", d.get("BroadcastName", "")))
        team = norm_team(str(d.get("TeamName", "")))
        status = str(d.get("Status", "Finished"))
        pts = safe_float(d.get("Points", 0))

        # Time – FastF1 3.x returns pd.Timedelta, str gap, or NaT
        t = d.get("Time", pd.NaT)
        time_str = ""
        gap = ""

        if pd.isna(t):
            time_str = "DNF" if status not in ("Finished", "+1 Lap", "+1 lap", "+2 Laps", "+2 laps") else ""
        elif isinstance(t, pd.Timedelta):
            total_sec = t.total_seconds()
            if pos == 1:
                h = int(total_sec // 3600)
                m = int((total_sec % 3600) // 60)
                s = total_sec % 60
                time_str = f"{h}:{m:02d}:{s:06.3f}"
            else:
                # Gap from winner
                time_str = f"+{total_sec:.3f}"
        else:
            time_str = str(t)

        if pos == 1:
            winner_seconds = parse_race_time(time_str) if time_str else None
        elif time_str and winner_seconds is not None and time_str != "DNF" and not time_str.startswith("+"):
            rt = parse_race_time(time_str)
            if rt:
                gap = f"+{rt - winner_seconds:.3f}"
        elif time_str.startswith("+"):
            gap = time_str

        race_rows.append({
            "pos": pos,
            "name": name,
            "team": team,
            "time": time_str,
            "gap": gap,
            "status": status,
            "points": int(pts),
        })

    # Fastest lap
    fastest_lap = {}
    try:
        qlaps = r_session.laps.pick_quicklaps()
        if len(qlaps) > 0:
            fl = qlaps.loc[qlaps["LapTime"].idxmin()]
            lt_td = fl.get("LapTime", pd.NaT)
            lt_sec = lt_td.total_seconds() if not pd.isna(lt_td) else 0
            s1_td = fl.get("Sector1Time", pd.NaT)
            s2_td = fl.get("Sector2Time", pd.NaT)
            s3_td = fl.get("Sector3Time", pd.NaT)
            s1 = s1_td.total_seconds() if not pd.isna(s1_td) else 0
            s2 = s2_td.total_seconds() if not pd.isna(s2_td) else 0
            s3 = s3_td.total_seconds() if not pd.isna(s3_td) else 0
            sectors = {}
            if s1 > 0:
                sectors = {
                    "s1": fmt_seconds(s1),
                    "s2": fmt_seconds(s2),
                    "s3": fmt_seconds(s3),
                }
            # Resolve full driver name: laps rows only carry the 3-letter code,
            # so join via DriverNumber against race results (same as the pole card)
            fl_code = str(fl.get("Driver", ""))
            fl_full = ""
            try:
                fl_no = str(fl.get("DriverNumber", ""))
                if fl_no and len(r_session.results) > 0:
                    dr_row = r_session.results[r_session.results["DriverNumber"].astype(str) == fl_no]
                    if len(dr_row) > 0:
                        fl_full = str(dr_row.iloc[0].get("FullName", ""))
            except Exception:
                fl_full = ""
            fastest_lap = {
                "driver": fl_full or fl_code,
                "code": fl_code,
                "team": norm_team(str(fl.get("Team", ""))),
                "time": fmt_timedelta_lap(lt_td),
                "tyre": str(fl.get("Compound", "SOFT")),
                "topSpeed": int(safe_float(fl.get("SpeedST", 320))),
                "sectors": sectors,
                "lastYear": {},
            }
            # Try last year's fastest lap — use event name, not round number
            try:
                ly_ev = fastf1.get_event(year - 1, ev.EventName)
                ly_r = ly_ev.get_session("R")
                ly_r.load(telemetry=False, weather=False, messages=False)
                ly_qlaps = ly_r.laps.pick_quicklaps()
                if len(ly_qlaps) > 0:
                    ly_fl_row = ly_qlaps.loc[ly_qlaps["LapTime"].idxmin()]
                    ly_lt_td = ly_fl_row.get("LapTime", pd.NaT)
                    ly_lt_sec = ly_lt_td.total_seconds() if not pd.isna(ly_lt_td) else 0
                    delta = lt_sec - ly_lt_sec if lt_sec > 0 and ly_lt_sec > 0 else 0
                    # Same join for last year's fastest driver (laps -> DriverNumber -> FullName)
                    ly_code = str(ly_fl_row.get("Driver", ""))
                    ly_full = ""
                    try:
                        ly_no = str(ly_fl_row.get("DriverNumber", ""))
                        if ly_no and len(ly_r.results) > 0:
                            ly_dr_row = ly_r.results[ly_r.results["DriverNumber"].astype(str) == ly_no]
                            if len(ly_dr_row) > 0:
                                ly_full = str(ly_dr_row.iloc[0].get("FullName", ""))
                    except Exception:
                        ly_full = ""
                    fastest_lap["lastYear"] = {
                        "year": year - 1,
                        "driver": ly_full or ly_code,
                        "code": ly_code,
                        "team": norm_team(str(ly_fl_row.get("Team", ""))),
                        "time": fmt_timedelta_lap(ly_lt_td),
                        "delta": round(delta, 3),
                    }
            except Exception:
                fastest_lap["lastYear"] = {}
    except Exception:
        pass

    return race_rows, fastest_lap


# ── time utils ───────────────────────────────────────────────────────

def parse_lap_time(t):
    """Parse '1:17.207' → seconds float."""
    if not t or t in ("", "Q1 exit", "Q2 exit", "Q3 exit"):
        return None
    t = str(t).strip()
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    try:
        return float(t)
    except ValueError:
        return None


def parse_race_time(t):
    """Parse '1:39:56.180' → seconds float."""
    if not t:
        return None
    t = str(t).strip()
    parts = t.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    try:
        return float(t)
    except ValueError:
        return None


def fmt_timedelta_lap(td):
    """Convert pd.Timedelta to lap time string like '1:17.207' or '27.364'."""
    import pandas as pd
    if pd.isna(td):
        return ""
    secs = td.total_seconds()
    mins = int(secs // 60)
    rest = secs % 60
    if mins > 0:
        return f"{mins}:{rest:06.3f}"
    return f"{rest:.3f}"


def fmt_seconds(s):
    if s == 0:
        return ""
    mins = int(s // 60)
    secs = s % 60
    if mins > 0:
        return f"{mins}:{secs:06.3f}"
    return f"{secs:.3f}"


# ── main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now().year
    print(f"🏎️  Fetching {year} F1 season data via FastF1...")
    data = fetch_all(year)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Written to {OUTPUT}")
    print(f"   event: {data['event'].get('eventName', 'N/A')} (round {data['event'].get('round', '?')})")
    print(f"   next:  {data['nextEvent'].get('eventName', 'N/A')} (round {data['nextEvent'].get('round', '?')})")
    print(f"   standings: {len(data['standings'].get('drivers', []))} drivers, {len(data['standings'].get('constructors', []))} constructors")
    print(f"   updated: {data['lastUpdated']}")

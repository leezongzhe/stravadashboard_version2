"""Build an AI-safe snapshot from dashboard data and calculations.

This module deliberately has no database import. The dashboard passes its
already-loaded activity table and point loader into this calculation layer.
"""

import math
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.metrics import (
    activity_summary,
    aerobic_decoupling,
    best_efforts,
    exact_splits,
    heart_rate_zones,
    negative_split,
    prepare_trackpoints,
    quality_report,
)


def _clean(value):
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _records(frame):
    if frame is None or frame.empty:
        return []
    return _clean(frame.to_dict(orient="records"))


def _downsample_profile(data, limit=80):
    if data.empty:
        return []
    indices = np.linspace(0, len(data) - 1, min(limit, len(data)), dtype=int)
    sampled = data.iloc[np.unique(indices)].copy()
    sampled["distance_km"] = sampled["distance"] / 1000
    columns = ["distance_km", "moving_elapsed", "pace_smooth", "heart_rate", "hr_smooth", "altitude_smooth", "grade_percent", "speed_kmh"]
    return _records(sampled[columns].round(3))


def _route_summary(data):
    gps = data.dropna(subset=["latitude", "longitude"])
    result = {"gps_available": not gps.empty, "gps_point_count": int(len(gps)), "coordinates_shared": False}
    if len(gps) > 1:
        lat1, lon1 = np.radians(gps.iloc[0][["latitude", "longitude"]].astype(float))
        lat2, lon2 = np.radians(gps.iloc[-1][["latitude", "longitude"]].astype(float))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        result["start_to_finish_distance_m"] = round(float(6371000 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))), 1)
        result["appears_looped"] = result["start_to_finish_distance_m"] <= 150
    return result


def _activity_context(row, raw_points, config, activity_ref, include_name=False, include_exact_date=True, include_profile=True):
    data = prepare_trackpoints(raw_points, config)
    summary = activity_summary(data)
    summary["aerobic_decoupling_percent"] = aerobic_decoupling(data)
    summary["second_half_pace_change_percent"] = negative_split(data)
    zones = heart_rate_zones(data, config)
    split_frame = exact_splits(data)
    effort_frame = best_efforts(data)
    result = {
        "activity_reference": activity_ref,
        "activity_type": row.get("activity_type", "Unknown"),
        "start_time": row["start_time"] if include_exact_date else str(pd.Timestamp(row["start_time"]).date()),
        "activity_name": row.get("activity_name") if include_name else "Not shared",
        "metrics": summary,
        "heart_rate": {
            "available": bool(data["heart_rate"].notna().any()),
            "zones": _records(zones),
        },
        "splits": _records(split_frame),
        "best_efforts": _records(effort_frame),
        "route": _route_summary(data),
        "data_quality": quality_report(data),
        "available_samples": {
            "trackpoints": int(len(data)),
            "heart_rate": int(data["heart_rate"].notna().sum()),
            "gps": int(data[["latitude", "longitude"]].notna().all(axis=1).sum()),
            "altitude": int(data["altitude"].notna().sum()),
        },
    }
    if include_profile:
        result["chart_profile_samples"] = _downsample_profile(data)
    return _clean(result)


def _period_summary(frame, now_local, days):
    cutoff = now_local - pd.Timedelta(days=days)
    period = frame[(frame["local_start"] >= cutoff) & (frame["local_start"] <= now_local)]
    return {
        "days": days,
        "activities": int(len(period)),
        "active_days": int(period["local_start"].dt.date.nunique()),
        "distance_km": round(float(period["distance_km"].fillna(0).sum()), 2),
        "moving_hours": round(float(period["moving_seconds"].fillna(0).sum() / 3600), 2),
        "average_distance_km": round(float(period["distance_km"].mean()), 2) if not period.empty else None,
    }


def build_dashboard_context(activities, points_loader, config, now=None, selected_activity_id=None):
    """Return a rich, JSON-safe snapshot for today or one selected activity."""
    timezone = config.get("timezone", "UTC")
    now_local = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz=timezone)
    if now_local.tzinfo is None:
        now_local = now_local.tz_localize(timezone)
    else:
        now_local = now_local.tz_convert(timezone)

    frame = activities.copy()
    frame["start_time"] = pd.to_datetime(frame["start_time"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["start_time"])
    frame["local_start"] = frame["start_time"].dt.tz_convert(timezone)
    if "distance_km" not in frame:
        frame["distance_km"] = pd.to_numeric(frame.get("distance_m"), errors="coerce") / 1000
    if selected_activity_id is not None:
        selected = frame[frame["activity_id"].astype(str) == str(selected_activity_id)]
        if selected.empty:
            raise ValueError("The selected dashboard activity is no longer available.")
        now_local = selected.iloc[0]["local_start"]
        today = selected.copy()
        analysis_scope = "selected_activity"
        activity_reference_prefix = "selected"
    else:
        today = frame[frame["local_start"].dt.date == now_local.date()].sort_values("local_start")
        analysis_scope = "today"
        activity_reference_prefix = "today"

    include_name = bool(config.get("ai_include_activity_names", False))
    include_date = bool(config.get("ai_include_exact_dates", True))
    include_profile = bool(config.get("ai_include_chart_samples", True))
    today_contexts = [
        _activity_context(row, points_loader(row["activity_id"]), config, f"{activity_reference_prefix}-{index}", include_name, include_date, include_profile)
        for index, (_, row) in enumerate(today.iterrows(), 1)
    ]

    prior_limit = max(0, min(20, int(config.get("ai_comparison_activity_limit", 8))))
    prior = frame[frame["local_start"] < now_local].sort_values("local_start", ascending=False)
    if selected_activity_id is not None:
        prior = prior[prior["activity_id"].astype(str) != str(selected_activity_id)]
    prior = prior.head(prior_limit)
    prior_contexts = []
    for index, (_, row) in enumerate(prior.iterrows(), 1):
        item = _activity_context(row, points_loader(row["activity_id"]), config, f"prior-{index}", include_name, include_date, False)
        item.pop("splits", None)
        item.pop("best_efforts", None)
        prior_contexts.append(item)

    recent = frame[
        (frame["local_start"] >= now_local - pd.Timedelta(days=84))
        & (frame["local_start"] <= now_local)
    ].copy()
    recent_local_naive = recent["local_start"].dt.tz_localize(None)
    recent["week"] = recent_local_naive.dt.to_period("W-SUN").astype(str)
    recent["month"] = recent_local_naive.dt.to_period("M").astype(str)
    weekly = recent.groupby("week", as_index=False).agg(activities=("activity_id", "count"), distance_km=("distance_km", "sum"), moving_seconds=("moving_seconds", "sum"))
    history_frame = frame[frame["local_start"] <= now_local].copy()
    history_frame["month"] = history_frame["local_start"].dt.tz_localize(None).dt.to_period("M").astype(str)
    monthly = history_frame.groupby("month", as_index=False).agg(activities=("activity_id", "count"), distance_km=("distance_km", "sum"), moving_seconds=("moving_seconds", "sum"))

    zone_limits = config.get("zone_upper_percentages", [60, 70, 80, 90, 100])
    resting = int(config["resting_heart_rate"])
    maximum = int(config["maximum_heart_rate"])
    reserve = maximum - resting
    lower_limits = [0] + list(zone_limits[:-1])
    zone_definition = [
        {"zone": f"Z{index + 1}", "hr_reserve_percent": [int(low), int(high)], "bpm": [round(resting + reserve * low / 100), round(resting + reserve * high / 100)]}
        for index, (low, high) in enumerate(zip(lower_limits, zone_limits))
    ]
    return _clean({
        "schema_version": 1,
        "analysis_scope": analysis_scope,
        "generated_at": now_local,
        "timezone": timezone,
        "today": str(now_local.date()),
        "selected_activity_count": int(len(today_contexts)),
        "selected_activities": today_contexts,
        # Compatibility aliases retained for previously saved coach sessions.
        "today_activity_count": int(len(today_contexts)),
        "today_activities": today_contexts,
        "heart_rate_profile": {
            "method": "Heart-rate reserve (Karvonen)",
            "resting_heart_rate_bpm": resting,
            "maximum_heart_rate_bpm": maximum,
            "resting_source": config.get("resting_heart_rate_mode", "observed"),
            "maximum_source": config.get("maximum_heart_rate_mode", "observed"),
            "zones": zone_definition,
        },
        "training_baselines": [_period_summary(frame, now_local, days) for days in (7, 28, 84)],
        "weekly_history": _records(weekly.tail(12).round(2)),
        "monthly_history": _records(monthly.tail(12).round(2)),
        "recent_comparison_activities": prior_contexts,
        "privacy": {
            "exact_route_coordinates_shared": False,
            "activity_names_shared": include_name,
            "exact_dates_shared": include_date,
            "chart_samples_shared": include_profile,
        },
    })

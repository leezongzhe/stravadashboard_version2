import math

import numpy as np
import pandas as pd


BEST_EFFORT_DISTANCES = {
    "400 m": 400,
    "1 km": 1000,
    "1 mile": 1609.344,
    "3 km": 3000,
    "5 km": 5000,
    "10 km": 10000,
    "Half marathon": 21097.5,
}


def prepare_trackpoints(df, config):
    data = df.copy()
    data["time"] = pd.to_datetime(data["time"], errors="coerce", utc=True)
    numeric = ["latitude", "longitude", "altitude", "distance", "heart_rate", "speed"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["time"]).sort_values("time").drop_duplicates("time")

    data["dt"] = data["time"].diff().dt.total_seconds().clip(lower=0)
    data["dd"] = data["distance"].diff()
    derived_speed = data["dd"] / data["dt"].replace(0, np.nan)

    # Prefer the device-recorded TCX speed. Strava exports from some devices
    # contain one-second GPS samples while DistanceMeters changes only in
    # coarse steps; deriving speed exclusively from that quantized distance
    # incorrectly labels genuine running samples as stationary. When speed is
    # absent or zero, distance-derived speed remains the fallback. Long gaps
    # are independently rejected by maximum_moving_gap_seconds below.
    has_distance_interval = (
        data["distance"].notna()
        & data["distance"].shift().notna()
        & data["dt"].gt(0)
    )
    recorded_speed = data["speed"].where(data["speed"] > 0)
    data["effective_speed"] = recorded_speed.combine_first(
        derived_speed.where(has_distance_interval)
    )
    data["speed_kmh"] = data["effective_speed"] * 3.6
    data["pace_min_km"] = np.where(
        data["effective_speed"] > 0,
        1000 / data["effective_speed"] / 60,
        np.nan,
    )
    data.loc[~data["pace_min_km"].between(2, 20), "pace_min_km"] = np.nan

    window = max(3, int(config["altitude_smoothing_points"]))
    data["altitude_smooth"] = data["altitude"].rolling(window, center=True, min_periods=1).median()
    data["altitude_change"] = data["altitude_smooth"].diff()
    data["grade_percent"] = data["altitude_change"] / data["dd"].where(data["dd"] > 0) * 100
    data.loc[~data["grade_percent"].between(-30, 30), "grade_percent"] = np.nan
    data["pace_smooth"] = data["pace_min_km"].rolling(10, min_periods=3).mean()
    data["hr_smooth"] = data["heart_rate"].rolling(10, min_periods=3).mean()
    data["efficiency"] = data["effective_speed"] / data["heart_rate"].where(data["heart_rate"] > 0)
    data["moving"] = (
        (data["effective_speed"] > config["moving_speed_threshold_mps"])
        & (data["dt"] <= config["maximum_moving_gap_seconds"])
    )
    data["moving_dt"] = data["dt"].where(data["moving"], 0).fillna(0)
    data["moving_elapsed"] = data["moving_dt"].cumsum()
    return data.reset_index(drop=True)


def activity_summary(data):
    distance_m = data["distance"].max() if data["distance"].notna().any() else 0
    elapsed = data["dt"].fillna(0).sum()
    moving = data["moving_dt"].sum()
    altitude_change = data["altitude_change"].dropna()
    gain = altitude_change[altitude_change > 0].sum()
    loss = -altitude_change[altitude_change < 0].sum()
    moving_pace = moving / 60 / (distance_m / 1000) if distance_m > 0 and moving > 0 else np.nan
    valid_pace = data["pace_min_km"].dropna()
    consistency = valid_pace.std() / valid_pace.mean() * 100 if len(valid_pace) > 1 else np.nan
    return {
        "distance_km": distance_m / 1000,
        "elapsed_seconds": elapsed,
        "moving_seconds": moving,
        "stopped_seconds": max(0, elapsed - moving),
        # `pace` is the dashboard's primary pace and intentionally excludes
        # stationary intervals. Elapsed time remains available as a separate
        # descriptive value.
        "pace": moving_pace,
        "moving_pace": moving_pace,
        "avg_hr": data.loc[data["moving"], "heart_rate"].mean(),
        "max_hr": data["heart_rate"].max(),
        "avg_speed_kmh": data.loc[data["moving"], "speed_kmh"].mean(),
        "max_speed_kmh": data["speed_kmh"].max(),
        "elevation_gain": gain,
        "elevation_loss": loss,
        "pace_variability_percent": consistency,
    }


def exact_splits(data, interval_m=1000):
    valid = data.dropna(subset=["distance", "moving_elapsed"]).sort_values("distance")
    valid = valid.drop_duplicates("distance")
    if len(valid) < 2 or valid["distance"].max() < interval_m:
        return pd.DataFrame()
    elapsed = valid["moving_elapsed"].to_numpy()
    distances = valid["distance"].to_numpy()
    boundaries = np.arange(0, valid["distance"].max(), interval_m)
    if boundaries[-1] < distances[-1]:
        boundaries = np.append(boundaries, distances[-1])
    times = np.interp(boundaries, distances, elapsed)
    rows = []
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        duration = times[index + 1] - times[index]
        segment = valid[(valid["distance"] >= start) & (valid["distance"] <= end)]
        delta_km = (end - start) / 1000
        rows.append({
            "Split": index + 1,
            "Distance_km": delta_km,
            "Time_seconds": duration,
            "Pace_min_km": duration / 60 / delta_km,
            "Avg_HR": segment["heart_rate"].mean(),
            "Elevation_gain": segment["altitude_change"].clip(lower=0).sum(),
        })
    return pd.DataFrame(rows)


def best_efforts(data):
    valid = data.dropna(subset=["distance", "moving_elapsed"]).sort_values("distance").drop_duplicates("distance")
    if len(valid) < 2:
        return pd.DataFrame()
    distances = valid["distance"].to_numpy()
    elapsed = valid["moving_elapsed"].to_numpy()
    rows = []
    for label, target in BEST_EFFORT_DISTANCES.items():
        if distances[-1] < target:
            continue
        best = math.inf
        for start_index, start_distance in enumerate(distances):
            finish_distance = start_distance + target
            if finish_distance > distances[-1]:
                break
            finish_time = np.interp(finish_distance, distances, elapsed)
            best = min(best, finish_time - elapsed[start_index])
        if math.isfinite(best) and best > 0:
            rows.append({"Distance": label, "Time_seconds": best, "Pace_min_km": best / 60 / (target / 1000)})
    return pd.DataFrame(rows)


def heart_rate_zones(data, config):
    columns = ["Zone", "Lower_bpm", "Upper_bpm", "Seconds", "Percent"]
    if "heart_rate" not in data or not data["heart_rate"].notna().any():
        return pd.DataFrame(columns=columns)
    resting = config["resting_heart_rate"]
    maximum = config["maximum_heart_rate"]
    reserve = max(1, maximum - resting)
    upper_percentages = config.get(
        "zone_upper_percentages", [60, 70, 80, 90, 100]
    )
    if len(upper_percentages) != 5:
        upper_percentages = [60, 70, 80, 90, 100]
    upper_fractions = [float(value) / 100 for value in upper_percentages]
    lower_fractions = [0.0] + upper_fractions[:-1]
    boundaries = list(zip(lower_fractions, upper_fractions))
    rows = []
    moving_hr = data["moving"] & data["heart_rate"].notna()
    total = data.loc[moving_hr, "moving_dt"].sum()
    for number, (low, high) in enumerate(boundaries, 1):
        lower = resting + reserve * low
        upper = resting + reserve * high
        inclusive = "both" if number == len(boundaries) else "left"
        seconds = data.loc[
            moving_hr & data["heart_rate"].between(lower, upper, inclusive=inclusive),
            "moving_dt",
        ].sum()
        rows.append({
            "Zone": f"Z{number}",
            "Lower_bpm": round(lower),
            "Upper_bpm": round(min(upper, maximum)),
            "Seconds": seconds,
            "Percent": seconds / total * 100 if total else 0,
        })
    return pd.DataFrame(rows, columns=columns)


def aerobic_decoupling(data):
    valid = data[(data["moving"]) & data["efficiency"].notna() & data["distance"].notna()]
    if len(valid) < 20:
        return np.nan
    midpoint = (valid["distance"].min() + valid["distance"].max()) / 2
    first = valid.loc[valid["distance"] <= midpoint, "efficiency"].mean()
    second = valid.loc[valid["distance"] > midpoint, "efficiency"].mean()
    return (first / second - 1) * 100 if second > 0 else np.nan


def negative_split(data):
    valid = data.dropna(subset=["distance", "moving_elapsed"]).sort_values("distance").drop_duplicates("distance")
    if len(valid) < 2 or valid["distance"].max() <= 0:
        return np.nan
    distances = valid["distance"].to_numpy()
    elapsed = valid["moving_elapsed"].to_numpy()
    midpoint = distances[-1] / 2
    midpoint_time = np.interp(midpoint, distances, elapsed)
    first_pace = midpoint_time / midpoint
    second_pace = (elapsed[-1] - midpoint_time) / (distances[-1] - midpoint)
    return (second_pace - first_pace) / first_pace * 100 if first_pace > 0 else np.nan


def quality_report(data):
    time_gaps = data["dt"].dropna()
    gps_jump = data["dd"] / data["dt"].replace(0, np.nan)
    return {
        "points": len(data),
        "duplicate_times": int(data["time"].duplicated().sum()),
        "distance_reversals": int((data["dd"] < 0).sum()),
        "median_sampling_seconds": time_gaps.median(),
        "maximum_gap_seconds": time_gaps.max(),
        "gps_or_distance_spikes": int((gps_jump > 12).sum()),
        "missing_gps_percent": float((data[["latitude", "longitude"]].isna().any(axis=1)).mean() * 100),
        "missing_hr_percent": float(data["heart_rate"].isna().mean() * 100),
        "missing_altitude_percent": float(data["altitude"].isna().mean() * 100),
    }


def format_duration(seconds):
    if pd.isna(seconds):
        return "--"
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def format_pace(value):
    if pd.isna(value) or value <= 0 or np.isinf(value):
        return "--:--"
    minutes = int(value)
    seconds = round((value - minutes) * 60)
    if seconds == 60:
        minutes, seconds = minutes + 1, 0
    return f"{minutes}:{seconds:02d}"

import html
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from app.config import (
    DATA_DIR,
    DB_PATH,
    default_backup_directory,
    load_config,
    resolve_maximum_heart_rate,
    resolve_resting_heart_rate,
    save_config,
    worldwide_timezones,
)
from app.backup import BACKUP_SUFFIX, create_backup, inspect_backup, restore_backup
from app.ai_context import build_dashboard_context
from app.ai_provider import (
    DEFAULT_MODELS,
    PROVIDERS,
    generate_analysis,
    list_models,
)
from app.credential_store import delete_api_key, has_api_key, read_api_key, save_api_key
from app.database import (
    activity_heart_rate_extrema,
    current_heart_rate_records,
    initialize_database,
    refresh_heart_rate_records,
)
from app.metrics import (
    activity_summary,
    aerobic_decoupling,
    best_efforts,
    exact_splits,
    format_duration,
    format_pace,
    heart_rate_zones,
    negative_split,
    prepare_trackpoints,
    quality_report,
)


st.set_page_config(page_title="Strava Dashboard v2", page_icon="🏃", layout="wide")
initialize_database()
config = load_config()
hr_observations = refresh_heart_rate_records(
    config.get("minimum_valid_heart_rate", 40),
    config.get("maximum_valid_heart_rate", 240),
)
active_resting_hr, resting_hr_source = resolve_resting_heart_rate(
    config, hr_observations["observed_minimum"]
)
active_maximum_hr, maximum_hr_source = resolve_maximum_heart_rate(
    config, hr_observations["observed_maximum"]
)
if active_resting_hr >= active_maximum_hr:
    active_resting_hr = min(60, active_maximum_hr - 1)
    resting_hr_source = "Safety fallback: observed resting HR was not below maximum HR"
config["resting_heart_rate"] = active_resting_hr
config["maximum_heart_rate"] = active_maximum_hr

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at 92% 5%, rgba(227, 85, 50, 0.08), transparent 25rem), linear-gradient(145deg, #f8fafc 0%, #eef4f1 100%);
        font-family: Inter, "Segoe UI", Arial, sans-serif;
    }
    .block-container { max-width: 1500px; padding-top: 2rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: #17352b; letter-spacing: -0.025em; }
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(38, 92, 70, 0.12);
        border-radius: 20px;
        padding: 1rem 1.15rem;
        box-shadow: 0 8px 24px rgba(31, 72, 57, 0.07);
    }
    [data-testid="stMetricLabel"] { color: #587067; }
    [data-testid="stMetricValue"] {
        color: #17352b;
        font-size: clamp(1.45rem, 2.15vw, 2.3rem) !important;
        line-height: 1.12 !important;
        white-space: nowrap !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    [data-testid="stMetricValue"] > div,
    [data-testid="stMetricValue"] p {
        max-width: none !important;
        font-size: inherit !important;
        line-height: inherit !important;
        white-space: nowrap !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    [data-baseweb="select"] > div, [data-baseweb="input"] > div {
        border-radius: 14px !important;
        border-color: rgba(38, 92, 70, 0.16) !important;
        background: rgba(255, 255, 255, 0.90) !important;
    }
    [data-testid="stDataFrame"] {
        border-radius: 18px !important; overflow: hidden !important;
        border: 1px solid rgba(38, 92, 70, 0.10);
    }
    [data-testid="stPlotlyChart"], [data-testid="stDeckGlJsonChart"] {
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(38, 92, 70, 0.10);
        border-radius: 20px;
        padding: 0.55rem;
        box-shadow: 0 8px 24px rgba(31, 72, 57, 0.05);
        overflow: hidden;
    }
    .stTabs div[data-baseweb="tab-list"], .stTabs [role="tablist"] {
        gap: 0.4rem !important; width: fit-content; max-width: 100%;
        background: rgba(255, 255, 255, 0.82) !important;
        border: 1px solid rgba(38, 92, 70, 0.10);
        border-radius: 999px !important; padding: 0.38rem !important;
        box-shadow: 0 8px 24px rgba(31, 72, 57, 0.06);
        overflow-x: auto;
    }
    .stTabs button[data-baseweb="tab"], .stTabs [role="tab"] {
        min-height: 2.75rem !important; border: 0 !important;
        border-radius: 999px !important; padding: 0.55rem 1.05rem !important;
        background: transparent !important; color: #405c52 !important;
        overflow: hidden !important;
        transition: background-color 160ms ease, color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
    }
    .stTabs button[data-baseweb="tab"] > div,
    .stTabs button[data-baseweb="tab"] p,
    .stTabs [role="tab"] > div,
    .stTabs [role="tab"] p {
        border-radius: 999px !important; color: inherit !important;
    }
    .stTabs button[data-baseweb="tab"]:hover, .stTabs [role="tab"]:hover {
        background: #edf5f1 !important; color: #17352b !important;
    }
    .stTabs button[data-baseweb="tab"][aria-selected="true"],
    .stTabs [role="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #e85b37, #cf4325) !important;
        color: white !important;
        box-shadow: 0 6px 16px rgba(207, 67, 37, 0.26) !important;
        transform: translateY(-1px);
    }
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none !important; }
    section[data-testid="stSidebar"] > div {
        background: linear-gradient(180deg, #17352b 0%, #20483a 100%); color: #f4faf7;
    }
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] p { color: #f4faf7; }
    hr { border-color: rgba(38, 92, 70, 0.12); }
    .hr-report { display: grid; gap: 0.55rem; margin: 0.6rem 0 1.2rem; }
    .hr-report-row {
        display: grid; gap: 0.75rem; align-items: center;
        padding: 0.78rem 1rem; border-radius: 16px;
        background: rgba(255, 255, 255, 0.88);
        border: 1px solid rgba(38, 92, 70, 0.11);
        box-shadow: 0 5px 16px rgba(31, 72, 57, 0.045);
    }
    .hr-report-header {
        color: #587067; font-size: 0.82rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.035em;
        background: transparent; border: 0; box-shadow: none;
        padding-top: 0.3rem; padding-bottom: 0.3rem;
    }
    .hr-report-cell { min-width: 0; overflow-wrap: anywhere; color: #17352b; }
    .hr-analysis-link {
        display: inline-block; width: fit-content; padding: 0.42rem 0.8rem;
        border-radius: 999px; background: #edf5f1; color: #1f664e !important;
        font-weight: 650; text-decoration: none !important;
    }
    .hr-analysis-link:hover { background: #dcece5; color: #17352b !important; }
    @media (max-width: 800px) {
        .hr-report-row { grid-template-columns: 1fr !important; }
        .hr-report-header { display: none; }
    }
    .st-key-floating_ai_coach {
        position: fixed !important;
        right: 1.4rem;
        bottom: 1.25rem;
        z-index: 1000000;
        width: auto !important;
        padding: 0 !important;
        filter: drop-shadow(0 12px 24px rgba(23, 53, 43, 0.22));
    }
    .st-key-floating_ai_coach button {
        border-radius: 999px !important;
        min-height: 3.2rem !important;
        padding: 0.72rem 1.15rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stPopoverBody"] {
        width: min(440px, calc(100vw - 2rem)) !important;
        max-height: min(78vh, 760px) !important;
        overflow-y: auto !important;
        border-radius: 22px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60)
def load_activities():
    with sqlite3.connect(DB_PATH) as connection:
        return pd.read_sql_query(
            """
            SELECT activity_id, COALESCE(activity_name, 'Activity ' || activity_id) activity_name,
                   COALESCE(activity_type, 'Unknown') activity_type, start_time,
                   elapsed_seconds, moving_seconds, distance_m, source, import_status, retry_count,
                   last_error, updated_at
            FROM activities
            ORDER BY start_time DESC, updated_at DESC
            """,
            connection,
        )


@st.cache_data(ttl=60)
def load_points(activity_id):
    with sqlite3.connect(DB_PATH) as connection:
        return pd.read_sql_query(
            """
            SELECT time, latitude, longitude, altitude, distance, heart_rate, speed
            FROM trackpoints WHERE activity_id=? ORDER BY time
            """,
            connection,
            params=(str(activity_id),),
        )


def color_scale(value, minimum, maximum, reverse=False):
    if pd.isna(value):
        return [130, 130, 130, 150]
    ratio = .5 if maximum == minimum else np.clip((value - minimum) / (maximum - minimum), 0, 1)
    if reverse:
        ratio = 1 - ratio
    return [int(255 * ratio), int(255 * (1 - ratio)), 60, 210]


def month_name(month):
    return pd.Timestamp(year=2000, month=int(month), day=1).strftime("%B")


def activity_period_filter(frame, key_prefix, initial_activity_id=None):
    """Render year/month controls and return matching activities."""
    dated = frame.dropna(subset=["start_time"]).copy()
    years = sorted(dated["start_time"].dt.year.unique(), reverse=True)
    if not years:
        return dated
    target = dated[dated["activity_id"].astype(str) == str(initial_activity_id)]
    target_year = int(target.iloc[0]["start_time"].year) if not target.empty else None
    year_index = years.index(target_year) if target_year in years else 0
    key_suffix = f"_{initial_activity_id}" if initial_activity_id else ""
    year_column, month_column = st.columns(2)
    selected_year = year_column.selectbox(
        "Year", years, index=year_index, key=f"{key_prefix}_year{key_suffix}"
    )
    year_data = dated[dated["start_time"].dt.year == selected_year].copy()
    months = sorted(year_data["start_time"].dt.month.unique(), reverse=True)
    target_month = (
        int(target.iloc[0]["start_time"].month)
        if not target.empty and target_year == selected_year else None
    )
    month_index = months.index(target_month) if target_month in months else 0
    selected_month = month_column.selectbox(
        "Month", months, index=month_index, format_func=month_name,
        key=f"{key_prefix}_month{key_suffix}",
    )
    return year_data[year_data["start_time"].dt.month == selected_month].copy()


def add_activity_labels(frame):
    labelled = frame.copy()
    local_time = labelled["start_time"].dt.tz_convert(config["timezone"])
    labelled["label"] = (
        local_time.dt.strftime("%d %B %Y, %H:%M")
        + "  ·  "
        + labelled["distance_km"].round(2).astype(str)
        + " km"
    )
    return labelled


def activity_analysis_url(activity_id):
    return f"?view=activity&activity_id={quote(str(activity_id), safe='')}"


def timezone_label(timezone_name):
    """Show a readable IANA location together with its current UTC offset."""
    try:
        offset = datetime.now(ZoneInfo(timezone_name)).strftime("%z")
        formatted_offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
    except ZoneInfoNotFoundError:
        formatted_offset = "Unavailable"
    return f"{timezone_name.replace('_', ' ')}  ·  {formatted_offset}"


def render_linked_report(frame, columns):
    """Render rounded report rows with an explicit internal activity link."""
    template = " ".join("minmax(0, 1fr)" for _ in range(len(columns) + 1))
    parts = [f'<div class="hr-report" style="--report-columns:{len(columns) + 1}">']
    headings = "".join(
        f'<div class="hr-report-cell">{html.escape(label)}</div>'
        for label, _ in columns
    )
    parts.append(
        f'<div class="hr-report-row hr-report-header" style="grid-template-columns:{template}">'
        f'{headings}<div class="hr-report-cell">Activity analysis</div></div>'
    )
    for _, row in frame.iterrows():
        cells = "".join(
            f'<div class="hr-report-cell">{html.escape(str(row[field]))}</div>'
            for _, field in columns
        )
        url = html.escape(activity_analysis_url(row["activity_id"]), quote=True)
        parts.append(
            f'<div class="hr-report-row" style="grid-template-columns:{template}">'
            f'{cells}<div class="hr-report-cell"><a class="hr-analysis-link" '
            f'href="{url}" target="_self">Open analysis →</a></div></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


st.title("🏃 Strava Dashboard — Version 2")
st.caption("Deterministic synchronization, historical trends, best efforts, heart-rate zones and data-quality checks.")

activities = load_activities()
if activities.empty:
    st.warning("No activity metadata is available. Run `python sync.py --local-only` first.")

activities["start_time"] = pd.to_datetime(activities["start_time"], errors="coerce", utc=True)
activities["distance_km"] = activities["distance_m"] / 1000
imported = activities[activities["import_status"] == "imported"].copy()
requested_activity_id = str(st.query_params.get("activity_id", ""))
available_activity_ids = set(imported["activity_id"].astype(str))
if requested_activity_id not in available_activity_ids:
    requested_activity_id = ""
default_dashboard_tab = (
    "Activity analysis"
    if st.query_params.get("view") == "activity" and requested_activity_id
    else "Training history"
)

with st.sidebar:
    st.header("Dashboard controls")
    available_years = sorted(imported["start_time"].dropna().dt.year.unique(), reverse=True)
    selected_years = st.multiselect("Years", available_years, default=available_years[:1])
    activity_types = sorted(imported["activity_type"].dropna().unique())
    selected_types = st.multiselect("Activity types", activity_types, default=activity_types)
    st.divider()
    st.caption(f"Database: {DB_PATH.name}")
    st.caption(f"Timezone: {config['timezone']}")
    st.caption("Use `python sync.py --retry-failed` to retry unavailable records.")

filtered = imported.copy()
if selected_years:
    filtered = filtered[filtered["start_time"].dt.year.isin(selected_years)]
if selected_types:
    filtered = filtered[filtered["activity_type"].isin(selected_types)]

selected_activity_id = None
selected_activity_label = None
tab_history, tab_activity, tab_compare, tab_imports, tab_backup, tab_settings = st.tabs([
    "Training history", "Activity analysis", "Compare", "Import health", "Backup", "Settings"
], default=default_dashboard_tab, key="dashboard_section", on_change="rerun")

with tab_history:
    total_distance = filtered["distance_km"].sum()
    total_time = filtered["moving_seconds"].sum()
    longest = filtered["distance_km"].max()
    cols = st.columns(4)
    cols[0].metric("Activities", f"{len(filtered):,}")
    cols[1].metric("Distance", f"{total_distance:,.1f} km")
    cols[2].metric("Moving time", format_duration(total_time))
    cols[3].metric("Longest activity", f"{longest:.2f} km" if pd.notna(longest) else "--")

    history = filtered.dropna(subset=["start_time"]).copy()
    if not history.empty:
        local_dates = history["start_time"].dt.tz_convert(config["timezone"]).dt.tz_localize(None)
        history["Month"] = local_dates.dt.to_period("M").astype(str)
        monthly = history.groupby("Month", as_index=False).agg(
            Distance_km=("distance_km", "sum"), Activities=("activity_id", "count"),
            Duration_hours=("moving_seconds", lambda values: values.sum() / 3600),
        )
        left, right = st.columns(2)
        left.plotly_chart(px.bar(monthly, x="Month", y="Distance_km", title="Monthly distance"), width="stretch")
        right.plotly_chart(px.line(monthly, x="Month", y="Activities", markers=True, title="Monthly consistency"), width="stretch")

        history["Week starting"] = local_dates.dt.to_period("W-SUN").dt.start_time
        weekly = history.groupby("Week starting", as_index=False).agg(
            Distance_km=("distance_km", "sum"), Activities=("activity_id", "count"),
            Duration_hours=("moving_seconds", lambda values: values.sum() / 3600),
        )
        weekly_left, weekly_right = st.columns(2)
        weekly_left.plotly_chart(
            px.bar(
                weekly, x="Week starting", y="Distance_km", title="Weekly distance",
                labels={"Distance_km": "Distance (km)"},
            ),
            width="stretch",
        )
        weekly_right.plotly_chart(
            px.line(
                weekly, x="Week starting", y="Activities", markers=True,
                title="Weekly consistency", labels={"Activities": "Activities"},
            ),
            width="stretch",
        )

        history["Date"] = history["start_time"].dt.tz_convert(config["timezone"]).dt.date
        history["Weekday"] = history["start_time"].dt.tz_convert(config["timezone"]).dt.day_name().str[:3]
        history["Week"] = history["start_time"].dt.tz_convert(config["timezone"]).dt.strftime("%Y-W%U")
        calendar = history.groupby(["Week", "Weekday"], as_index=False)["distance_km"].sum()
        weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        fig_calendar = px.density_heatmap(
            calendar, x="Week", y="Weekday", z="distance_km", histfunc="sum",
            category_orders={"Weekday": weekday_order}, title="Training calendar (distance)",
            color_continuous_scale="Oranges",
        )
        st.plotly_chart(fig_calendar, width="stretch")

        st.subheader("Recent activities")
        display = history[["start_time", "activity_type", "distance_km", "moving_seconds"]].head(25).copy()
        display["Date"] = display["start_time"].dt.tz_convert(config["timezone"]).dt.strftime("%d %b %Y %H:%M")
        display["Moving time"] = display["moving_seconds"].apply(format_duration)
        display["Distance (km)"] = display["distance_km"].round(2)
        st.dataframe(display[["Date", "activity_type", "Distance (km)", "Moving time"]], hide_index=True, width="stretch")

with tab_activity:
    if imported.empty:
        st.info("No imported activities are available.")
    else:
        st.subheader("Choose an activity")
        choices = add_activity_labels(activity_period_filter(
            imported, "activity", requested_activity_id or None
        ))
        label_lookup = choices.set_index("activity_id")["label"].to_dict()
        choice_ids = list(choices["activity_id"])
        selected_index = (
            choice_ids.index(requested_activity_id)
            if requested_activity_id in choice_ids else 0
        )
        selected_id = st.selectbox(
            "Activity", choice_ids, index=selected_index,
            format_func=lambda value: label_lookup[value],
            key=f"activity_selection_{requested_activity_id or 'default'}",
        )
        selected_activity_id = selected_id
        selected_activity_label = label_lookup[selected_id]
        raw = load_points(selected_id)
        data = prepare_trackpoints(raw, config)
        has_heart_rate = data["heart_rate"].notna().any()
        summary = activity_summary(data)
        split_data = exact_splits(data)
        efforts = best_efforts(data)
        zones = heart_rate_zones(data, config)
        quality = quality_report(data)
        decoupling = aerobic_decoupling(data)
        split_change = negative_split(data)

        kpis = st.columns(6)
        kpis[0].metric("Distance", f"{summary['distance_km']:.2f} km")
        kpis[1].metric("Elapsed", format_duration(summary["elapsed_seconds"]))
        kpis[2].metric("Moving", format_duration(summary["moving_seconds"]))
        kpis[3].metric("Average moving pace", f"{format_pace(summary['pace'])}/km")
        kpis[4].metric("Average HR", f"{summary['avg_hr']:.0f} bpm" if pd.notna(summary["avg_hr"]) else "--")
        kpis[5].metric("Elevation gain", f"{summary['elevation_gain']:.0f} m")

        overview, splits_tab, route_tab, quality_tab = st.tabs(["Performance", "Splits & best efforts", "Route & elevation", "Data quality"])
        data["Distance (km)"] = data["distance"] / 1000

        with overview:
            indicators = st.columns(5)
            indicators[0].metric("Average moving speed", f"{summary['avg_speed_kmh']:.1f} km/h" if pd.notna(summary["avg_speed_kmh"]) else "--")
            indicators[1].metric("Stopped time", format_duration(summary["stopped_seconds"]))
            indicators[2].metric("Pace variability", f"{summary['pace_variability_percent']:.1f}%" if pd.notna(summary["pace_variability_percent"]) else "--")
            indicators[3].metric("Aerobic decoupling", f"{decoupling:+.1f}%" if pd.notna(decoupling) else "--")
            indicators[4].metric("Second-half change", f"{split_change:+.1f}%" if pd.notna(split_change) else "--")

            chart = go.Figure()
            chart.add_trace(go.Scatter(x=data["Distance (km)"], y=data["pace_smooth"], name="Pace", yaxis="y"))
            if has_heart_rate:
                chart.add_trace(go.Scatter(x=data["Distance (km)"], y=data["hr_smooth"], name="Heart rate", yaxis="y2"))
            chart.update_layout(
                height=430, xaxis_title="Distance (km)",
                yaxis=dict(title="Pace (min/km)", autorange="reversed"),
                legend=dict(orientation="h"),
            )
            if has_heart_rate:
                chart.update_layout(yaxis2=dict(title="Heart rate (bpm)", overlaying="y", side="right"))
            st.plotly_chart(chart, width="stretch")
            if has_heart_rate:
                st.plotly_chart(px.bar(zones, x="Zone", y="Seconds", color="Zone", title="Time in heart-rate zones", hover_data=["Percent", "Lower_bpm", "Upper_bpm"]), width="stretch")
            else:
                st.info("No heart-rate samples were recorded for this activity. Pace and GPS analysis remain available.")

        with splits_tab:
            if split_data.empty:
                st.info("This activity is shorter than one kilometer.")
            else:
                shown = split_data.copy()
                shown["Time"] = shown["Time_seconds"].apply(format_duration)
                shown["Pace"] = shown["Pace_min_km"].apply(format_pace)
                shown["Average HR"] = shown["Avg_HR"].apply(
                    lambda value: f"{value:.0f} bpm" if pd.notna(value) else "--"
                )
                st.dataframe(shown[["Split", "Distance_km", "Time", "Pace", "Average HR", "Elevation_gain"]], hide_index=True, width="stretch")
                st.plotly_chart(px.bar(split_data, x="Split", y="Pace_min_km", title="Split pace"), width="stretch")
            st.subheader("Best rolling efforts")
            if efforts.empty:
                st.info("Not enough data for best efforts.")
            else:
                effort_display = efforts.copy()
                effort_display["Time"] = effort_display["Time_seconds"].apply(format_duration)
                effort_display["Pace"] = effort_display["Pace_min_km"].apply(format_pace)
                st.dataframe(effort_display[["Distance", "Time", "Pace"]], hide_index=True, width="stretch")

        with route_tab:
            map_data = data.dropna(subset=["latitude", "longitude"]).copy()
            if map_data.empty:
                st.info("No GPS data is available.")
            else:
                color_choices = ["pace_min_km", "speed_kmh", "altitude_smooth"]
                if has_heart_rate:
                    color_choices.insert(0, "heart_rate")
                color_field = st.selectbox("Route color", color_choices)
                valid = map_data[color_field].dropna()
                minimum, maximum = (valid.min(), valid.max()) if not valid.empty else (0, 1)
                map_data["color"] = map_data[color_field].apply(lambda value: color_scale(value, minimum, maximum, color_field == "pace_min_km"))
                path = map_data[["longitude", "latitude"]].values.tolist()
                layers = [
                    pdk.Layer("PathLayer", [{"path": path}], get_path="path", get_color=[255, 255, 255, 170], width_min_pixels=3),
                    pdk.Layer("ScatterplotLayer", map_data, get_position="[longitude, latitude]", get_fill_color="color", get_radius=6, pickable=True),
                ]
                view = pdk.ViewState(latitude=map_data["latitude"].mean(), longitude=map_data["longitude"].mean(), zoom=13)
                tooltip_text = "Pace: {pace_min_km}\nAltitude: {altitude_smooth}"
                if has_heart_rate:
                    tooltip_text = "HR: {heart_rate}\n" + tooltip_text
                st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip={"text": tooltip_text}), width="stretch")
            elevation = data.dropna(subset=["Distance (km)", "altitude_smooth"])
            st.plotly_chart(px.area(elevation, x="Distance (km)", y="altitude_smooth", title="Smoothed elevation profile"), width="stretch")
            grade = data.dropna(subset=["Distance (km)", "grade_percent"])
            st.plotly_chart(px.line(grade, x="Distance (km)", y="grade_percent", title="Smoothed grade"), width="stretch")

        with quality_tab:
            quality_frame = pd.DataFrame([{"Measure": key.replace("_", " ").title(), "Value": value} for key, value in quality.items()])
            st.dataframe(quality_frame, hide_index=True, width="stretch")
            sampling = data["dt"].dropna()
            st.plotly_chart(px.histogram(sampling, nbins=30, title="Sampling interval"), width="stretch")
            st.dataframe(data, hide_index=True, width="stretch")

with tab_compare:
    if len(imported) < 2:
        st.info("At least two imported activities are required.")
    else:
        st.subheader("Compare activities from the same month")
        compare_choices = add_activity_labels(activity_period_filter(imported, "compare"))
        all_compare_choices = add_activity_labels(imported)
        compare_labels = all_compare_choices.set_index("activity_id")["label"].to_dict()

        # Keep existing selections available while the month filter changes,
        # allowing one comparison set to contain activities from many months.
        previous_choices = [
            activity_id
            for activity_id in st.session_state.get("comparison_activities", [])
            if activity_id in compare_labels
        ]
        visible_choices = list(compare_choices["activity_id"])
        comparison_options = list(dict.fromkeys(previous_choices + visible_choices))

        compare_ids = st.multiselect(
            "Select 2 to 5 activities", comparison_options,
            format_func=lambda value: compare_labels[value], max_selections=5,
            key="comparison_activities",
        )
        comparison_rows = []
        prepared_activities = {}
        for activity_id in compare_ids:
            prepared = prepare_trackpoints(load_points(activity_id), config)
            summary = activity_summary(prepared)
            summary["aerobic_decoupling"] = aerobic_decoupling(prepared)
            summary["second_half_change"] = negative_split(prepared)
            summary["Activity"] = compare_labels[activity_id]
            comparison_rows.append(summary)
            prepared_activities[activity_id] = prepared

        if len(comparison_rows) == 1:
            st.info("Select at least one more activity to begin the comparison.")

        if len(comparison_rows) >= 2:
            comparison = pd.DataFrame(comparison_rows)

            def show_number(value, suffix="", decimals=1, signed=False):
                if pd.isna(value):
                    return "--"
                sign = "+" if signed and value > 0 else ""
                return f"{sign}{value:.{decimals}f}{suffix}"

            metric_definitions = [
                ("Distance", "distance_km", lambda value: show_number(value, " km", 2)),
                ("Elapsed time", "elapsed_seconds", format_duration),
                ("Moving time", "moving_seconds", format_duration),
                ("Stopped time", "stopped_seconds", format_duration),
                ("Average moving pace", "moving_pace", lambda value: f"{format_pace(value)}/km"),
                ("Average heart rate", "avg_hr", lambda value: show_number(value, " bpm", 0)),
                ("Maximum heart rate", "max_hr", lambda value: show_number(value, " bpm", 0)),
                ("Average speed", "avg_speed_kmh", lambda value: show_number(value, " km/h", 2)),
                ("Maximum speed", "max_speed_kmh", lambda value: show_number(value, " km/h", 2)),
                ("Elevation gain", "elevation_gain", lambda value: show_number(value, " m", 0)),
                ("Elevation loss", "elevation_loss", lambda value: show_number(value, " m", 0)),
                ("Pace variability", "pace_variability_percent", lambda value: show_number(value, "%", 1)),
                ("Aerobic decoupling", "aerobic_decoupling", lambda value: show_number(value, "%", 1, True)),
                ("Second-half pace change", "second_half_change", lambda value: show_number(value, "%", 1, True)),
            ]

            matrix = {"Metric": [definition[0] for definition in metric_definitions]}
            for _, row in comparison.iterrows():
                matrix[row["Activity"]] = [
                    formatter(row[field])
                    for _, field, formatter in metric_definitions
                ]

            st.subheader("Performance comparison matrix")
            st.dataframe(pd.DataFrame(matrix), hide_index=True, width="stretch")
            st.caption(
                "For pace and second-half change, lower values are faster. "
                "Lower pace variability generally indicates steadier pacing."
            )

            pace_tab, heart_rate_tab, elevation_tab, relationship_tab = st.tabs([
                "Pace profiles", "Heart-rate profiles", "Elevation profiles", "Efficiency map"
            ])

            with pace_tab:
                figure = go.Figure()
                for activity_id, prepared in prepared_activities.items():
                    figure.add_trace(go.Scatter(
                        x=prepared["distance"] / 1000,
                        y=prepared["pace_smooth"],
                        name=compare_labels[activity_id],
                    ))
                figure.update_layout(height=460, xaxis_title="Distance (km)", yaxis_title="Pace (min/km)", yaxis_autorange="reversed")
                st.plotly_chart(figure, width="stretch")

            with heart_rate_tab:
                figure = go.Figure()
                activities_with_hr = 0
                for activity_id, prepared in prepared_activities.items():
                    if not prepared["heart_rate"].notna().any():
                        continue
                    activities_with_hr += 1
                    figure.add_trace(go.Scatter(
                        x=prepared["distance"] / 1000,
                        y=prepared["hr_smooth"],
                        name=compare_labels[activity_id],
                    ))
                figure.update_layout(height=460, xaxis_title="Distance (km)", yaxis_title="Heart rate (bpm)")
                if activities_with_hr:
                    st.plotly_chart(figure, width="stretch")
                    if activities_with_hr < len(prepared_activities):
                        st.caption("Activities without recorded heart rate are omitted from this HR-only chart.")
                else:
                    st.info("None of the selected activities contains heart-rate data.")

            with elevation_tab:
                figure = go.Figure()
                for activity_id, prepared in prepared_activities.items():
                    figure.add_trace(go.Scatter(
                        x=prepared["distance"] / 1000,
                        y=prepared["altitude_smooth"],
                        name=compare_labels[activity_id],
                    ))
                figure.update_layout(height=460, xaxis_title="Distance (km)", yaxis_title="Elevation (m)")
                st.plotly_chart(figure, width="stretch")

            with relationship_tab:
                relationship = comparison.dropna(subset=["avg_hr", "moving_pace"]).copy()
                relationship["Distance (km)"] = relationship["distance_km"]
                if relationship.empty:
                    st.info("Heart-rate efficiency cannot be calculated for the selected activities because no HR data is available.")
                else:
                    figure = px.scatter(
                        relationship,
                        x="avg_hr",
                        y="moving_pace",
                        size="Distance (km)",
                        color="Activity",
                        hover_data={
                            "Activity": True,
                            "Distance (km)": ":.2f",
                            "avg_hr": ":.0f",
                            "moving_pace": ":.2f",
                            "elevation_gain": ":.0f",
                        },
                        title="Moving pace versus average heart rate",
                    )
                    figure.update_yaxes(autorange="reversed", title="Moving pace (min/km)")
                    figure.update_xaxes(title="Average heart rate (bpm)")
                    figure.update_layout(height=470)
                    st.plotly_chart(figure, width="stretch")
                    if len(relationship) < len(comparison):
                        st.caption("Activities without recorded heart rate are omitted from this HR-only chart.")

with tab_imports:
    counts = activities.groupby("import_status").size().reset_index(name="Activities")
    st.plotly_chart(px.bar(counts, x="import_status", y="Activities", color="import_status", title="Import status"), width="stretch")
    problems = activities[activities["import_status"] != "imported"].copy()
    st.dataframe(problems[["activity_id", "source", "import_status", "retry_count", "last_error", "updated_at"]], hide_index=True, width="stretch")
    st.caption("A repeated download failure becomes `tcx_unavailable`; it will remain visible here without blocking future synchronization.")

with tab_backup:
    st.subheader("Local backup and restore")
    st.caption(
        "Backups contain the database, settings, and optionally the original TCX files. "
        "The private browser profile and Strava login session are never included."
    )
    backup_directory = default_backup_directory()
    st.info(f"Backup location: {backup_directory}")

    create_left, create_right = st.columns([2, 1])
    include_tcx = create_left.checkbox(
        "Include original TCX files",
        value=True,
        help="Recommended for a complete, independently recoverable backup.",
    )
    if create_right.button("Create local backup", type="primary", width="stretch"):
        try:
            created_backup = create_backup(include_tcx=include_tcx)
            st.session_state["created_backup_path"] = str(created_backup)
            st.success(f"Backup created: {created_backup.name}")
        except Exception as error:
            st.error(f"Backup could not be created: {error}")

    created_path = st.session_state.get("created_backup_path")
    if created_path and Path(created_path).exists():
        path = Path(created_path)
        st.download_button(
            "Download a copy",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/zip",
            width="stretch",
        )

    st.markdown("#### Restore a backup")
    uploaded_backup = st.file_uploader(
        "Choose a Strava Dashboard backup",
        type=[BACKUP_SUFFIX.removeprefix(".")],
        help="The file can be selected from any folder; it is restored to the app's managed data location.",
    )
    if uploaded_backup is not None:
        backup_bytes = uploaded_backup.getvalue()
        try:
            backup_details = inspect_backup(backup_bytes)
            detail_columns = st.columns(3)
            detail_columns[0].metric("TCX files", backup_details["tcx_count"])
            detail_columns[1].metric("Database", "Included" if backup_details["has_database"] else "Not included")
            detail_columns[2].metric("Settings", "Included" if backup_details["has_settings"] else "Not included")
            st.caption(f"Created: {backup_details['created_at']}")
            st.warning(
                "Restore replaces the current database and settings, then merges included TCX files. "
                "A safety backup of the current data is created first."
            )
            if st.button("Restore this backup", type="primary"):
                result = restore_backup(backup_bytes)
                st.cache_data.clear()
                safety = result.get("safety_backup")
                message = f"Restore completed; {result['restored_tcx']} TCX files restored."
                if safety:
                    message += f" Safety backup: {Path(safety).name}."
                st.success(message)
                st.rerun()
        except Exception as error:
            st.error(f"This backup cannot be restored: {error}")

    existing_backups = []
    if backup_directory.exists():
        existing_backups = sorted(
            backup_directory.glob(f"*{BACKUP_SUFFIX}"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:10]
    if existing_backups:
        st.markdown("#### Recent local backups")
        for index, path in enumerate(existing_backups):
            label, action = st.columns([4, 1])
            label.markdown(f"**{path.name}**  \n{path.stat().st_size / 1024 / 1024:.1f} MB")
            action.download_button(
                "Download",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/zip",
                key=f"download_backup_{index}_{path.name}",
                width="stretch",
            )
    st.caption(f"Managed application data: {DATA_DIR}")

with tab_settings:
    st.subheader("AI coach connection")
    st.caption(
        "Choose your own model provider. API keys are stored in Windows Credential Manager—not in "
        "config.json, SQLite, local backups, logs, or the packaged application."
    )
    st.warning(
        "Dashboard data sent to an external AI provider leaves this computer. Review the provider's "
        "privacy terms and the context preview before analysis; free services may handle data differently from paid services."
    )
    provider_options = list(PROVIDERS)
    current_provider = str(config.get("ai_provider", "gemini"))
    if current_provider not in provider_options:
        current_provider = "gemini"
    selected_provider = st.selectbox(
        "AI provider",
        provider_options,
        index=provider_options.index(current_provider),
        format_func=lambda value: PROVIDERS[value],
        key="ai_provider_selection",
    )
    with st.form("ai_connection_settings"):
        default_model = (
            str(config.get("ai_model", ""))
            if selected_provider == current_provider
            else DEFAULT_MODELS.get(selected_provider, "")
        )
        selected_model = st.text_input(
            "Model ID",
            value=default_model,
            placeholder=DEFAULT_MODELS.get(selected_provider, "model-name"),
        )
        selected_base_url = st.text_input(
            "Custom API base URL",
            value=str(config.get("ai_base_url", "")),
            placeholder="http://localhost:11434/v1",
            disabled=selected_provider != "openai_compatible",
            help="Used only by OpenAI-compatible servers. Include /v1 when required by that server.",
        )
        submitted_key = st.text_input(
            "API key",
            type="password",
            value="",
            placeholder="Leave blank to keep the currently stored key",
        )
        selected_instructions = st.text_area(
            "Personal coaching preferences",
            value=str(config.get("ai_additional_instructions", "")),
            placeholder="Example: I am preparing for a half marathon; prioritize sustainable aerobic development.",
        )
        privacy_left, privacy_middle, privacy_right = st.columns(3)
        include_names = privacy_left.checkbox(
            "Share activity names", value=bool(config.get("ai_include_activity_names", False))
        )
        include_dates = privacy_middle.checkbox(
            "Share exact timestamps", value=bool(config.get("ai_include_exact_dates", True)),
            help="When disabled, activity time is reduced to its calendar date; weekly and monthly trend labels remain.",
        )
        include_profiles = privacy_right.checkbox(
            "Share chart samples", value=bool(config.get("ai_include_chart_samples", True)),
            help="Downsampled pace, HR, elevation, grade, and speed values; never coordinates.",
        )
        ai_limits_left, ai_limits_right = st.columns(2)
        comparison_limit = ai_limits_left.number_input(
            "Recent comparison activities", min_value=0, max_value=20,
            value=int(config.get("ai_comparison_activity_limit", 8)), step=1,
        )
        output_tokens = ai_limits_right.number_input(
            "Maximum response tokens", min_value=256, max_value=8192,
            value=int(config.get("ai_max_output_tokens", 1800)), step=128,
        )
        save_ai_settings = st.form_submit_button("Save AI settings", type="primary")

    if save_ai_settings:
        if not selected_model.strip():
            st.error("A model ID is required.")
        elif selected_provider == "openai_compatible" and not selected_base_url.strip():
            st.error("A base URL is required for an OpenAI-compatible provider.")
        else:
            try:
                if submitted_key.strip():
                    save_api_key(selected_provider, submitted_key)
                save_config({
                    "ai_provider": selected_provider,
                    "ai_model": selected_model.strip(),
                    "ai_base_url": selected_base_url.strip() if selected_provider == "openai_compatible" else "",
                    "ai_additional_instructions": selected_instructions.strip(),
                    "ai_include_activity_names": bool(include_names),
                    "ai_include_exact_dates": bool(include_dates),
                    "ai_include_chart_samples": bool(include_profiles),
                    "ai_comparison_activity_limit": int(comparison_limit),
                    "ai_max_output_tokens": int(output_tokens),
                })
                st.success("AI settings saved securely.")
                st.rerun()
            except Exception as error:
                st.error(f"AI settings could not be saved: {error}")

    credential_columns = st.columns(2)
    if credential_columns[0].button("Test saved connection", width="stretch"):
        try:
            stored_key = read_api_key(current_provider)
            if not stored_key:
                raise ValueError("No API key is stored for this provider.")
            with st.spinner("Contacting the configured provider…"):
                models = list_models(current_provider, stored_key, config.get("ai_base_url", ""))
            configured_model = str(config.get("ai_model", ""))
            model_status = "available" if configured_model in models else "not returned by the model list"
            st.success(f"Connection succeeded. {len(models)} compatible models found; configured model is {model_status}.")
        except Exception as error:
            st.error(f"Connection test failed: {error}")
    if credential_columns[1].button("Delete saved API key", width="stretch"):
        try:
            deleted = delete_api_key(current_provider)
            st.success("Saved API key deleted." if deleted else "No saved API key was found.")
            st.rerun()
        except Exception as error:
            st.error(f"Saved API key could not be deleted: {error}")

    st.divider()
    st.subheader("Heart-rate profile and calculation settings")
    st.caption(
        "Automatic values are rebuilt from valid heart-rate samples in all imported TCX files. "
        "A new high or low record updates the active zones on the next dashboard refresh."
    )

    status_columns = st.columns(4)
    status_columns[0].metric("Active resting HR", f"{active_resting_hr} bpm")
    status_columns[1].metric("Active maximum HR", f"{active_maximum_hr} bpm")
    status_columns[2].metric(
        "Lowest activity HR",
        f"{hr_observations['observed_minimum']} bpm"
        if hr_observations["observed_minimum"] is not None else "No data",
    )
    status_columns[3].metric(
        "Highest activity HR",
        f"{hr_observations['observed_maximum']} bpm"
        if hr_observations["observed_maximum"] is not None else "No data",
    )
    st.caption(f"Resting-HR source: {resting_hr_source} · Maximum-HR source: {maximum_hr_source}")
    st.warning(
        "The lowest HR recorded during exercise is not a clinical resting-heart-rate measurement. "
        "For more accurate zones, enter a morning, sleep, or clinician-measured resting HR manually."
    )

    with st.form("dashboard_settings"):
        source_left, source_right = st.columns(2)
        resting_mode_label = source_left.radio(
            "Resting-heart-rate source",
            ["Automatic: lowest downloaded TCX value", "Manual override"],
            index=1 if config.get("resting_heart_rate_mode") == "manual" else 0,
        )
        maximum_mode_label = source_right.radio(
            "Maximum-heart-rate source",
            ["Automatic: highest downloaded TCX value", "Manual override"],
            index=1 if config.get("maximum_heart_rate_mode") == "manual" else 0,
        )

        manual_left, manual_right = st.columns(2)
        manual_resting = manual_left.number_input(
            "Manual resting HR (bpm)", min_value=30, max_value=140,
            value=int(config.get("manual_resting_heart_rate") or active_resting_hr), step=1,
        )
        manual_maximum = manual_right.number_input(
            "Manual maximum HR (bpm)", min_value=100, max_value=240,
            value=int(config.get("manual_maximum_heart_rate") or active_maximum_hr), step=1,
        )

        st.markdown("#### Heart-rate zone upper limits")
        st.caption(
            "Zones use heart-rate reserve: resting HR + percentage × (maximum HR − resting HR)."
        )
        configured_zone_limits = config.get("zone_upper_percentages", [60, 70, 80, 90, 100])
        if len(configured_zone_limits) != 5:
            configured_zone_limits = [60, 70, 80, 90, 100]
        zone_columns = st.columns(5)
        zone_limits = [
            zone_columns[index].number_input(
                f"Zone {index + 1} upper (%)", min_value=1, max_value=100,
                value=int(configured_zone_limits[index]), step=1,
            )
            for index in range(5)
        ]

        st.markdown("#### Data-quality and dashboard settings")
        valid_left, valid_right, timezone_column = st.columns(3)
        minimum_valid_hr = valid_left.number_input(
            "Minimum valid sensor HR", min_value=20, max_value=150,
            value=int(config.get("minimum_valid_heart_rate", 40)), step=1,
        )
        maximum_valid_hr = valid_right.number_input(
            "Maximum valid sensor HR", min_value=120, max_value=260,
            value=int(config.get("maximum_valid_heart_rate", 240)), step=1,
        )
        timezone_options = worldwide_timezones()
        current_timezone = str(config.get("timezone", "UTC"))
        if current_timezone not in timezone_options:
            timezone_options.append(current_timezone)
            timezone_options.sort()
        timezone_name = timezone_column.selectbox(
            "Timezone",
            timezone_options,
            index=timezone_options.index(current_timezone),
            format_func=timezone_label,
            help=(
                "Search the worldwide IANA catalog by region or city. "
                "The displayed UTC offset reflects the current date and daylight-saving rules."
            ),
        )

        advanced_left, advanced_middle, advanced_right = st.columns(3)
        moving_threshold = advanced_left.number_input(
            "Moving threshold (m/s)", min_value=0.1, max_value=3.0,
            value=float(config.get("moving_speed_threshold_mps", 0.5)), step=0.1,
        )
        maximum_gap = advanced_middle.number_input(
            "Maximum moving gap (seconds)", min_value=1, max_value=120,
            value=int(config.get("maximum_moving_gap_seconds", 10)), step=1,
        )
        altitude_window = advanced_right.number_input(
            "Altitude smoothing points", min_value=3, max_value=101,
            value=int(config.get("altitude_smoothing_points", 15)), step=2,
        )
        retry_limit = st.number_input(
            "Automatic download retry limit", min_value=1, max_value=10,
            value=int(config.get("automatic_retry_limit", 2)), step=1,
        )
        backup_destination = st.text_input(
            "Local backup folder",
            value=str(config.get("backup_directory", "")),
            placeholder=str(default_backup_directory()),
            help="Leave blank to use Documents\\Strava Dashboard\\Backups.",
        )

        save_settings = st.form_submit_button("Save settings", type="primary")

    if save_settings:
        errors = []
        if not all(zone_limits[index] < zone_limits[index + 1] for index in range(4)):
            errors.append("Zone upper limits must increase strictly from Zone 1 to Zone 5.")
        if zone_limits[-1] != 100:
            errors.append("Zone 5 must end at 100%.")
        if minimum_valid_hr >= maximum_valid_hr:
            errors.append("Minimum valid sensor HR must be below maximum valid sensor HR.")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            errors.append("Timezone is not a recognized IANA timezone name.")

        candidate_resting = (
            int(manual_resting)
            if resting_mode_label == "Manual override"
            else hr_observations["observed_minimum"] or int(config.get("fallback_resting_heart_rate", 60))
        )
        candidate_maximum = (
            int(manual_maximum)
            if maximum_mode_label == "Manual override"
            else hr_observations["observed_maximum"] or int(config.get("fallback_maximum_heart_rate", 190))
        )
        if candidate_resting >= candidate_maximum:
            errors.append("The active resting HR must be lower than the active maximum HR.")

        if errors:
            for error in errors:
                st.error(error)
        else:
            save_config({
                "resting_heart_rate_mode": (
                    "manual" if resting_mode_label == "Manual override" else "observed"
                ),
                "manual_resting_heart_rate": int(manual_resting),
                "maximum_heart_rate_mode": (
                    "manual" if maximum_mode_label == "Manual override" else "observed"
                ),
                "manual_maximum_heart_rate": int(manual_maximum),
                "zone_upper_percentages": [int(value) for value in zone_limits],
                "minimum_valid_heart_rate": int(minimum_valid_hr),
                "maximum_valid_heart_rate": int(maximum_valid_hr),
                "timezone": timezone_name,
                "moving_speed_threshold_mps": float(moving_threshold),
                "maximum_moving_gap_seconds": int(maximum_gap),
                "altitude_smoothing_points": int(altitude_window),
                "automatic_retry_limit": int(retry_limit),
                "backup_directory": backup_destination.strip(),
            })
            refresh_heart_rate_records(minimum_valid_hr, maximum_valid_hr)
            st.cache_data.clear()
            st.success("Settings saved. Heart-rate records and zones were recalculated.")
            st.rerun()

    reserve = active_maximum_hr - active_resting_hr
    zone_rows = []
    previous_limit = 0
    for zone_number, upper_limit in enumerate(config.get("zone_upper_percentages", [60, 70, 80, 90, 100]), 1):
        lower_bpm = active_resting_hr + reserve * previous_limit / 100
        upper_bpm = active_resting_hr + reserve * upper_limit / 100
        zone_rows.append({
            "Zone": f"Zone {zone_number}",
            "HR reserve interval": f"{previous_limit}–{upper_limit}%",
            "Active interval": f"{round(lower_bpm)}–{round(upper_bpm)} bpm",
        })
        previous_limit = upper_limit
    st.markdown("#### Current calculated zones")
    st.dataframe(pd.DataFrame(zone_rows), hide_index=True, width="stretch")

    history_rows = [dict(row) for row in current_heart_rate_records()]
    st.markdown("#### Current all-time HR records")
    if history_rows:
        record_frame = pd.DataFrame(history_rows)
        record_frame["Record"] = record_frame["record_type"].map({
            "minimum": "New lowest activity HR",
            "maximum": "New highest activity HR",
        })
        record_frame["Heart rate"] = record_frame["heart_rate"].astype(str) + " bpm"
        record_frame["Observed"] = pd.to_datetime(
            record_frame["observed_at"], errors="coerce", utc=True
        ).dt.tz_convert(config["timezone"]).dt.strftime("%d %b %Y %H:%M")
        render_linked_report(
            record_frame,
            [("Record", "Record"), ("Heart rate", "Heart rate"), ("Observed", "Observed")],
        )
    else:
        st.info("No valid TCX heart-rate records have been imported yet.")

    st.markdown("#### Highest-HR activities")
    available_hr_activities = int(hr_observations.get("activities_with_hr", 0))
    if available_hr_activities:
        saved_highest_hr_limit = config.get("highest_hr_activity_limit")
        initial_highest_hr_limit = (
            max(1, min(int(saved_highest_hr_limit), available_hr_activities))
            if saved_highest_hr_limit is not None
            else available_hr_activities
        )
        highest_hr_limit = st.number_input(
            "Show top N activities",
            min_value=1,
            max_value=available_hr_activities,
            value=initial_highest_hr_limit,
            step=1,
            key="highest_hr_activity_limit",
            help=(
                "Choose how many activities to include after ranking by maximum valid HR. "
                "Your selection is saved as the default for future dashboard sessions."
            ),
        )
        if int(highest_hr_limit) != saved_highest_hr_limit:
            save_config({"highest_hr_activity_limit": int(highest_hr_limit)})
            config["highest_hr_activity_limit"] = int(highest_hr_limit)
        st.caption(f"Saved default: top {int(highest_hr_limit)} activities")
    else:
        highest_hr_limit = 1
    st.caption(
        "Selection method: imported activities with at least one HR sample inside the "
        f"configured valid range ({config.get('minimum_valid_heart_rate', 40)}–"
        f"{config.get('maximum_valid_heart_rate', 240)} bpm) are ranked by their single "
        "highest valid TCX sample. The chosen top N are shown; ties are ordered by activity date."
    )
    extrema_rows = [dict(row) for row in activity_heart_rate_extrema(highest_hr_limit)]
    if extrema_rows:
        extrema_frame = pd.DataFrame(extrema_rows)
        extrema_frame["Activity date"] = pd.to_datetime(
            extrema_frame["start_time"], errors="coerce", utc=True
        ).dt.tz_convert(config["timezone"]).dt.strftime("%d %b %Y %H:%M")
        extrema_frame = extrema_frame.merge(
            activities[["activity_id", "distance_km"]], on="activity_id", how="left"
        )
        extrema_frame["Distance"] = extrema_frame["distance_km"].map(
            lambda value: f"{value:.2f} km" if pd.notna(value) else "--"
        )
        extrema_frame = extrema_frame.rename(columns={
            "minimum_hr": "Minimum HR", "maximum_hr": "Maximum HR",
        })
        render_linked_report(
            extrema_frame,
            [
                ("Activity date", "Activity date"),
                ("Distance", "Distance"),
                ("Minimum HR", "Minimum HR"),
                ("Maximum HR", "Maximum HR"),
            ],
        )
    else:
        st.info("No activities with valid heart-rate samples are available.")

# Floating, page-aware coach. It is intentionally rendered outside the tab
# hierarchy so it behaves like a normal website assistant instead of another
# dashboard report page.
active_dashboard_section = st.session_state.get("dashboard_section", default_dashboard_tab)
coach_target = str(selected_activity_id) if selected_activity_id is not None else ""
if st.session_state.get("ai_coach_target") != coach_target:
    st.session_state["ai_coach_target"] = coach_target
    st.session_state.pop("ai_coach_context", None)
    st.session_state.pop("ai_coach_answer", None)
    st.session_state.pop("ai_follow_up_question", None)

ai_provider = str(config.get("ai_provider", "gemini"))
ai_model = str(config.get("ai_model") or DEFAULT_MODELS.get(ai_provider, ""))
try:
    ai_key_available = has_api_key(ai_provider)
except Exception:
    ai_key_available = False

with st.container(key="floating_ai_coach"):
    with st.popover("✨ AI Coach", type="primary", key="ai_coach_popover"):
        st.markdown("### Activity coach")
        st.caption(
            f"{PROVIDERS.get(ai_provider, ai_provider)} · {ai_model or 'Model not configured'}"
        )

        activity_page_open = (
            active_dashboard_section == "Activity analysis"
            and selected_activity_id is not None
        )
        if not activity_page_open:
            st.info("Open **Activity analysis** and choose a training record. I will analyze that page.")
        else:
            st.markdown(f"**Current page**  \n{selected_activity_label}")
            st.caption(
                "Uses the visible activity metrics plus zones, splits, route characteristics, "
                "data quality and earlier training trends. GPS coordinates are never sent."
            )
            if not ai_key_available or not ai_model:
                st.warning("Configure the AI provider, model and API key in **Settings** first.")

            if st.button("Prepare current page", key="prepare_ai_page_context", width="stretch"):
                try:
                    with st.spinner("Preparing this activity and its earlier training context…"):
                        st.session_state["ai_coach_context"] = build_dashboard_context(
                            imported,
                            load_points,
                            config,
                            selected_activity_id=selected_activity_id,
                        )
                    st.session_state.pop("ai_coach_answer", None)
                except Exception as error:
                    st.error(f"The current page could not be prepared: {error}")

            context = st.session_state.get("ai_coach_context")
            if context is not None:
                activity_context = context["selected_activities"][0]
                metric = activity_context["metrics"]
                preview_columns = st.columns(3)
                preview_columns[0].metric("Distance", f"{metric['distance_km']:.2f} km")
                preview_columns[1].metric("Moving", format_duration(metric["moving_seconds"]))
                preview_columns[2].metric("Pace", f"{format_pace(metric['moving_pace'])}/km")

                with st.expander("Review data that will be sent"):
                    st.json(context, expanded=False)

                consent = st.checkbox(
                    "Send this previewed data to my configured AI provider",
                    value=False,
                    key="ai_transfer_consent",
                )
                if st.button(
                    "Analyze this activity",
                    type="primary",
                    width="stretch",
                    disabled=not (consent and ai_key_available and ai_model),
                ):
                    try:
                        with st.spinner("Analyzing this activity page…"):
                            st.session_state["ai_coach_answer"] = generate_analysis(
                                ai_provider,
                                read_api_key(ai_provider),
                                ai_model,
                                context,
                                config.get("ai_additional_instructions", ""),
                                config.get("ai_base_url", ""),
                                config.get("ai_max_output_tokens", 1800),
                            )
                    except Exception as error:
                        st.error(f"Analysis failed: {error}")

                existing_answer = st.session_state.get("ai_coach_answer")
                if existing_answer:
                    st.markdown("#### Coach response")
                    st.markdown(existing_answer)
                    follow_up = st.text_area(
                        "Ask about this activity",
                        placeholder="For example: What does the zone distribution suggest about this session?",
                        key="ai_follow_up_question",
                    )
                    if st.button(
                        "Send follow-up",
                        width="stretch",
                        disabled=not (follow_up.strip() and consent and ai_key_available),
                    ):
                        try:
                            with st.spinner("Reviewing the same activity page…"):
                                st.session_state["ai_coach_answer"] = generate_analysis(
                                    ai_provider,
                                    read_api_key(ai_provider),
                                    ai_model,
                                    context,
                                    config.get("ai_additional_instructions", ""),
                                    config.get("ai_base_url", ""),
                                    config.get("ai_max_output_tokens", 1800),
                                    follow_up=follow_up,
                                    previous_answer=existing_answer,
                                )
                            st.rerun()
                        except Exception as error:
                            st.error(f"Follow-up failed: {error}")

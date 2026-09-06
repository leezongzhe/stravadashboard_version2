import html
import sqlite3
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from app.config import (
    DB_PATH,
    load_config,
    resolve_maximum_heart_rate,
    resolve_resting_heart_rate,
    save_config,
)
from app.database import (
    activity_heart_rate_extrema,
    heart_rate_record_history,
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
                   elapsed_seconds, distance_m, source, import_status, retry_count,
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

tab_history, tab_activity, tab_compare, tab_imports, tab_settings = st.tabs([
    "Training history", "Activity analysis", "Compare", "Import health", "Settings"
], default=default_dashboard_tab, key="dashboard_section")

with tab_history:
    total_distance = filtered["distance_km"].sum()
    total_time = filtered["elapsed_seconds"].sum()
    longest = filtered["distance_km"].max()
    cols = st.columns(4)
    cols[0].metric("Activities", f"{len(filtered):,}")
    cols[1].metric("Distance", f"{total_distance:,.1f} km")
    cols[2].metric("Recorded time", format_duration(total_time))
    cols[3].metric("Longest activity", f"{longest:.2f} km" if pd.notna(longest) else "--")

    history = filtered.dropna(subset=["start_time"]).copy()
    if not history.empty:
        local_dates = history["start_time"].dt.tz_convert(config["timezone"]).dt.tz_localize(None)
        history["Month"] = local_dates.dt.to_period("M").astype(str)
        monthly = history.groupby("Month", as_index=False).agg(
            Distance_km=("distance_km", "sum"), Activities=("activity_id", "count"),
            Duration_hours=("elapsed_seconds", lambda values: values.sum() / 3600),
        )
        left, right = st.columns(2)
        left.plotly_chart(px.bar(monthly, x="Month", y="Distance_km", title="Monthly distance"), width="stretch")
        right.plotly_chart(px.line(monthly, x="Month", y="Activities", markers=True, title="Monthly consistency"), width="stretch")

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
        display = history[["start_time", "activity_type", "distance_km", "elapsed_seconds"]].head(25).copy()
        display["Date"] = display["start_time"].dt.tz_convert(config["timezone"]).dt.strftime("%d %b %Y %H:%M")
        display["Duration"] = display["elapsed_seconds"].apply(format_duration)
        display["Distance (km)"] = display["distance_km"].round(2)
        st.dataframe(display[["Date", "activity_type", "Distance (km)", "Duration"]], hide_index=True, width="stretch")

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
        raw = load_points(selected_id)
        data = prepare_trackpoints(raw, config)
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
        kpis[3].metric("Average pace", f"{format_pace(summary['pace'])}/km")
        kpis[4].metric("Average HR", f"{summary['avg_hr']:.0f} bpm" if pd.notna(summary["avg_hr"]) else "--")
        kpis[5].metric("Elevation gain", f"{summary['elevation_gain']:.0f} m")

        overview, splits_tab, route_tab, quality_tab = st.tabs(["Performance", "Splits & best efforts", "Route & elevation", "Data quality"])
        data["Distance (km)"] = data["distance"] / 1000

        with overview:
            indicators = st.columns(5)
            indicators[0].metric("Moving pace", f"{format_pace(summary['moving_pace'])}/km")
            indicators[1].metric("Stopped time", format_duration(summary["stopped_seconds"]))
            indicators[2].metric("Pace variability", f"{summary['pace_variability_percent']:.1f}%" if pd.notna(summary["pace_variability_percent"]) else "--")
            indicators[3].metric("Aerobic decoupling", f"{decoupling:+.1f}%" if pd.notna(decoupling) else "--")
            indicators[4].metric("Second-half change", f"{split_change:+.1f}%" if pd.notna(split_change) else "--")

            chart = go.Figure()
            chart.add_trace(go.Scatter(x=data["Distance (km)"], y=data["pace_smooth"], name="Pace", yaxis="y"))
            chart.add_trace(go.Scatter(x=data["Distance (km)"], y=data["hr_smooth"], name="Heart rate", yaxis="y2"))
            chart.update_layout(
                height=430, xaxis_title="Distance (km)",
                yaxis=dict(title="Pace (min/km)", autorange="reversed"),
                yaxis2=dict(title="Heart rate (bpm)", overlaying="y", side="right"),
                legend=dict(orientation="h"),
            )
            st.plotly_chart(chart, width="stretch")
            st.plotly_chart(px.bar(zones, x="Zone", y="Seconds", color="Zone", title="Time in heart-rate zones", hover_data=["Percent", "Lower_bpm", "Upper_bpm"]), width="stretch")

        with splits_tab:
            if split_data.empty:
                st.info("This activity is shorter than one kilometer.")
            else:
                shown = split_data.copy()
                shown["Time"] = shown["Time_seconds"].apply(format_duration)
                shown["Pace"] = shown["Pace_min_km"].apply(format_pace)
                st.dataframe(shown[["Split", "Distance_km", "Time", "Pace", "Avg_HR", "Elevation_gain"]], hide_index=True, width="stretch")
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
                color_field = st.selectbox("Route color", ["heart_rate", "pace_min_km", "speed_kmh", "altitude_smooth"])
                valid = map_data[color_field].dropna()
                minimum, maximum = (valid.min(), valid.max()) if not valid.empty else (0, 1)
                map_data["color"] = map_data[color_field].apply(lambda value: color_scale(value, minimum, maximum, color_field == "pace_min_km"))
                path = map_data[["longitude", "latitude"]].values.tolist()
                layers = [
                    pdk.Layer("PathLayer", [{"path": path}], get_path="path", get_color=[255, 255, 255, 170], width_min_pixels=3),
                    pdk.Layer("ScatterplotLayer", map_data, get_position="[longitude, latitude]", get_fill_color="color", get_radius=6, pickable=True),
                ]
                view = pdk.ViewState(latitude=map_data["latitude"].mean(), longitude=map_data["longitude"].mean(), zoom=13)
                st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip={"text": "HR: {heart_rate}\nPace: {pace_min_km}\nAltitude: {altitude_smooth}"}), width="stretch")
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
                ("Average pace", "pace", lambda value: f"{format_pace(value)}/km"),
                ("Moving pace", "moving_pace", lambda value: f"{format_pace(value)}/km"),
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
                for activity_id, prepared in prepared_activities.items():
                    figure.add_trace(go.Scatter(
                        x=prepared["distance"] / 1000,
                        y=prepared["hr_smooth"],
                        name=compare_labels[activity_id],
                    ))
                figure.update_layout(height=460, xaxis_title="Distance (km)", yaxis_title="Heart rate (bpm)")
                st.plotly_chart(figure, width="stretch")

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
                relationship = comparison.copy()
                relationship["Distance (km)"] = relationship["distance_km"]
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

with tab_imports:
    counts = activities.groupby("import_status").size().reset_index(name="Activities")
    st.plotly_chart(px.bar(counts, x="import_status", y="Activities", color="import_status", title="Import status"), width="stretch")
    problems = activities[activities["import_status"] != "imported"].copy()
    st.dataframe(problems[["activity_id", "source", "import_status", "retry_count", "last_error", "updated_at"]], hide_index=True, width="stretch")
    st.caption("A repeated download failure becomes `tcx_unavailable`; it will remain visible here without blocking future synchronization.")

with tab_settings:
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
        timezone_name = timezone_column.text_input(
            "Timezone", value=str(config.get("timezone", "UTC")),
            help="Use an IANA name such as Asia/Kuala_Lumpur or Europe/London.",
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

    history_rows = [dict(row) for row in heart_rate_record_history()]
    st.markdown("#### All-time HR record changes")
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

    extrema_rows = [dict(row) for row in activity_heart_rate_extrema(25)]
    st.markdown("#### Highest-HR activities")
    st.caption(
        "Selection method: imported activities with at least one HR sample inside the "
        f"configured valid range ({config.get('minimum_valid_heart_rate', 40)}–"
        f"{config.get('maximum_valid_heart_rate', 240)} bpm) are ranked by their single "
        "highest valid TCX sample. The first 25 are shown; ties are ordered by activity date."
    )
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


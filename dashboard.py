import sqlite3

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from app.config import DB_PATH, load_config
from app.database import initialize_database
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


def activity_period_filter(frame, key_prefix):
    """Render year/month controls and return matching activities."""
    dated = frame.dropna(subset=["start_time"]).copy()
    years = sorted(dated["start_time"].dt.year.unique(), reverse=True)
    if not years:
        return dated
    year_column, month_column = st.columns(2)
    selected_year = year_column.selectbox("Year", years, key=f"{key_prefix}_year")
    year_data = dated[dated["start_time"].dt.year == selected_year].copy()
    months = sorted(year_data["start_time"].dt.month.unique(), reverse=True)
    selected_month = month_column.selectbox(
        "Month", months, format_func=month_name, key=f"{key_prefix}_month"
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


st.title("🏃 Strava Dashboard — Version 2")
st.caption("Deterministic synchronization, historical trends, best efforts, heart-rate zones and data-quality checks.")

activities = load_activities()
if activities.empty:
    st.warning("No activity metadata is available. Run `python sync.py --local-only` first.")
    st.stop()

activities["start_time"] = pd.to_datetime(activities["start_time"], errors="coerce", utc=True)
activities["distance_km"] = activities["distance_m"] / 1000
imported = activities[activities["import_status"] == "imported"].copy()

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

tab_history, tab_activity, tab_compare, tab_imports = st.tabs([
    "Training history", "Activity analysis", "Compare", "Import health"
])

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
        choices = add_activity_labels(activity_period_filter(imported, "activity"))
        label_lookup = choices.set_index("activity_id")["label"].to_dict()
        selected_id = st.selectbox(
            "Activity", choices["activity_id"],
            format_func=lambda value: label_lookup[value],
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


# app.py
# A mini volcano data-viz app: tabs, filters, map, rankings, table & download.
import json
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Volcano Data Viz", layout="wide", page_icon="🌋")
st.title("🌋 Volcano dataset: count per country")

# ---------------------- DATA LOADING ----------------------
@st.cache_data
def load_geojson(path_or_bytes):
    if isinstance(path_or_bytes, (str, Path)):
        with open(path_or_bytes, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path_or_bytes.read().decode("utf-8"))

@st.cache_data
def load_csv(file) -> pd.DataFrame:
    return pd.read_csv(file)

# Default filenames (change if yours differ)
DEFAULT_GJ = "C:\\Users\\damla\\Desktop\\countries (2).geojson"
DEFAULT_CSV = "C:\\Users\\damla\\Desktop\\volcano_ds_pop (2).csv"

with st.sidebar:
    st.header("⚙️ Data")
    # allow both: path text or upload
    geojson_upload = st.file_uploader("GeoJSON (countries)", type=["json","geojson"])
    csv_upload     = st.file_uploader("Volcano CSV", type=["csv"])

    gj = load_geojson(geojson_upload) if geojson_upload else load_geojson(DEFAULT_GJ)
    df = load_csv(csv_upload) if csv_upload else load_csv(DEFAULT_CSV)

    st.caption("Tip: If names don't match, switch the GeoJSON property below.")

    # Figure out possible property keys on the geojson
    prop_keys = list(gj["features"][0]["properties"].keys())
    feature_prop = st.selectbox(
        "GeoJSON country property",
        options=prop_keys,
        index=prop_keys.index("ADMIN") if "ADMIN" in prop_keys else 0,
        help="This must match your CSV country naming"
    )
    FEATURE_KEY = f"properties.{feature_prop}"

# ---------------------- PREPARE DATA ----------------------
# Try to guess country column
possible_country_cols = ["Country","country","COUNTRY","name","Name"]
country_col = next((c for c in possible_country_cols if c in df.columns), None)
if country_col is None:
    st.error(f"Could not find a country column in CSV. Columns: {list(df.columns)}")
    st.stop()

# If you have a 'status' (Active/Dormant/Extinct), we’ll expose it as an optional filter
status_col = "status" if "status" in df.columns else None
status_vals = ["All"]
if status_col:
    status_vals += sorted(df[status_col].dropna().unique().tolist())

# Sidebar filters
with st.sidebar:
    st.header("🎛️ Controls")
    selected_status = st.selectbox("Status filter", status_vals, index=0)
    per_million = st.checkbox("Normalize per million population (if population column exists)", value=False)
    color_scale = st.selectbox("Color scale", ["Plasma","Viridis","Cividis","Turbo","YlOrRd","Blues"], index=0)
    map_style = st.selectbox("Map style", ["carto-positron","open-street-map","carto-darkmatter","stamen-terrain","stamen-toner"], index=0)
    thr_mode = st.checkbox("Threshold mode (Above/Below)", value=False)
    thr = st.slider("Threshold on normalized metric", 0.0, 0.999, 0.0, 0.001, disabled=not thr_mode)

# Filter by status if present
work_df = df.copy()
if status_col and selected_status != "All":
    work_df = work_df[work_df[status_col] == selected_status]

# Aggregate counts
country_count = (
    work_df.groupby(country_col, as_index=False)
           .size()
           .rename(columns={country_col: "Country", "size": "count"})
)

# Optional per-million if you have a 'population' column on the CSV
metric = "count"
if per_million and "population" in df.columns:
    pop_df = df[["Country","population"]].drop_duplicates()
    country_count = country_count.merge(pop_df, on="Country", how="left")
    country_count["per_million"] = country_count["count"] / (country_count["population"] / 1_000_000)
    metric = "per_million"

# Normalized metric for threshold
country_count["metric_norm"] = country_count[metric].fillna(0)
maxv = country_count["metric_norm"].max()
if maxv > 0:
    country_count["metric_norm"] = country_count["metric_norm"] / maxv
country_count["above_thr"] = country_count["metric_norm"] >= thr

# ---------------------- TABS ----------------------
tab_map, tab_rank, tab_table, tab_about = st.tabs(["🗺️ Map", "🏆 Rankings", "📄 Table & Download", "ℹ️ About"])

with tab_map:
    st.subheader("World choropleth")

    # Choropleth (continuous or threshold)
    if thr_mode:
        # two-color categorical (above/below)
        view = country_count.copy()
        view["class"] = np.where(view["above_thr"], "Above threshold", "Below threshold")
        fig = px.choropleth_mapbox(
            view,
            geojson=gj,
            locations="Country",
            featureidkey=FEATURE_KEY,
            color="class",
            hover_name="Country",
            mapbox_style=map_style,
            center={"lat": 20, "lon": 0},
            zoom=1,
            color_discrete_map={"Above threshold": "#66bb6a", "Below threshold": "#ef5350"},
        )
        fig.update_layout(legend_title_text="Threshold")
    else:
        fig = px.choropleth_mapbox(
            country_count,
            geojson=gj,
            locations="Country",
            featureidkey=FEATURE_KEY,
            color=metric,
            hover_name="Country",
            color_continuous_scale=color_scale,
            mapbox_style=map_style,
            center={"lat": 20, "lon": 0},
            zoom=1,
            labels={metric: metric.replace("_"," ").title()}
        )

    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

with tab_rank:
    st.subheader("Top countries")
    k = st.slider("Show top N", 5, 30, 15)
    topk = country_count.sort_values(metric, ascending=False).head(k)

    bar = px.bar(
        topk[::-1],  # horizontal bar, largest at bottom to top
        x=metric, y="Country",
        orientation="h",
        color=metric,
        color_continuous_scale=color_scale,
        labels={metric: metric.replace("_"," ").title()},
        height=500
    )
    bar.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(bar, use_container_width=True)

with tab_table:
    st.subheader("Data table")
    st.dataframe(country_count.sort_values(metric, ascending=False), use_container_width=True)

    csv = country_count.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download CSV", data=csv, file_name="volcano_country_counts.csv", mime="text/csv")

with tab_about:
    st.markdown(
        """
**How it works**

- Aggregates your records by **Country** → `count`.
- *(Optional)* If your CSV has a `population` column, enables **per million** normalization.
- Choose the **GeoJSON property** (e.g., `ADMIN`, `NAME`) that matches your country names.
- Switch to **Threshold mode** to highlight countries above/below a normalized cutoff.
- Explore **Top N** rankings or download the aggregated table.

**Hints**
- If a country doesn’t color, its name likely doesn’t match the GeoJSON property.
- Try changing the property in the sidebar (e.g., ADMIN ↔ NAME).
        """
    )

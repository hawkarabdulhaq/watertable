# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine

# Load the deep.csv well details for VMOEov_EOVx/VMOEov_EOVy lookup
@st.cache_data(show_spinner="Loading well locations…")
def load_well_metadata():
    url = "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/deep.csv"
    df_meta = pd.read_csv(url)
    # Use only Rendszam, VMOEov_EOVx, VMOEov_EOVy for merge
    return df_meta[["Rendszam", "VMOEov_EOVx", "VMOEov_EOVy"]].drop_duplicates("Rendszam")

def _load_table(engine: Engine, table_name: str) -> pd.DataFrame:
    query = f"SELECT * FROM `{table_name}`"
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn)

def monthly_page(engine: Engine) -> None:
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    table_choice = st.selectbox(
        "Select groundwater table",
        ["talajviz_table", "melyviz_table"]
    )

    try:
        df = _load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # For melyviz_table, load and merge metadata
    if table_choice == "melyviz_table":
        meta = load_well_metadata()
        df = df.merge(meta, on="Rendszam", how="left")
    else:
        df["VMOEov_EOVx"] = None
        df["VMOEov_EOVy"] = None

    col1 = (
        "vFkAllomas_TalajvizkutKutperemmag"
        if table_choice == "talajviz_table"
        else "vFaAllomas_RetegvizkutKutperemmag"
    )
    col2 = (
        "Talajvízállás" if "Talajvízállás" in df.columns
        else ("Talajvizallas" if "Talajvizallas" in df.columns else None)
    )
    if col2 is None or col1 not in df.columns:
        st.error("Required columns missing in the selected table.")
        return

    df["vizkutfenekmagasag"] = df[col1] + df[col2]

    if "Datum" not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Year"] = df["Datum"].dt.year
    df["Month"] = df["Datum"].dt.month

    rendszam_unique = sorted(df["Rendszam"].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select wells for time-series plot",
        rendszam_unique,
        default=rendszam_unique[:1] if rendszam_unique else []
    )

    df_valid = df.dropna(subset=["Rendszam", "Year", "Month", "vizkutfenekmagasag"])
    df_plot = (
        df_valid[df_valid["Rendszam"].isin(selected_rendszam)]
        if selected_rendszam else df_valid.copy()
    )

    st.subheader("Statistics to include")
    show_mean = st.checkbox("Mean", value=True, key="chk_mean")
    show_min = st.checkbox("Min", value=True, key="chk_min")
    show_max = st.checkbox("Max", value=True, key="chk_max")

    selected_stats = [
        stat for stat, flag in
        [("mean", show_mean), ("min", show_min), ("max", show_max)]
        if flag
    ]
    if not selected_stats:
        st.warning("Please select at least one statistic.")
        return

    # ---- Aggregate for table/plot ----
    group_cols = ["Rendszam", "Year", "Month"]
    if table_choice == "melyviz_table":
        group_cols += ["VMOEov_EOVx", "VMOEov_EOVy"]
    agg = (
        df_plot.groupby(group_cols)["vizkutfenekmagasag"]
        .agg(selected_stats)
        .reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"],
                                      month=agg["Month"], day=1))

    # Show main table (always put coords after Rendszam for melyviz_table)
    if table_choice == "melyviz_table":
        display_cols = ["Rendszam", "VMOEov_EOVx", "VMOEov_EOVy", "Year", "Month", "date"] + selected_stats
    else:
        display_cols = ["Rendszam", "Year", "Month", "date"] + selected_stats
    display_cols = [c for c in display_cols if c in agg.columns]  # avoid errors
    st.dataframe(agg.sort_values(["Rendszam", "date"])[display_cols], use_container_width=True)

    # ---- Plot ----
    st.subheader("Time-series plot")
    plt.figure(figsize=(12, 4))
    cmap = plt.get_cmap("tab10")

    for idx, rendszam in enumerate(sorted(agg["Rendszam"].unique())):
        g = agg[agg["Rendszam"] == rendszam]
        color = cmap(idx % 10)
        if "mean" in selected_stats and "mean" in g.columns:
            plt.plot(g["date"], g["mean"], label=f"{rendszam} Mean",
                     color=color, linestyle="-")
        if "max" in selected_stats and "max" in g.columns:
            plt.plot(g["date"], g["max"], label=f"{rendszam} Max",
                     color=color, linestyle="--")
        if "min" in selected_stats and "min" in g.columns:
            plt.plot(g["date"], g["min"], label=f"{rendszam} Min",
                     color=color, linestyle=":")
    plt.xlabel("Date")
    plt.ylabel("vizkutfenekmagasag")
    plt.title("Monthly statistics by well")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # ---- Wide table for Excel download ----
    agg_all = (
        df_valid.groupby(group_cols)["vizkutfenekmagasag"]
        .agg(selected_stats)
        .reset_index()
    )

    wide_index = ["Rendszam"]
    if table_choice == "melyviz_table":
        wide_index += ["VMOEov_EOVx", "VMOEov_EOVy"]
    wide_parts = []
    for stat in selected_stats:
        wide = agg_all.pivot(index=wide_index,
                             columns=["Year", "Month"],
                             values=stat)
        wide.columns = [f"{int(yr)}_{int(mn):02d}_{stat}" for yr, mn in wide.columns]
        wide_parts.append(wide)
    wide_full = pd.concat(wide_parts, axis=1).reset_index()

    # Order columns: Rendszam, EOVx, EOVy (if present), then month blocks
    ordered_cols = [col for col in wide_index]
    for base in sorted({c.rsplit("_", 1)[0] for c in wide_full.columns if c not in wide_index}):
        for stat in selected_stats:
            col = f"{base}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)
    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)

    # ---- Excel download ----
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        wide_full.to_excel(writer, index=False, sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buffer.getvalue(),
        file_name=f"monthly_{'_'.join(selected_stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

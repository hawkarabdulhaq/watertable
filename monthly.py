# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine  # only for type hinting

# ──────────────────────────────────────────────────────────────────────────────
# Helper – run a SELECT * safely
# ──────────────────────────────────────────────────────────────────────────────
def _load_table(engine: Engine, table_name: str) -> pd.DataFrame:
    """Return the whole table as a DataFrame (simple helper)."""
    query = f"SELECT * FROM `{table_name}`"
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn)


def monthly_page(engine: Engine) -> None:
    """Interactive Monthly stats page – engine is SQLAlchemy."""
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    # 1️⃣  Load data ----------------------------------------------------------------
    table_choice = st.selectbox(
        "Select groundwater table",
        ["talajviz_table", "melyviz_table"]
    )

    try:
        df = _load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # --- column mapping -----------------------------------------------------------
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

    # --- calculated column & date parts ------------------------------------------
    df["vizkutfenekmagasag"] = df[col1] + df[col2]

    if "Datum" not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Year"]  = df["Datum"].dt.year
    df["Month"] = df["Datum"].dt.month

    # 2️⃣  Well selector ------------------------------------------------------------
    rendszam_unique = sorted(df["Rendszam"].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select wells for time-series plot",
        rendszam_unique,
        default=rendszam_unique[:1] if rendszam_unique else []
    )

    df_valid = df.dropna(subset=["Rendszam", "Year", "Month", "vizkutfenekmagasag"])
    df_plot  = (
        df_valid[df_valid["Rendszam"].isin(selected_rendszam)]
        if selected_rendszam else df_valid.copy()
    )

    # 3️⃣  Stat check-boxes ---------------------------------------------------------
    st.subheader("Statistics to include")
    show_mean = st.checkbox("Mean", value=True, key="chk_mean")
    show_min  = st.checkbox("Min",  value=True, key="chk_min")
    show_max  = st.checkbox("Max",  value=True, key="chk_max")

    selected_stats = [
        stat for stat, flag in
        [("mean", show_mean), ("min", show_min), ("max", show_max)]
        if flag
    ]
    if not selected_stats:
        st.warning("Please select at least one statistic.")
        return

    # 4️⃣  Aggregate for plot/table -------------------------------------------------
    agg = (
        df_plot.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(selected_stats)
        .reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"],
                                      month=agg["Month"], day=1))
    st.dataframe(agg.sort_values(["Rendszam", "date"]),
                 use_container_width=True)

    # 5️⃣  Plot ---------------------------------------------------------------------
    st.subheader("Time-series plot")
    plt.figure(figsize=(12, 4))
    cmap = plt.get_cmap("tab10")

    for idx, rendszam in enumerate(sorted(agg["Rendszam"].unique())):
        g = agg[agg["Rendszam"] == rendszam]
        color = cmap(idx % 10)
        if "mean" in selected_stats:
            plt.plot(g["date"], g["mean"], label=f"{rendszam} Mean",
                     color=color, linestyle="-")
        if "max" in selected_stats:
            plt.plot(g["date"], g["max"],  label=f"{rendszam} Max",
                     color=color, linestyle="--")
        if "min" in selected_stats:
            plt.plot(g["date"], g["min"],  label=f"{rendszam} Min",
                     color=color, linestyle=":")
    plt.xlabel("Date")
    plt.ylabel("vizkutfenekmagasag")
    plt.title("Monthly statistics by well")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # 6️⃣  Build “wide” table for download -----------------------------------------
    agg_all = (
        df_valid.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(selected_stats)
        .reset_index()
    )

    wide_parts = []
    for stat in selected_stats:
        wide = agg_all.pivot(index="Rendszam",
                             columns=["Year", "Month"],
                             values=stat)
        wide.columns = [f"{int(yr)}_{int(mn):02d}_{stat}"
                        for yr, mn in wide.columns]
        wide_parts.append(wide)

    wide_full = pd.concat(wide_parts, axis=1).reset_index()

    # order columns
    ordered_cols = ["Rendszam"]
    for base in sorted({c.rsplit("_", 1)[0] for c in wide_full.columns
                        if c != "Rendszam"}):
        for stat in selected_stats:
            col = f"{base}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)
    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)

    # 7️⃣  Excel download -----------------------------------------------------------
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        wide_full.to_excel(writer, index=False, sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buffer.getvalue(),
        file_name=f"monthly_{'_'.join(selected_stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

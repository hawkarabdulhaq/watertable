# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine  # type hint only

# ──────────────────────────────────────────────────────────────────────────────
# Configuration – metadata columns we want from deep.csv
# ──────────────────────────────────────────────────────────────────────────────
META_COLS = [
    "Rendszam",
    "VMOEov_EOVx",
    "VMOEov_EOVy",
    "Torzsszam",
    "vmoNev",
    "VMOEov_Torzsszam",
    "vFaAllomas_AdatgazdaNev",
    "vFaAllomas_RetegvizkutTelepulesNev",
    "vFaAllomas_KapcsSzkmNev",
    "vFaAllomas_AllomasTVA",
    "vFaAllomas_RetegvizkutJellegkodNev",
    "vFaAllomas_RetegvizkutKatSzam",
    "vFaAllomas_FaAllAdatforgTipNev",
    "vFaAllomas_RetegvizkutTipuskodNev",
    "vFaAllomas_RetegvizkutJelzoszam",
    "vFaAllomas_RetegvizkutTerepmag",
    "vFaAllomas_RetegvizkutKutperemmag",
    "vFaAllomas_RetegvizkutKutmelyseg",
    "vFaAllomas_FaAllVKImon",
    "vFaAllomas_FaAllUzemelesNev",
]

COORDS_CSV_URL = (
    "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/deep.csv"
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _load_table(engine: Engine, table_name: str) -> pd.DataFrame:
    """Fetch a whole table via SQLAlchemy (so pandas is happy)."""
    query = f"SELECT * FROM `{table_name}`"
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn)


@st.cache_data(show_spinner=False)
def _load_metadata() -> pd.DataFrame:
    """Read deep.csv once and guarantee all META_COLS are present."""
    df = pd.read_csv(
        COORDS_CSV_URL,
        usecols=lambda c: c in META_COLS,   # pull only what we need
        encoding="utf-8"
    )
    # Ensure every requested column exists
    for col in META_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    return df.drop_duplicates("Rendszam")


# ──────────────────────────────────────────────────────────────────────────────
# Main Streamlit page
# ──────────────────────────────────────────────────────────────────────────────
def monthly_page(engine: Engine) -> None:
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    # 1️⃣  Choose table & load ------------------------------------------------------
    table_choice = st.selectbox(
        "Select groundwater table",
        ["talajviz_table", "melyviz_table"],
    )

    try:
        df = _load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # 1a️⃣  If melyviz_table → merge metadata -------------------------------------
    if table_choice == "melyviz_table":
        meta = _load_metadata()
        df = df.merge(meta, on="Rendszam", how="left")

    # 2️⃣  Column mapping -----------------------------------------------------------
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
        st.error("Required columns are missing in the selected table.")
        return

    # 3️⃣  Derived & time columns ---------------------------------------------------
    df["vizkutfenekmagasag"] = df[col1] + df[col2]
    if "Datum" not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Year"]  = df["Datum"].dt.year
    df["Month"] = df["Datum"].dt.month

    # 4️⃣  Well selector ------------------------------------------------------------
    rendszam_unique = sorted(df["Rendszam"].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select wells for time-series plot",
        rendszam_unique,
        default=rendszam_unique[:1] if rendszam_unique else [],
    )

    df_valid = df.dropna(subset=["Rendszam", "Year", "Month", "vizkutfenekmagasag"])
    df_plot  = (
        df_valid[df_valid["Rendszam"].isin(selected_rendszam)]
        if selected_rendszam else df_valid.copy()
    )

    # 5️⃣  Stat check-boxes ---------------------------------------------------------
    st.subheader("Statistics to include")
    show_mean = st.checkbox("Mean", value=True)
    show_min  = st.checkbox("Min",  value=True)
    show_max  = st.checkbox("Max",  value=True)

    selected_stats = [
        stat for stat, flag in [("mean", show_mean), ("min", show_min), ("max", show_max)] if flag
    ]
    if not selected_stats:
        st.warning("Please select at least one statistic.")
        return

    # 6️⃣  Aggregate for preview & plot --------------------------------------------
    agg = (
        df_plot.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(selected_stats)
        .reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"], month=agg["Month"], day=1))

    if table_choice == "melyviz_table":
        agg = agg.merge(meta[META_COLS], on="Rendszam", how="left")

    st.dataframe(agg.sort_values(["Rendszam", "date"]), use_container_width=True)

    # 7️⃣  Plot ---------------------------------------------------------------------
    st.subheader("Time-series plot")
    plt.figure(figsize=(12, 4))
    cmap = plt.get_cmap("tab10")

    for idx, rendszam in enumerate(sorted(agg["Rendszam"].unique())):
        g = agg[agg["Rendszam"] == rendszam]
        color = cmap(idx % 10)
        if "mean" in selected_stats:
            plt.plot(g["date"], g["mean"], label=f"{rendszam} Mean", color=color, linestyle="-")
        if "max" in selected_stats:
            plt.plot(g["date"], g["max"],  label=f"{rendszam} Max",  color=color, linestyle="--")
        if "min" in selected_stats:
            plt.plot(g["date"], g["min"],  label=f"{rendszam} Min",  color=color, linestyle=":")
    plt.xlabel("Date")
    plt.ylabel("vizkutfenekmagasag")
    plt.title("Monthly statistics by well")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # 8️⃣  Build “wide” table for download -----------------------------------------
    agg_all = (
        df_valid.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(selected_stats)
        .reset_index()
    )

    wide_parts = []
    for stat in selected_stats:
        wide = agg_all.pivot(index="Rendszam", columns=["Year", "Month"], values=stat)
        wide.columns = [f"{int(yr)}_{int(mn):02d}_{stat}" for yr, mn in wide.columns]
        wide_parts.append(wide)

    wide_full = pd.concat(wide_parts, axis=1).reset_index()

    if table_choice == "melyviz_table":
        wide_full = meta[META_COLS].merge(wide_full, on="Rendszam", how="right")

    # --- order columns: metadata first, then stats blocks ------------------------
    ordered_cols = [c for c in META_COLS if c in wide_full.columns]

    # stats blocks (same logic as before)
    for base in sorted({c.rsplit("_", 1)[0] for c in wide_full.columns
                        if c not in ordered_cols}):
        for stat in selected_stats:
            col = f"{base}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)

    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)

    # 9️⃣  Excel download -----------------------------------------------------------
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        wide_full.to_excel(writer, index=False, sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buffer.getvalue(),
        file_name=f"monthly_{'_'.join(selected_stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

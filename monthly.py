# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine  # type-hint only

# ──────────────────────────────────────────────────────────────────────────────
# 1.  CSV with well metadata
# ──────────────────────────────────────────────────────────────────────────────
META_CSV_URL = (
    "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/deep.csv"
)

# Columns to bring in from deep.csv – first is Rendszam (key)
META_COLS = [
    "Rendszam",
    "VMOEov_EOVx",
    "VMOEov_EOVy",
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

@st.cache_data(show_spinner=False)
def _load_meta() -> pd.DataFrame:
    """Read deep.csv once per session, keep only META_COLS, return deduplicated."""
    df = pd.read_csv(META_CSV_URL, usecols=lambda c: c in META_COLS)
    return df.drop_duplicates(subset="Rendszam")

# ──────────────────────────────────────────────────────────────────────────────
# 2.  SQL helper
# ──────────────────────────────────────────────────────────────────────────────
def _load_table(engine: Engine, table: str) -> pd.DataFrame:
    """SELECT * FROM table via SQLAlchemy (no pandas warning)."""
    sql = f"SELECT * FROM `{table}`"
    with engine.connect() as conn:
        return pd.read_sql_query(sql, conn)

# ──────────────────────────────────────────────────────────────────────────────
# 3.  Main Streamlit page
# ──────────────────────────────────────────────────────────────────────────────
def monthly_page(engine: Engine) -> None:
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    # ── 3.1 choose table & load ───────────────────────────────────────────────
    table_choice = st.selectbox(
        "Select groundwater table", ["talajviz_table", "melyviz_table"]
    )
    try:
        df = _load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # ── 3.2 merge metadata if melyviz_table ──────────────────────────────────
    if table_choice == "melyviz_table":
        meta = _load_meta()

        # avoid duplicate cols that already exist in the SQL table
        dupes = [c for c in META_COLS if c != "Rendszam" and c in df.columns]
        meta = meta.drop(columns=dupes)

        df = df.merge(meta, on="Rendszam", how="left")
    else:
        meta = None  # talajviz_table

    # ── 3.3 required columns / derived field ─────────────────────────────────
    col1 = (
        "vFkAllomas_TalajvizkutKutperemmag"
        if table_choice == "talajviz_table"
        else "vFaAllomas_RetegvizkutKutperemmag"
    )
    col2 = (
        "Talajvízállás"
        if "Talajvízállás" in df.columns
        else ("Talajvizallas" if "Talajvizallas" in df.columns else None)
    )
    if col2 is None or col1 not in df.columns:
        st.error("Required columns are missing in the selected table.")
        return

    df["vizkutfenekmagasag"] = df[col1] + df[col2]
    if "Datum" not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Year"]  = df["Datum"].dt.year
    df["Month"] = df["Datum"].dt.month

    # ── 3.4 well selector ────────────────────────────────────────────────────
    wells = sorted(df["Rendszam"].dropna().unique())
    selected = st.multiselect(
        "Select wells for time-series plot",
        wells,
        default=wells[:1] if wells else [],
    )

    df_valid = df.dropna(subset=["Rendszam", "Year", "Month", "vizkutfenekmagasag"])
    df_plot = (
        df_valid[df_valid["Rendszam"].isin(selected)] if selected else df_valid
    )

    # ── 3.5 stats check-boxes ────────────────────────────────────────────────
    st.subheader("Statistics to include")
    opts = {
        "mean": st.checkbox("Mean", value=True, key="chk_mean"),
        "min":  st.checkbox("Min",  value=True, key="chk_min"),
        "max":  st.checkbox("Max",  value=True, key="chk_max"),
    }
    stats = [k for k, v in opts.items() if v]
    if not stats:
        st.warning("Please select at least one statistic.")
        return

    # ── 3.6 aggregate for preview / plot ─────────────────────────────────────
    agg = (
        df_plot.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(stats)
        .reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"], month=agg["Month"], day=1))
    if meta is not None:
        agg = agg.merge(meta, on="Rendszam", how="left")

    st.dataframe(agg.sort_values(["Rendszam", "date"]), use_container_width=True)

    # ── 3.7 plot ─────────────────────────────────────────────────────────────
    st.subheader("Time-series plot")
    plt.figure(figsize=(12, 4))
    cmap = plt.get_cmap("tab10")
    for idx, w in enumerate(sorted(agg["Rendszam"].unique())):
        g, color = agg[agg["Rendszam"] == w], cmap(idx % 10)
        if "mean" in stats:
            plt.plot(g["date"], g["mean"], label=f"{w} Mean", color=color, ls="-")
        if "max" in stats:
            plt.plot(g["date"], g["max"],  label=f"{w} Max",  color=color, ls="--")
        if "min" in stats:
            plt.plot(g["date"], g["min"],  label=f"{w} Min",  color=color, ls=":")
    plt.xlabel("Date"); plt.ylabel("vizkutfenekmagasag")
    plt.title("Monthly statistics by well")
    plt.legend(); plt.tight_layout()
    st.pyplot(plt.gcf()); plt.clf()

    # ── 3.8 build “wide” download table ──────────────────────────────────────
    agg_all = (
        df_valid.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(stats)
        .reset_index()
    )

    parts = []
    for s in stats:
        w = agg_all.pivot(index="Rendszam", columns=["Year", "Month"], values=s)
        w.columns = [f"{int(y)}_{int(m):02d}_{s}" for y, m in w.columns]
        parts.append(w)
    wide = pd.concat(parts, axis=1).reset_index()

    if meta is not None:
        wide = meta.merge(wide, on="Rendszam", how="right")

    # column order: Rendszam, meta cols, then stats blocks
    ordered = ["Rendszam"]
    if meta is not None:
        ordered += [c for c in META_COLS[1:] if c in wide.columns]
    for base in sorted({c.rsplit("_", 1)[0] for c in wide.columns
                        if c not in ordered}):
        for s in stats:
            col = f"{base}_{s}"
            if col in wide.columns:
                ordered.append(col)
    wide = wide[ordered]
    st.dataframe(wide.head(), use_container_width=True)

    # ── 3.9 Excel download ───────────────────────────────────────────────────
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as xls:
        wide.to_excel(xls, index=False, sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buff.getvalue(),
        file_name=f"monthly_{'_'.join(stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

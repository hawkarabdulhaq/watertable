# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine  # type-hint only

# ──────────────────────────────────────────────────────────────────────────────
# 1.  CSV with well metadata  (single source for both tables)
# ──────────────────────────────────────────────────────────────────────────────
META_CSV_URL = (
    "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/deep.csv"
)

# --- metadata column sets -------------------------------------------------------
META_COLS_MELY = [                 # used for melyviz_table  (deep)
    "Rendszam",
    "VMOEov_EOVx", "VMOEov_EOVy",
    "vmoNev", "VMOEov_Torzsszam",
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

META_COLS_TALAJ = [                # used for talajviz_table (shallow)
    "Rendszam",
    "vmoTipusKod", "Torzsszam", "vmoNev",
    "VMOEov_EOVx", "VMOEov_EOVy",
    "vFkAllomas_AdatgazdaNev",
    "vFkAllomas_Nevr", "vFkAllomas_Leiras",
    "vFkAllomas_TalajvizkutTelepulesNev",
    "vFkAllomas_KapcsSzkmNev",
    "vFkAllomas_AllomasTavmBemenetNev",
    "vFkAllomas_AllomasTVA",
    "vFkAllomas_TalajvizkutKatSzam",
    "vFkAllomas_TalajvizkutJelzoszam",
    "vFkAllomas_FkAllAdatforgTipNev",
    "vFkAllomas_TalajvizkutVizminVanE",
    "vFkAllomas_TalajvizkutTipuskodNev",
    "vFkAllomas_TalajvizkutTerepmag",
    "vFkAllomas_TalajvizkutKutperemmag",
    "vFkAllomas_TalajvizkutKutmelyseg",
    "vFkAllomas_TalajvizjutGyorsadat",
    "vFkAllomas_FkAllVKImon",
    "vFkAllomas_FkAllUzemelesNev",
]

META_COLS_BY_TABLE = {
    "melyviz_table":  META_COLS_MELY,
    "talajviz_table": META_COLS_TALAJ,
}
# union of every metadata field we might need
ALL_META_COLS = sorted(
    {c for cols in META_COLS_BY_TABLE.values() for c in cols}
)

@st.cache_data(show_spinner=False)
def _load_meta() -> pd.DataFrame:
    """Load deep.csv once per session, keep only columns we care about."""
    df = pd.read_csv(META_CSV_URL, usecols=lambda c: c in ALL_META_COLS)
    return df.drop_duplicates(subset="Rendszam")

# ──────────────────────────────────────────────────────────────────────────────
# 2.  SQL helper
# ──────────────────────────────────────────────────────────────────────────────
def _load_table(engine: Engine, table: str) -> pd.DataFrame:
    sql = f"SELECT * FROM `{table}`"
    with engine.connect() as conn:
        return pd.read_sql_query(sql, conn)

# ──────────────────────────────────────────────────────────────────────────────
# 3.  Main Streamlit page
# ──────────────────────────────────────────────────────────────────────────────
def monthly_page(engine: Engine) -> None:
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    # ── 3.1 choose table & load ──────────────────────────────────────────────
    table_choice = st.selectbox(
        "Select groundwater table", ["talajviz_table", "melyviz_table"]
    )
    try:
        df = _load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # ── 3.2 bring in metadata for the chosen table ───────────────────────────
    meta_cols_needed = META_COLS_BY_TABLE[table_choice]
    meta_full        = _load_meta()

    # keep only requested columns that are present in the CSV
    meta = meta_full.loc[:, [c for c in meta_cols_needed if c in meta_full.columns]]

    # drop metadata columns that already exist in SQL table to avoid *_x/_y
    dupes = [c for c in meta.columns if c in df.columns and c != "Rendszam"]
    meta = meta.drop(columns=dupes)
    df   = df.merge(meta, on="Rendszam", how="left")

    # ── 3.3 mapping of water-level & peremmag columns ────────────────────────
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

    # ── 3.4 derived & time columns ───────────────────────────────────────────
    df["vizkutfenekmagasag"] = df[col1] + df[col2]
    if "Datum" not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Year"]  = df["Datum"].dt.year
    df["Month"] = df["Datum"].dt.month

    # ── 3.5 well selector ────────────────────────────────────────────────────
    wells = sorted(df["Rendszam"].dropna().unique())
    selected = st.multiselect(
        "Select wells for time-series plot",
        wells,
        default=wells[:1] if wells else [],
    )
    df_valid = df.dropna(subset=["Rendszam", "Year", "Month", "vizkutfenekmagasag"])
    df_plot  = df_valid[df_valid["Rendszam"].isin(selected)] if selected else df_valid

    # ── 3.6 stats check-boxes ────────────────────────────────────────────────
    st.subheader("Statistics to include")
    opts  = {"mean": st.checkbox("Mean", True),
             "min":  st.checkbox("Min",  True),
             "max":  st.checkbox("Max",  True)}
    stats = [k for k, v in opts.items() if v]
    if not stats:
        st.warning("Please select at least one statistic."); return

    # ── 3.7 aggregate for preview / plot ─────────────────────────────────────
    agg = (
        df_plot.groupby(["Rendszam", "Year", "Month"])["vizkutfenekmagasag"]
        .agg(stats)
        .reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"], month=agg["Month"], day=1))
    agg = agg.merge(meta, on="Rendszam", how="left")   # add meta to preview
    st.dataframe(agg.sort_values(["Rendszam", "date"]), use_container_width=True)

    # ── 3.8 plot ─────────────────────────────────────────────────────────────
    st.subheader("Time-series plot")
    plt.figure(figsize=(12, 4)); cmap = plt.get_cmap("tab10")
    for idx, w in enumerate(sorted(agg["Rendszam"].unique())):
        g, color = agg[agg["Rendszam"] == w], cmap(idx % 10)
        if "mean" in stats: plt.plot(g["date"], g["mean"], label=f"{w} Mean", color=color, ls="-")
        if "max"  in stats: plt.plot(g["date"], g["max"],  label=f"{w} Max",  color=color, ls="--")
        if "min"  in stats: plt.plot(g["date"], g["min"],  label=f"{w} Min",  color=color, ls=":")
    plt.xlabel("Date"); plt.ylabel("vizkutfenekmagasag")
    plt.title("Monthly statistics by well")
    plt.legend(); plt.tight_layout(); st.pyplot(plt.gcf()); plt.clf()

    # ── 3.9 build “wide” table for download ──────────────────────────────────
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
    wide = meta.merge(wide, on="Rendszam", how="right")  # prepend meta

    # column order: Rendszam + meta (in the order specified) + stats blocks
    ordered = ["Rendszam"] + [c for c in meta_cols_needed[1:] if c in wide.columns]
    for base in sorted({c.rsplit("_", 1)[0] for c in wide.columns if c not in ordered}):
        for s in stats:
            col = f"{base}_{s}"
            if col in wide.columns:
                ordered.append(col)
    wide = wide[ordered]
    st.dataframe(wide.head(), use_container_width=True)

    # ── 3.10 Excel download ──────────────────────────────────────────────────
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as xls:
        wide.to_excel(xls, index=False, sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buff.getvalue(),
        file_name=f"monthly_{'_'.join(stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

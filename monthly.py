# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine

# ──────────────────────────────────────────────────────────────────────────────
# 1.  Single CSV that holds metadata for *both* well types
# ──────────────────────────────────────────────────────────────────────────────
META_CSV_URL = (
    "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/deep.csv"
)

# Deep-well (melyvíz) metadata fields we already used
META_MELY = [
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

# Shallow-well (talajvíz) metadata fields requested now
META_TALAJ = [
    "Rendszam",
    "vmoTipusKod", "Torzsszam", "vmoNev",
    "VMOEov_EOVx", "VMOEov_EOVy",
    "vFkAllomas_AdatgazdaNev",
    "vFkAllomas_Nevr",
    "vFkAllomas_Leiras",
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

# One helper to read only the union of needed columns
@st.cache_data(show_spinner=False)
def _load_meta() -> pd.DataFrame:
    need = set(META_MELY).union(META_TALAJ)
    df = pd.read_csv(META_CSV_URL, usecols=lambda c: c in need)
    return df.drop_duplicates(subset="Rendszam")

# ──────────────────────────────────────────────────────────────────────────────
# 2.  SQL helper
# ──────────────────────────────────────────────────────────────────────────────
def _load_table(engine: Engine, table: str) -> pd.DataFrame:
    sql = f"SELECT * FROM `{table}`"
    with engine.connect() as conn:
        return pd.read_sql_query(sql, conn)

# ──────────────────────────────────────────────────────────────────────────────
# 3.  Streamlit page
# ──────────────────────────────────────────────────────────────────────────────
def monthly_page(engine: Engine) -> None:
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    # 3.1 ─ Choose table
    table_choice = st.selectbox(
        "Select groundwater table", ["talajviz_table", "melyviz_table"]
    )

    # 3.2 ─ Load SQL rows
    try:
        df = _load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # 3.3 ─ Merge the appropriate metadata set
    meta = _load_meta()
    if table_choice == "melyviz_table":
        wanted = [c for c in META_MELY if c in meta.columns]
    else:  # talaj
        wanted = [c for c in META_TALAJ if c in meta.columns]

    meta_sub = meta[wanted]

    # drop meta cols that already exist in SQL table to avoid _x/_y
    dupes = [c for c in meta_sub.columns if c != "Rendszam" and c in df.columns]
    meta_sub = meta_sub.drop(columns=dupes, errors="ignore")

    df = df.merge(meta_sub, on="Rendszam", how="left")

    # 3.4 ─ Core columns for computation
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
        st.error("No 'Datum' column found."); return
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Year"] = df["Datum"].dt.year
    df["Month"] = df["Datum"].dt.month

    # 3.5 ─ Well selector
    wells = sorted(df["Rendszam"].dropna().unique())
    chosen = st.multiselect(
        "Select wells for time-series plot",
        wells,
        default=wells[:1] if wells else [],
    )
    df_valid = df.dropna(subset=["Rendszam","Year","Month","vizkutfenekmagasag"])
    df_plot  = df_valid[df_valid["Rendszam"].isin(chosen)] if chosen else df_valid

    # 3.6 ─ Stat checkboxes
    st.subheader("Statistics to include")
    opts = {
        "mean": st.checkbox("Mean", True),
        "min":  st.checkbox("Min",  True),
        "max":  st.checkbox("Max",  True),
    }
    stats = [k for k,v in opts.items() if v]
    if not stats:
        st.warning("Select at least one statistic."); return

    # 3.7 ─ Aggregate for preview & plot
    agg = (
        df_plot.groupby(["Rendszam","Year","Month"])["vizkutfenekmagasag"]
        .agg(stats).reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"], month=agg["Month"], day=1))
    agg = agg.merge(meta_sub, on="Rendszam", how="left")
    st.dataframe(agg.sort_values(["Rendszam","date"]), use_container_width=True)

    # 3.8 ─ Plot
    st.subheader("Time-series plot")
    plt.figure(figsize=(12,4)); cmap = plt.get_cmap("tab10")
    for i,w in enumerate(sorted(agg["Rendszam"].unique())):
        g, c = agg[agg["Rendszam"]==w], cmap(i%10)
        if "mean" in stats: plt.plot(g["date"],g["mean"],label=f"{w} Mean",c=c,ls="-")
        if "max"  in stats: plt.plot(g["date"],g["max"], label=f"{w} Max", c=c,ls="--")
        if "min"  in stats: plt.plot(g["date"],g["min"], label=f"{w} Min", c=c,ls=":")
    plt.xlabel("Date"); plt.ylabel("vizkutfenekmagasag"); plt.title("Monthly stats")
    plt.legend(); plt.tight_layout(); st.pyplot(plt.gcf()); plt.clf()

    # 3.9 ─ Build wide download table
    agg_all = (
        df_valid.groupby(["Rendszam","Year","Month"])["vizkutfenekmagasag"]
        .agg(stats).reset_index()
    )
    parts = []
    for s in stats:
        w = agg_all.pivot(index="Rendszam", columns=["Year","Month"], values=s)
        w.columns = [f"{int(y)}_{int(m):02d}_{s}" for y,m in w.columns]
        parts.append(w)
    wide = pd.concat(parts, axis=1).reset_index()
    wide = meta_sub.merge(wide, on="Rendszam", how="right")

    # clear column order: Rendszam, meta, then stats blocks
    ordered = ["Rendszam"] + [c for c in meta_sub.columns if c!="Rendszam"]
    for base in sorted({c.rsplit("_",1)[0] for c in wide.columns if c not in ordered}):
        for s in stats:
            col = f"{base}_{s}"
            if col in wide.columns:
                ordered.append(col)
    wide = wide[ordered]
    st.dataframe(wide.head(), use_container_width=True)

    # 3.10 ─ Excel download
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
        wide.to_excel(xl,index=False,sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buf.getvalue(),
        file_name=f"monthly_{'_'.join(stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

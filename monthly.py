# monthly.py
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.engine import Engine  # type-hint only

# ───────────────────────────────
# 1.  CSV sources & wanted fields
# ───────────────────────────────
SHALLOW_CSV_URL = (
    "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/shallow.csv"
)
SHALLOW_COLS = [
    "vmoTipusKod","Torzsszam","vmoNev","Rendszam","VMOEov_EOVx","VMOEov_EOVy",
    "vFkAllomas_AdatgazdaNev","vFkAllomas_Nevr","vFkAllomas_Leiras",
    "vFkAllomas_TalajvizkutTelepulesNev","vFkAllomas_KapcsSzkmNev",
    "vFkAllomas_AllomasTavmBemenetNev","vFkAllomas_AllomasTVA",
    "vFkAllomas_TalajvizkutKatSzam","vFkAllomas_TalajvizkutJelzoszam",
    "vFkAllomas_FkAllAdatforgTipNev","vFkAllomas_TalajvizkutVizminVanE",
    "vFkAllomas_TalajvizkutTipuskodNev","vFkAllomas_TalajvizkutTerepmag",
    "vFkAllomas_TalajvizkutKutperemmag","vFkAllomas_TalajvizkutKutmelyseg",
    "vFkAllomas_TalajvizjutGyorsadat","vFkAllomas_FkAllVKImon",
    "vFkAllomas_FkAllUzemelesNev",
]

DEEP_CSV_URL = (
    "https://raw.githubusercontent.com/hawkarabdulhaq/watertable/main/input/deep.csv"
)
DEEP_COLS = [
    "Rendszam","VMOEov_EOVx","VMOEov_EOVy","vmoNev","VMOEov_Torzsszam",
    "vFaAllomas_AdatgazdaNev","vFaAllomas_RetegvizkutTelepulesNev",
    "vFaAllomas_KapcsSzkmNev","vFaAllomas_AllomasTVA",
    "vFaAllomas_RetegvizkutJellegkodNev","vFaAllomas_RetegvizkutKatSzam",
    "vFaAllomas_FaAllAdatforgTipNev","vFaAllomas_RetegvizkutTipuskodNev",
    "vFaAllomas_RetegvizkutJelzoszam","vFaAllomas_RetegvizkutTerepmag",
    "vFaAllomas_RetegvizkutKutperemmag","vFaAllomas_RetegvizkutKutmelyseg",
    "vFaAllomas_FaAllVKImon","vFaAllomas_FaAllUzemelesNev",
]

@st.cache_data(show_spinner=False)
def load_shallow_meta() -> pd.DataFrame:
    return (
        pd.read_csv(SHALLOW_CSV_URL, usecols=lambda c: c in SHALLOW_COLS)
        .drop_duplicates(subset="Rendszam")
    )

@st.cache_data(show_spinner=False)
def load_deep_meta() -> pd.DataFrame:
    return (
        pd.read_csv(DEEP_CSV_URL, usecols=lambda c: c in DEEP_COLS)
        .drop_duplicates(subset="Rendszam")
    )

# ───────────────────────────────
# 2.  SQL helper
# ───────────────────────────────
def load_table(engine: Engine, name: str) -> pd.DataFrame:
    sql = f"SELECT * FROM `{name}`"
    with engine.connect() as conn:
        return pd.read_sql_query(sql, conn)

# ───────────────────────────────
# 3.  Main Streamlit page
# ───────────────────────────────
def monthly_page(engine: Engine) -> None:
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")
    debug = st.sidebar.checkbox("🔧 Debug mode")

    # 3-A  choose table & load SQL data
    table_choice = st.selectbox(
        "Select groundwater table", ["talajviz_table", "melyviz_table"]
    )
    try:
        df_sql = load_table(engine, table_choice)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return
    if debug:
        st.sidebar.write(f"SQL table shape: {df_sql.shape}")

    # 3-B  pick metadata and merge (CSV values override SQL)
    if table_choice == "talajviz_table":
        meta_cols, meta = SHALLOW_COLS, load_shallow_meta()
    else:
        meta_cols, meta = DEEP_COLS, load_deep_meta()

    if debug:
        st.sidebar.write(f"Metadata shape: {meta.shape}")

    # Merge with suffixes so *CSV* keeps original names, SQL duplicates get *_sql
    df = df_sql.merge(meta, on="Rendszam", how="left", suffixes=("_sql", ""))

    # After merge, drop the *_sql columns (i.e. keep CSV values)
    drop_cols = [c for c in df.columns if c.endswith("_sql")]
    df.drop(columns=drop_cols, inplace=True)
    if debug and drop_cols:
        st.sidebar.write(f"Dropped SQL duplicates: {drop_cols}")

    # Debug counts for coordinates
    if debug:
        non_null = df["VMOEov_EOVx"].notna().sum()
        st.sidebar.write(
            f"Coordinates present after merge: {non_null}/{len(df)}"
        )
        with st.expander("Coordinates preview"):
            st.dataframe(df[["Rendszam","VMOEov_EOVx","VMOEov_EOVy"]].head())

    # 3-C  required columns & derived field
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

    # 3-D  well selector
    wells = sorted(df["Rendszam"].dropna().unique())
    selected = st.multiselect(
        "Select wells for time-series plot",
        wells,
        default=wells[:1] if wells else [],
    )

    df_valid = df.dropna(subset=["Rendszam","Year","Month","vizkutfenekmagasag"])
    df_plot  = df_valid[df_valid["Rendszam"].isin(selected)] if selected else df_valid

    # 3-E  stats check-boxes
    st.subheader("Statistics to include")
    stats = [s for s, ok in [
        ("mean", st.checkbox("Mean", True)),
        ("min",  st.checkbox("Min",  True)),
        ("max",  st.checkbox("Max",  True)),
    ] if ok]
    if not stats:
        st.warning("Please select at least one statistic.")
        return

    # 3-F  aggregate for preview & plot
    agg = (
        df_plot.groupby(["Rendszam","Year","Month"])["vizkutfenekmagasag"]
        .agg(stats).reset_index()
    )
    agg["date"] = pd.to_datetime(dict(year=agg["Year"], month=agg["Month"], day=1))
    agg = agg.merge(meta, on="Rendszam", how="left")

    st.dataframe(agg.sort_values(["Rendszam","date"]), use_container_width=True)

    # 3-G  time-series plot
    st.subheader("Time-series plot")
    plt.figure(figsize=(12,4))
    cmap = plt.get_cmap("tab10")
    for idx, w in enumerate(sorted(agg["Rendszam"].unique())):
        g, color = agg[agg["Rendszam"]==w], cmap(idx%10)
        if "mean" in stats: plt.plot(g["date"],g["mean"],label=f"{w} Mean",color=color,ls="-")
        if "max"  in stats: plt.plot(g["date"],g["max"], label=f"{w} Max", color=color,ls="--")
        if "min"  in stats: plt.plot(g["date"],g["min"], label=f"{w} Min", color=color,ls=":")
    plt.xlabel("Date"); plt.ylabel("vizkutfenekmagasag")
    plt.legend(); plt.tight_layout()
    st.pyplot(plt.gcf()); plt.clf()

    # 3-H  build wide table
    agg_all = (
        df_valid.groupby(["Rendszam","Year","Month"])["vizkutfenekmagasag"]
        .agg(stats).reset_index()
    )
    parts=[]
    for s in stats:
        w = agg_all.pivot(index="Rendszam", columns=["Year","Month"], values=s)
        w.columns=[f"{int(y)}_{int(m):02d}_{s}" for y,m in w.columns]
        parts.append(w)
    wide = pd.concat(parts, axis=1).reset_index()
    wide = meta.merge(wide, on="Rendszam", how="right")

    # order columns: Rendszam, all meta fields in their original order, then stats
    ordered = ["Rendszam"] + [c for c in meta_cols if c != "Rendszam"]
    for base in sorted({c.rsplit("_",1)[0] for c in wide.columns if c not in ordered}):
        for s in stats:
            col = f"{base}_{s}"
            if col in wide.columns:
                ordered.append(col)
    wide = wide[ordered]
    st.dataframe(wide.head(), use_container_width=True)

    # 3-I  download Excel
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as xls:
        wide.to_excel(xls, index=False, sheet_name="MonthlyWide")
    st.download_button(
        "Download selected statistics (Excel)",
        buff.getvalue(),
        file_name=f"monthly_{'_'.join(stats)}_{table_choice}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

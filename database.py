# database.py
import streamlit as st
import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine   # type-hint only

# ──────────────────────────────────────────────────────────────────────────────
# Utility: clean numeric columns
# ──────────────────────────────────────────────────────────────────────────────
def clean_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    num_cols = [
        'nyug_vizszint', 'uz_vizszint', 'vizhozam', 'havi_kiterm_viz', 'havi_uzemora', 'Vizmerleg',
        'EOVX', 'EOVY', 'VMOEov_EOVx', 'VMOEov_EOVy', 'TSZF', 'TALP',
        'SZURO_F', 'SZURO_A', 'SZURO_DB', 'SZURO_H',
        'LETESITES', 'NYUGALMI', 'UZEMI', 'HOZAM',
        'vFkAllomas_TalajvizkutTerepmag', 'vFkAllomas_TalajvizkutKutperemmag',
        'vFkAllomas_TalajvizkutKutmelyseg', 'Talajvizallas',
        'vFaAllomas_RetegvizkutTerepmag', 'vFaAllomas_RetegvizkutKutperemmag', 'vFaAllomas_RetegvizkutKutmelyseg',
        'year', 'month', 'OBJECTID', 'VIZIG', 'TERM2004', 'TERM2005', 'TERM2006', 'TERM2007',
        'TERM2008', 'TERM2009', 'TERM2010', 'TERM2011', 'TERM2012', 'TERM2013', 'TERM2014',
        'TERM2015', 'TERM2016', 'TERM2017', 'TERM2018', 'TERM2019', 'TERM2020', 'TERM2021', 'TERM2022'
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# ──────────────────────────────────────────────────────────────────────────────
# 1.  Table-name helper (uses SQLAlchemy Inspector)
# ──────────────────────────────────────────────────────────────────────────────
def get_mysql_table_names(engine: Engine):
    return inspect(engine).get_table_names()

# ──────────────────────────────────────────────────────────────────────────────
# 2.  Fast insert using raw DB-API connection from the engine
# ──────────────────────────────────────────────────────────────────────────────
def fast_mysql_insert(df: pd.DataFrame, table: str, engine: Engine, chunksize: int = 1000):
    """
    Bulk-insert a DataFrame into `table` in chunks via the engine's raw connection.
    Keeps your old executemany logic but works with SQLAlchemy.
    """
    raw = engine.raw_connection()          # DB-API connection (mysql-connector)
    cursor = raw.cursor()

    cols = ", ".join([f"`{c}`" for c in df.columns])
    placeholders = ", ".join(["%s"] * len(df.columns))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"

    rows = df.values.tolist()
    n = len(rows)
    progress = st.progress(0, text="Uploading…")

    for i in range(0, n, chunksize):
        batch = rows[i:i + chunksize]
        cursor.executemany(sql, batch)
        raw.commit()
        progress.progress(min(i + chunksize, n) / n,
                          text=f"Uploaded {min(i + chunksize, n)} / {n} rows")

    progress.empty()
    cursor.close()
    raw.close()
    st.success(f"Successfully uploaded {n} rows to `{table}`.")

# ──────────────────────────────────────────────────────────────────────────────
# 3.  Main Streamlit page
# ──────────────────────────────────────────────────────────────────────────────
def database_viewer_page(engine: Engine):
    st.title("Well Database Page")
    tabs = st.tabs(["Database Viewer", "Upload CSV to Table"])

    # ── TAB 1: VIEWER / DELETE ───────────────────────────────────────────────
    with tabs[0]:
        table_names = get_mysql_table_names(engine)
        table_to_show = st.selectbox("Select table to display:", table_names)

        try:
            df = pd.read_sql_query(f"SELECT * FROM `{table_to_show}`", engine)
        except Exception as e:
            st.error(f"Failed to load {table_to_show}: {e}")
            return

        df = clean_numeric_columns(df)
        st.markdown(f"Showing **{len(df)}** rows from **{table_to_show}**.")
        st.dataframe(df, use_container_width=True)

        # -------------- Quick filters ----------------------------------------
        if table_to_show == "wells":
            st.subheader("Quick Filter for Wells Table")
            county = st.selectbox("County (VARMEGYE)",
                                  ["All"] + sorted(df['VARMEGYE'].dropna().unique()))
            if county != "All":
                filtered = clean_numeric_columns(df[df['VARMEGYE'] == county])
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** wells in **{county}**.")

        elif table_to_show == "osap_timeseries":
            st.subheader("Quick Filter for OSAP Timeseries Table")
            colA, colB = st.columns(2)
            with colA:
                vor = st.selectbox("VOR (Well code)",
                                   ["All"] + sorted(df['VOR'].dropna().unique()))
            with colB:
                year = st.selectbox("Year",
                                    ["All"] + sorted(df['year'].dropna().unique()))
            filtered = df.copy()
            if vor != "All":
                filtered = filtered[filtered['VOR'] == vor]
            if year != "All":
                filtered = filtered[filtered['year'] == year]
            if vor != "All" or year != "All":
                st.dataframe(clean_numeric_columns(filtered), use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for your filter.")

        elif table_to_show == "vizmerleg_table":
            st.subheader("Quick Filter for Vizmerleg Table")
            vor = st.selectbox("VOR (Well code)",
                               ["All"] + sorted(df['VOR'].dropna().unique()))
            if vor != "All":
                filtered = df[df['VOR'] == vor]
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for VOR = **{vor}**.")

        elif table_to_show in ("talajviz_table", "melyviz_table"):
            st.subheader(f"Quick Filter for {table_to_show} Table")
            rendszam = st.selectbox("Rendszam",
                                    ["All"] + sorted(df['Rendszam'].dropna().unique()))
            if rendszam != "All":
                filtered = df[df['Rendszam'] == rendszam]
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for Rendszam = **{rendszam}**.")

        # -------------- Danger zone: delete entire table ----------------------
        st.markdown("---")
        st.subheader("⚠️ Danger zone: Delete all data from this table")
        if st.button(f"Delete ALL data from `{table_to_show}` table"):
            try:
                with engine.begin() as conn:      # auto-commit on success
                    conn.execute(text(f"DELETE FROM `{table_to_show}`"))
                st.success(f"All data deleted from `{table_to_show}`. Refresh to see effect.")
            except Exception as e:
                st.error(f"Could not delete data: {e}")

    # ── TAB 2: UPLOAD CSV ────────────────────────────────────────────────────
    with tabs[1]:
        st.header("Upload CSV to Any Table")
        st.markdown("Columns must match the table exactly; see note below for accented columns.")
        table_names = get_mysql_table_names(engine)
        table_to_upload = st.selectbox("Select table to upload to:", table_names,
                                       key="upload_select_table")

        uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="upload_file")
        if uploaded:
            try:
                df_new = pd.read_csv(uploaded)

                # Rename accented columns for talajviz/melyviz tables
                if table_to_upload in ("talajviz_table", "melyviz_table"):
                    df_new = df_new.rename(columns={'Dátum': 'Datum',
                                                    'Talajvízállás': 'Talajvizallas'})

                st.write("First 5 rows of the file (after any renaming):")
                st.dataframe(df_new.head())

                if st.button(f"Upload to `{table_to_upload}` table"):
                    fast_mysql_insert(df_new, table_to_upload, engine, chunksize=1000)
            except Exception as e:
                st.error(f"Failed to import CSV: {e}")

        st.markdown("""
        **Note:** When uploading to `talajviz_table` or `melyviz_table`, columns `Dátum`
        and `Talajvízállás` are automatically renamed to `Datum` and `Talajvizallas`.
        """)

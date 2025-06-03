import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

def get_sqlalchemy_engine():
    return create_engine("mysql+pymysql://Hawkar:Noway2025@188.36.44.146:8081/wells")

def clean_numeric_columns(df):
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

def get_mysql_table_names(conn):
    q = "SHOW TABLES"
    cur = conn.cursor()
    cur.execute(q)
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    return tables

def database_viewer_page(conn):
    st.title("Well Database Page")
    tabs = st.tabs(["Database Viewer", "Upload CSV to Table"])

    # -------- TAB 1: VIEWER/DELETE --------
    with tabs[0]:
        table_names = get_mysql_table_names(conn)
        table_to_show = st.selectbox("Select table to display:", table_names)
        try:
            df = pd.read_sql(f"SELECT * FROM {table_to_show}", conn)
        except Exception as e:
            st.error(f"Failed to load {table_to_show}: {e}")
            return

        df = clean_numeric_columns(df)

        st.markdown(f"Showing **{len(df)}** rows from **{table_to_show}**.")
        st.dataframe(df, use_container_width=True)

        # Filters (same as before)
        if table_to_show == "wells":
            st.subheader("Quick Filter for Wells Table")
            county = st.selectbox("County (VARMEGYE)", ["All"] + sorted(df['VARMEGYE'].dropna().unique()))
            if county != "All":
                filtered = df[df['VARMEGYE'] == county]
                filtered = clean_numeric_columns(filtered)
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** wells in **{county}**.")
        elif table_to_show == "osap_timeseries":
            st.subheader("Quick Filter for OSAP Timeseries Table")
            colA, colB = st.columns(2)
            with colA:
                unique_vor = ["All"] + sorted(df['VOR'].dropna().unique())
                selected_vor = st.selectbox("VOR (Well code)", unique_vor)
            with colB:
                unique_years = ["All"] + sorted(df['year'].dropna().unique())
                selected_year = st.selectbox("Year", unique_years)
            filtered = df.copy()
            if selected_vor != "All":
                filtered = filtered[filtered['VOR'] == selected_vor]
            if selected_year != "All":
                filtered = filtered[filtered['year'] == selected_year]
            if selected_vor != "All" or selected_year != "All":
                filtered = clean_numeric_columns(filtered)
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for your filter.")
        elif table_to_show == "vizmerleg_table":
            st.subheader("Quick Filter for Vizmerleg Table")
            vor = st.selectbox("VOR (Well code)", ["All"] + sorted(df['VOR'].dropna().unique()))
            if vor != "All":
                filtered = df[df['VOR'] == vor]
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for VOR = **{vor}**.")
        elif table_to_show == "talajviz_table":
            st.subheader("Quick Filter for Talajviz Table")
            rendszam = st.selectbox("Rendszam", ["All"] + sorted(df['Rendszam'].dropna().unique()))
            if rendszam != "All":
                filtered = df[df['Rendszam'] == rendszam]
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for Rendszam = **{rendszam}**.")
        elif table_to_show == "melyviz_table":
            st.subheader("Quick Filter for Melyviz Table (Deep Wells)")
            rendszam = st.selectbox("Rendszam", ["All"] + sorted(df['Rendszam'].dropna().unique()))
            if rendszam != "All":
                filtered = df[df['Rendszam'] == rendszam]
                st.dataframe(filtered, use_container_width=True)
                st.markdown(f"Found **{len(filtered)}** records for Rendszam = **{rendszam}**.")

        st.markdown("---")
        st.subheader("⚠️ Danger zone: Delete all data from this table")
        if st.button(f"Delete ALL data from '{table_to_show}' table"):
            try:
                cur = conn.cursor()
                cur.execute(f"DELETE FROM {table_to_show};")
                conn.commit()
                cur.close()
                st.success(f"All data deleted from '{table_to_show}'. Please refresh to see effect.")
            except Exception as e:
                st.error(f"Could not delete data: {e}")

    # -------- TAB 2: UPLOAD CSV --------
    with tabs[1]:
        st.header("Upload CSV to Any Table")
        st.markdown("You can upload a CSV to any table. The columns must match the table columns exactly (see note below for accented columns).")

        table_names = get_mysql_table_names(conn)
        table_to_upload = st.selectbox("Select table to upload to:", table_names, key="upload_select_table")

        uploaded_file = st.file_uploader("Choose CSV file to upload (columns must match table)", type=["csv"], key="upload_file")
        if uploaded_file is not None:
            try:
                df_new = pd.read_csv(uploaded_file)

                # Handle accented columns for talajviz_table and melyviz_table
                if table_to_upload == "talajviz_table":
                    col_rename = {'Dátum': 'Datum', 'Talajvízállás': 'Talajvizallas'}
                    df_new = df_new.rename(columns=col_rename)
                if table_to_upload == "melyviz_table":
                    col_rename = {'Dátum': 'Datum', 'Talajvízállás': 'Talajvizallas'}
                    df_new = df_new.rename(columns=col_rename)

                st.write("First 5 rows of your file (after column name fix if any):")
                st.dataframe(df_new.head())
                if st.button(f"Upload to '{table_to_upload}' table"):
                    engine = get_sqlalchemy_engine()
                    df_new.to_sql(table_to_upload, engine, if_exists='append', index=False, method='multi')
                    st.success(f"Successfully imported {len(df_new)} rows into '{table_to_upload}'!")
            except Exception as e:
                st.error(f"Failed to import CSV: {e}")
        st.markdown("""
        **Note:** If uploading to `talajviz_table` or `melyviz_table`, columns `Dátum` and `Talajvízállás`
        will be automatically renamed to `Datum` and `Talajvizallas`.
        """)

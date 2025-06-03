import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt

def monthly_page(db_path):
    st.title("Monthly Groundwater Table Summary (Min/Mean/Max)")

    table_choice = st.selectbox("Select table", ['talajviz_table', 'melyviz_table'])
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(f"SELECT * FROM {table_choice}", conn)
        conn.close()
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # Compute vizkutfenekmagasag if not present
    if table_choice == 'talajviz_table':
        col1 = 'vFkAllomas_TalajvizkutKutperemmag'
    else:
        col1 = 'vFaAllomas_RetegvizkutKutperemmag'
    if 'Talajvízállás' in df.columns:
        col2 = 'Talajvízállás'
    elif 'Talajvizallas' in df.columns:
        col2 = 'Talajvizallas'
    else:
        st.error(f"Could not find 'Talajvízállás' or 'Talajvizallas' in {table_choice}.")
        return

    # Always (re)compute vizkutfenekmagasag for safety
    df['vizkutfenekmagasag'] = df[col1] + df[col2]
    value_col = 'vizkutfenekmagasag'

    if 'Datum' in df.columns:
        df['Datum'] = pd.to_datetime(df['Datum'], errors='coerce')
    else:
        st.error("Could not find 'Datum' column in the table.")
        return

    df['Year'] = df['Datum'].dt.year
    df['Month'] = df['Datum'].dt.month

    rendszam_unique = sorted(df['Rendszam'].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select Rendszam Well(s) for Time Series Plot", rendszam_unique,
        default=(rendszam_unique[0] if rendszam_unique else [])
    )

    df_valid = df.dropna(subset=['Rendszam', 'Year', 'Month', value_col])
    df_plot = df_valid[df_valid['Rendszam'].isin(selected_rendszam)] if selected_rendszam else df_valid.copy()

    agg = df_plot.groupby(['Rendszam', 'Year', 'Month'])[value_col].agg(['mean', 'min', 'max']).reset_index()
    agg['date'] = pd.to_datetime(dict(year=agg['Year'], month=agg['Month'], day=1))
    st.dataframe(agg.sort_values(['Rendszam', 'date']), use_container_width=True)

    st.subheader("Monthly Time Series Plot Options")
    show_mean = st.checkbox("Show Mean", value=True)
    show_max = st.checkbox("Show Max", value=True)
    show_min = st.checkbox("Show Min", value=True)

    st.subheader("Monthly Mean, Min, and Max for Selected Wells (vizkutfenekmagasag)")
    plt.figure(figsize=(12, 5))
    color_map = {}
    for idx, rendszam in enumerate(sorted(agg['Rendszam'].unique())):
        group = agg[agg['Rendszam'] == rendszam]
        color = plt.get_cmap('tab10')(idx % 10)
        color_map[rendszam] = color
        if show_mean:
            plt.plot(group['date'], group['mean'], label=f'{rendszam} Mean', color=color, linestyle='-')
        if show_max:
            plt.plot(group['date'], group['max'], label=f'{rendszam} Max', color=color, linestyle='--')
        if show_min:
            plt.plot(group['date'], group['min'], label=f'{rendszam} Min', color=color, linestyle=':')
    plt.xlabel("Date")
    plt.ylabel('vizkutfenekmagasag')
    plt.title(f"Monthly vizkutfenekmagasag Statistics (by Well)")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # --- Wide Export for ALL wells: mean, min, max columns per month-year ---
    st.subheader("Download 'wide' Well × Month Table (mean, min, max columns for each month) as CSV")
    agg_all = df_valid.groupby(['Rendszam', 'Year', 'Month'])[value_col].agg(['mean', 'min', 'max']).reset_index()
    wide_mean = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values='mean')
    wide_min  = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values='min')
    wide_max  = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values='max')
    wide_mean.columns = [f"{int(yr)}_{int(mn):02d}_mean" for yr, mn in wide_mean.columns]
    wide_min.columns  = [f"{int(yr)}_{int(mn):02d}_min" for yr, mn in wide_min.columns]
    wide_max.columns  = [f"{int(yr)}_{int(mn):02d}_max" for yr, mn in wide_max.columns]
    wide_full = pd.concat([wide_mean, wide_min, wide_max], axis=1).reset_index()

    # Reorder columns for download
    col_base = set()
    for col in wide_full.columns:
        if col.endswith('_mean'):
            col_base.add(col[:-5])
    ordered_cols = ['Rendszam']
    for base in sorted(col_base):
        for stat in ['mean', 'min', 'max']:
            col = f"{base}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)
    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)
    st.download_button(
        "Download Well-Month Table (Wide CSV: mean/min/max)",
        wide_full.to_csv(index=False).encode('utf-8'),
        file_name=f"monthly_wide_{table_choice}_vizkutfenekmagasag.csv",
        mime='text/csv'
    )

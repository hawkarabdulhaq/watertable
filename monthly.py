import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io

def monthly_page(conn):
    st.title("Monthly Groundwater Table Summary (Min/Mean/Max)")

    # Select table
    table_choice = st.selectbox("Select groundwater table", ['talajviz_table', 'melyviz_table'])
    try:
        df = pd.read_sql(f"SELECT * FROM {table_choice}", conn)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # Choose correct columns
    col1 = 'vFkAllomas_TalajvizkutKutperemmag' if table_choice == 'talajviz_table' else 'vFaAllomas_RetegvizkutKutperemmag'
    col2 = None
    if 'Talajvízállás' in df.columns:
        col2 = 'Talajvízállás'
    elif 'Talajvizallas' in df.columns:
        col2 = 'Talajvizallas'
    else:
        st.error("No water level column found.")
        return

    # Compute water table elevation
    df['vizkutfenekmagasag'] = df[col1] + df[col2]

    # Date handling
    if 'Datum' not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df['Datum'] = pd.to_datetime(df['Datum'], errors='coerce')
    df['Year'] = df['Datum'].dt.year
    df['Month'] = df['Datum'].dt.month

    # Well selector
    rendszam_unique = sorted(df['Rendszam'].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select wells for time series plot",
        rendszam_unique,
        default=rendszam_unique[:1]
    )

    value_col = 'vizkutfenekmagasag'
    df_valid = df.dropna(subset=['Rendszam', 'Year', 'Month', value_col])
    if selected_rendszam:
        df_plot = df_valid[df_valid['Rendszam'].isin(selected_rendszam)]
    else:
        df_plot = df_valid.copy()

    # Aggregate stats
    agg = (
        df_plot.groupby(['Rendszam', 'Year', 'Month'])[value_col]
        .agg(['mean', 'min', 'max'])
        .reset_index()
    )
    agg['date'] = pd.to_datetime(dict(year=agg['Year'], month=agg['Month'], day=1))
    st.dataframe(agg.sort_values(['Rendszam', 'date']), use_container_width=True)

    # Plot options
    st.subheader("Time Series Plot Options")
    show_mean = st.checkbox("Show Mean", value=True)
    show_max = st.checkbox("Show Max", value=True)
    show_min = st.checkbox("Show Min", value=True)

    # Plot
    st.subheader("Monthly Mean, Min, and Max per Well")
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
    plt.title("Monthly vizkutfenekmagasag Stats by Well")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # --- Wide Export for ALL wells: mean, min, max columns per month-year ---
    st.subheader("Download Well × Month Table (mean, min, max) as Excel")
    agg_all = (
        df_valid.groupby(['Rendszam', 'Year', 'Month'])[value_col]
        .agg(['mean', 'min', 'max'])
        .reset_index()
    )

    # Pivot to wide format
    wide_mean = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values='mean')
    wide_min  = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values='min')
    wide_max  = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values='max')

    # Clean up column names
    wide_mean.columns = [f"{int(yr)}_{int(mn):02d}_mean" for yr, mn in wide_mean.columns]
    wide_min.columns  = [f"{int(yr)}_{int(mn):02d}_min"  for yr, mn in wide_min.columns]
    wide_max.columns  = [f"{int(yr)}_{int(mn):02d}_max"  for yr, mn in wide_max.columns]

    wide_full = pd.concat([wide_mean, wide_min, wide_max], axis=1).reset_index()

    # Reorder columns: Rendszam, then all year-month blocks in mean/min/max order
    col_base = set(col[:-5] for col in wide_full.columns if col.endswith('_mean'))
    ordered_cols = ['Rendszam']
    for base in sorted(col_base):
        for stat in ['mean', 'min', 'max']:
            col = f"{base}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)
    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)

    # Excel download (main)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        wide_full.to_excel(writer, index=False, sheet_name='MonthlyWide')
        writer.save()
    st.download_button(
        "Download Well-Month Table (Excel)",
        buffer.getvalue(),
        file_name=f"monthly_wide_{table_choice}_vizkutfenekmagasag.xlsx",
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Optional: also offer CSV (one line, not required)
    # st.download_button(
    #     "Download CSV",
    #     wide_full.to_csv(index=False).encode('utf-8'),
    #     file_name=f"monthly_wide_{table_choice}_vizkutfenekmagasag.csv",
    #     mime='text/csv'
    # )

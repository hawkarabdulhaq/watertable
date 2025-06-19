import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io

def monthly_page(conn):
    st.title("Monthly Groundwater Table Summary (Min/Mean/Max)")

    # Select table
    table_choice = st.selectbox("Select groundwater table", ['talajviz_table', 'melyviz_table'])

    # Load data
    try:
        df = pd.read_sql(f"SELECT * FROM {table_choice}", conn)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # Detect and create required columns
    col1 = 'vFkAllomas_TalajvizkutKutperemmag' if table_choice == 'talajviz_table' else 'vFaAllomas_RetegvizkutKutperemmag'
    col2 = 'Talajvízállás' if 'Talajvízállás' in df.columns else ('Talajvizallas' if 'Talajvizallas' in df.columns else None)
    if not col2 or col1 not in df.columns:
        st.error("One or more required columns are missing in the table.")
        return

    df['vizkutfenekmagasag'] = df[col1] + df[col2]

    if 'Datum' not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df['Datum'] = pd.to_datetime(df['Datum'], errors='coerce')
    df['Year'] = df['Datum'].dt.year
    df['Month'] = df['Datum'].dt.month

    rendszam_unique = sorted(df['Rendszam'].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select wells for time series plot",
        rendszam_unique,
        default=rendszam_unique[:1] if rendszam_unique else []
    )

    value_col = 'vizkutfenekmagasag'
    df_valid = df.dropna(subset=['Rendszam', 'Year', 'Month', value_col])
    df_plot = df_valid[df_valid['Rendszam'].isin(selected_rendszam)] if selected_rendszam else df_valid.copy()

    # Plot and export options
    st.subheader("Select statistics to show (will affect both plot and download)")
    show_mean = st.checkbox("Mean", value=True)
    show_max = st.checkbox("Max", value=True)
    show_min = st.checkbox("Min", value=True)

    selected_stats = []
    if show_mean: selected_stats.append('mean')
    if show_min:  selected_stats.append('min')
    if show_max:  selected_stats.append('max')

    if not selected_stats:
        st.warning("Please select at least one statistic to display.")
        return

    # Aggregate as needed
    agg = (
        df_plot.groupby(['Rendszam', 'Year', 'Month'])[value_col]
        .agg(selected_stats)
        .reset_index()
    )
    agg['date'] = pd.to_datetime(dict(year=agg['Year'], month=agg['Month'], day=1))
    st.dataframe(agg.sort_values(['Rendszam', 'date']), use_container_width=True)

    # Plot
    st.subheader("Monthly Statistics per Well")
    plt.figure(figsize=(12, 5))
    for idx, rendszam in enumerate(sorted(agg['Rendszam'].unique())):
        group = agg[agg['Rendszam'] == rendszam]
        color = plt.get_cmap('tab10')(idx % 10)
        if show_mean and 'mean' in group.columns:
            plt.plot(group['date'], group['mean'], label=f'{rendszam} Mean', color=color, linestyle='-')
        if show_max and 'max' in group.columns:
            plt.plot(group['date'], group['max'], label=f'{rendszam} Max', color=color, linestyle='--')
        if show_min and 'min' in group.columns:
            plt.plot(group['date'], group['min'], label=f'{rendszam} Min', color=color, linestyle=':')
    plt.xlabel("Date")
    plt.ylabel('vizkutfenekmagasag')
    plt.title("Monthly vizkutfenekmagasag Stats by Well")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # Wide Excel Export - include only selected statistics
    st.subheader("Download Well × Month Table (selected statistics) as Excel")
    agg_all = (
        df_valid.groupby(['Rendszam', 'Year', 'Month'])[value_col]
        .agg(selected_stats)
        .reset_index()
    )

    wide_dfs = []
    for stat in selected_stats:
        wide = agg_all.pivot(index='Rendszam', columns=['Year', 'Month'], values=stat)
        wide.columns = [f"{int(yr)}_{int(mn):02d}_{stat}" for yr, mn in wide.columns]
        wide_dfs.append(wide)
    wide_full = pd.concat(wide_dfs, axis=1).reset_index()

    # Order columns: Rendszam, then all by date/stat order
    col_base = set()
    for stat_df in wide_dfs:
        for col in stat_df.columns:
            col_base.add(col[:-5])  # Remove stat suffix
    ordered_cols = ['Rendszam']
    for base in sorted(col_base):
        for stat in selected_stats:
            col = f"{base}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)
    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)

    # Excel download
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        wide_full.to_excel(writer, index=False, sheet_name='MonthlyWide')
    st.download_button(
        "Download Well-Month Table (Excel)",
        buffer.getvalue(),
        file_name=f"monthly_wide_{table_choice}_vizkutfenekmagasag.xlsx",
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Optional: CSV export (uncomment if needed)
    # st.download_button(
    #     "Download CSV",
    #     wide_full.to_csv(index=False).encode('utf-8'),
    #     file_name=f"monthly_wide_{table_choice}_vizkutfenekmagasag.csv",
    #     mime='text/csv'
    # )

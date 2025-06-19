import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io

def monthly_page(conn):
    st.title("Monthly Groundwater Table Summary (Min / Mean / Max)")

    # 1️⃣  Load data -----------------------------------------------------------------
    table_choice = st.selectbox("Select groundwater table",
                                ['talajviz_table', 'melyviz_table'])

    try:
        df = pd.read_sql(f"SELECT * FROM {table_choice}", conn)
    except Exception as e:
        st.error(f"Failed to load {table_choice}: {e}")
        return

    # --- column mapping ------------------------------------------------------------
    col1 = ('vFkAllomas_TalajvizkutKutperemmag'
            if table_choice == 'talajviz_table'
            else 'vFaAllomas_RetegvizkutKutperemmag')
    if 'Talajvízállás' in df.columns:
        col2 = 'Talajvízállás'
    elif 'Talajvizallas' in df.columns:
        col2 = 'Talajvizallas'
    else:
        st.error("No 'Talajvízállás' or 'Talajvizallas' column found.")
        return

    if col1 not in df.columns:
        st.error(f"'{col1}' column missing in the table.")
        return

    # --- calculated column & date parts -------------------------------------------
    df['vizkutfenekmagasag'] = df[col1] + df[col2]
    if 'Datum' not in df.columns:
        st.error("No 'Datum' column found.")
        return
    df['Datum'] = pd.to_datetime(df['Datum'], errors='coerce')
    df['Year']   = df['Datum'].dt.year
    df['Month']  = df['Datum'].dt.month

    # 2️⃣  Well selector -------------------------------------------------------------
    rendszam_unique = sorted(df['Rendszam'].dropna().unique())
    selected_rendszam = st.multiselect(
        "Select wells for time-series plot",
        rendszam_unique,
        default=rendszam_unique[:1] if rendszam_unique else []
    )

    df_valid = df.dropna(subset=['Rendszam', 'Year', 'Month', 'vizkutfenekmagasag'])
    df_plot  = (df_valid[df_valid['Rendszam'].isin(selected_rendszam)]
                if selected_rendszam else df_valid.copy())

    # 3️⃣  Choose statistics to show / export --------------------------------------
    st.subheader("Statistics to include")
    show_mean = st.checkbox("Mean", value=True, key="chk_mean")
    show_min  = st.checkbox("Min",  value=True, key="chk_min")
    show_max  = st.checkbox("Max",  value=True, key="chk_max")

    selected_stats = [stat for stat, flag in
                      [('mean', show_mean), ('min', show_min), ('max', show_max)]
                      if flag]

    if not selected_stats:
        st.warning("Please select at least one statistic.")
        return

    # 4️⃣  Aggregate for plot/table -------------------------------------------------
    agg = (df_plot.groupby(['Rendszam', 'Year', 'Month'])['vizkutfenekmagasag']
           .agg(selected_stats)
           .reset_index())
    agg['date'] = pd.to_datetime(dict(year=agg['Year'],
                                      month=agg['Month'],
                                      day=1))

    st.dataframe(agg.sort_values(['Rendszam', 'date']),
                 use_container_width=True)

    # 5️⃣  Plot ----------------------------------------------------------------------
    st.subheader("Time-series plot")
    plt.figure(figsize=(12, 4))
    cmap = plt.get_cmap('tab10')

    for idx, rendszam in enumerate(sorted(agg['Rendszam'].unique())):
        g = agg[agg['Rendszam'] == rendszam]
        color = cmap(idx % 10)
        if 'mean' in selected_stats:
            plt.plot(g['date'], g['mean'], label=f'{rendszam} Mean',
                     color=color, linestyle='-')
        if 'max' in selected_stats:
            plt.plot(g['date'], g['max'],  label=f'{rendszam} Max',
                     color=color, linestyle='--')
        if 'min' in selected_stats:
            plt.plot(g['date'], g['min'],  label=f'{rendszam} Min',
                     color=color, linestyle=':')
    plt.xlabel("Date")
    plt.ylabel("vizkutfenekmagasag")
    plt.title("Monthly statistics by well")
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt.gcf())
    plt.clf()

    # 6️⃣  Build “wide” table only with selected stats ------------------------------
    st.subheader("Download Well × Month table")
    agg_all = (df_valid.groupby(['Rendszam', 'Year', 'Month'])['vizkutfenekmagasag']
               .agg(selected_stats)
               .reset_index())

    wide_parts = []
    for stat in selected_stats:
        wide = agg_all.pivot(index='Rendszam',
                             columns=['Year', 'Month'],
                             values=stat)
        wide.columns = [f"{int(yr)}_{int(mn):02d}_{stat}"
                        for yr, mn in wide.columns]
        wide_parts.append(wide)

    wide_full = (pd.concat(wide_parts, axis=1)
                   .reset_index())

    # Order columns: Rendszam then each Year-Month block in stat order
    ordered_cols = ['Rendszam']
    col_blocks = sorted({c.rsplit('_', 1)[0] for c in wide_full.columns
                         if c != 'Rendszam'})
    for block in col_blocks:
        for stat in selected_stats:
            col = f"{block}_{stat}"
            if col in wide_full.columns:
                ordered_cols.append(col)
    wide_full = wide_full[ordered_cols]

    st.dataframe(wide_full.head(), use_container_width=True)

    # 7️⃣  Excel download ------------------------------------------------------------
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        wide_full.to_excel(writer, index=False, sheet_name='MonthlyWide')
    st.download_button(
        "Download selected statistics (Excel)",
        buffer.getvalue(),
        file_name=f"monthly_{'_'.join(selected_stats)}_{table_choice}.xlsx",
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Optional CSV example:
    # st.download_button(
    #     "Download CSV",
    #     wide_full.to_csv(index=False).encode('utf-8'),
    #     file_name=f"monthly_{'_'.join(selected_stats)}_{table_choice}.csv",
    #     mime='text/csv'
    # )

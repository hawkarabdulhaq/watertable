import streamlit as st
import matplotlib.pyplot as plt
import mysql.connector

from timeseries import timeseries_page
from map import map_page
from database import database_viewer_page
from export import export_page
from monthly import monthly_page  # <-- NEW

st.set_page_config(page_title="Well Database Viewer", layout="wide")

# --- MySQL connection settings ---
MYSQL_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",
    "password": "Noway2025",
    "database": "wells"
}

def get_mysql_conn():
    return mysql.connector.connect(**MYSQL_CONFIG)

# Sidebar navigation
st.sidebar.title("Navigation")
if 'page' not in st.session_state:
    st.session_state.page = "Database Viewer"

if st.sidebar.button("Database Viewer"):
    st.session_state.page = "Database Viewer"
if st.sidebar.button("Time Series Chart"):
    st.session_state.page = "Time Series Chart"
if st.sidebar.button("Well Map"):
    st.session_state.page = "Well Map"
if st.sidebar.button("Export"):
    st.session_state.page = "Export"
if st.sidebar.button("Monthly"):    # <-- NEW BUTTON
    st.session_state.page = "Monthly"

page = st.session_state.page

# Open the connection once, share with all page functions
try:
    conn = get_mysql_conn()
except Exception as e:
    st.error(f"Could not connect to database: {e}")
    st.stop()

if page == "Database Viewer":
    database_viewer_page(conn)
elif page == "Time Series Chart":
    timeseries_page(conn)
elif page == "Well Map":
    map_page(conn)
elif page == "Export":
    export_page(conn)
elif page == "Monthly":
    monthly_page(conn)

# Close the connection at the end
conn.close()

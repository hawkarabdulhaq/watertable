import streamlit as st
import mysql.connector

from database import database_viewer_page
from monthly import monthly_page

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
if st.sidebar.button("Monthly"):
    st.session_state.page = "Monthly"

page = st.session_state.page

# Open the connection once, share with both pages
try:
    conn = get_mysql_conn()
except Exception as e:
    st.error(f"Could not connect to database: {e}")
    st.stop()

if page == "Database Viewer":
    database_viewer_page(conn)
elif page == "Monthly":
    monthly_page(conn)

conn.close()

# app.py
import os
import streamlit as st
from sqlalchemy import create_engine, text

from database import database_viewer_page
from monthly   import monthly_page

st.set_page_config(page_title="Well Database Viewer", layout="wide")

# ------------------------------------------------------------------------------
# 🐬  MySQL connection settings  – use SQLAlchemy (no pandas warning)
# ------------------------------------------------------------------------------

MYSQL_CONFIG = {
    "host":     "188.36.44.146",
    "port":     8081,                     # unusual, but keep as-is
    "user":     "Hawkar",
    "password": "Noway2025",              # ❗ Consider ENV VAR in production
    "database": "wells",
}

# Build an SQLAlchemy URL → mysql+mysqlconnector://user:pw@host:port/db
MYSQL_URI = (
    f"mysql+mysqlconnector://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}"
    f"@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}"
)

# Re-use one engine for the whole session (Streamlit cache)
@st.cache_resource(show_spinner=False)
def get_engine():
    return create_engine(MYSQL_URI, pool_recycle=3600, pool_pre_ping=True)

engine = get_engine()

# ------------------------------------------------------------------------------
# Sidebar navigation
# ------------------------------------------------------------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Choose a page:",
    ["Database Viewer", "Monthly"],
    index=0 if "page" not in st.session_state else ["Database Viewer", "Monthly"].index(st.session_state["page"]),
    key="page"
)

# ------------------------------------------------------------------------------
# Dispatch pages
# ------------------------------------------------------------------------------
try:
    if page == "Database Viewer":
        database_viewer_page(engine)      # pass engine instead of raw connector
    elif page == "Monthly":
        monthly_page(engine)
finally:
    # Optional: dispose when Streamlit session dies
    # (engine gets cached; disposal here is usually harmless)
    engine.dispose(close=False)

# main.py
# Entry point for the app
# Sidebar to switch between Student View and Coach View
# Run with: streamlit run main.py

import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()

# ── Build RAG DB if not exists ─────────────────────────────────────────────
if not os.path.exists("chroma_db"):
    import subprocess
    subprocess.run(["python3", "rag_setup.py"])

# ── Sidebar navigation ─────────────────────────────────────────────────────
st.sidebar.title("Success Coach AI")
view = st.sidebar.radio(
    "Select View",
    ["Student View", "Coach View"]
)

# ── Load correct view ──────────────────────────────────────────────────────
if view == "Student View":
    # Import and run student view
    # We import here so each view only loads what it needs
    import importlib
    import student_app
    importlib.reload(student_app)
    student_app.show_student_view()

elif view == "Coach View":
    import importlib
    import coach_app
    importlib.reload(coach_app)
    coach_app.show_coach_view()
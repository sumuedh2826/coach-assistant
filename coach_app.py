# coach_app.py
# M7 — Coach View
# Generate Today's Plan button
# Reads who talked today from Mem0 session logs
# Planning agent generates structured day
# Calendar events created for meeting slots

import streamlit as st
from memory import get_todays_sessions
from planning_agent import run_planning_agent
from calendar_utils import create_calendar_events
from datetime import date
import json
import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

def get_google_sheet_client():
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        service_account_info = json.loads(raw_json)
    else:
        service_account_info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_roster():
    try:
        spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID") or st.secrets.get("GOOGLE_SPREADSHEET_ID")
        gc = get_google_sheet_client()
        spreadsheet = gc.open_by_key(spreadsheet_id)
        return spreadsheet.worksheet("roster").get_all_records()
    except Exception as e:
        st.error(f"Could not load roster: {e}")
        return []

def show_coach_view():
    st.title("🎯 Success Coach — Daily Plan")
    st.caption("Coach View")

    # ── Generate Today's Plan ──────────────────────────────────────────────
    if st.button("Generate Today's Plan", type="primary", use_container_width=True):
        with st.spinner("Checking who talked today and generating plan..."):

            # Step 1 — Get all student IDs
            roster = load_roster()
            if not roster:
                st.error("Could not load student roster.")
                return

            student_ids = [s["student_id"] for s in roster]

            # Step 2 — Find which students talked today with their signals
            todays_sessions = get_todays_sessions(student_ids)

            # Step 3 — Run planning agent
            plan = run_planning_agent(todays_sessions)

            # Step 4 — Create calendar events for meeting slots
            today   = date.today()
            created = []

            if plan.get("plan_type") == "student_sessions":
                created = create_calendar_events(plan, today)

            # Store everything in session state
            st.session_state["coach_plan"]     = plan
            st.session_state["coach_sessions"] = todays_sessions
            st.session_state["calendar_events"] = created

    # ── Display plan ───────────────────────────────────────────────────────
    if "coach_plan" in st.session_state:
        plan     = st.session_state["coach_plan"]
        sessions = st.session_state.get("coach_sessions", [])
        events   = st.session_state.get("calendar_events", [])

        st.divider()

        # Summary
        summary = plan.get("summary", "Today's Plan")
        st.markdown(f"### {summary}")

        # Who talked today
        if sessions:
            st.markdown("#### Students who had sessions today")
            for s in sessions:
                severity = s.get("severity")
                if severity == "high":
                    badge = "🔴 HIGH"
                elif severity == "medium":
                    badge = "🟡 MEDIUM"
                else:
                    badge = "🟢 No signal"

                st.markdown(f"**{s['student_name']}** — {badge} — Session ended at {s['time']}")
                if s.get("signal_summary"):
                    st.caption(s["signal_summary"])
        else:
            st.info("No students had sessions today — showing default plan.")

        st.divider()

        # Schedule
        st.markdown("#### Today's Schedule")
        for slot in plan.get("schedule", []):
            time     = slot.get("time", "")
            activity = slot.get("activity", "")
            detail   = slot.get("detail", "")

            if "Meeting" in activity:
                st.markdown(f"**{time}** — 📅 {activity}")
            elif "Lunch" in activity:
                st.markdown(f"**{time}** — 🍽️ {activity}")
            elif "Review" in activity:
                st.markdown(f"**{time}** — 📋 {activity}")
            else:
                st.markdown(f"**{time}** — 🔧 {activity}")

            if detail:
                st.caption(detail)

        # Calendar events created
        if events:
            st.divider()
            st.markdown("#### Calendar Invites Created")
            for e in events:
                st.markdown(f"✅ **{e['student']}** — {e['time']} — [Open in Calendar]({e['link']})")

        # Deferred students
        deferred = plan.get("deferred", [])
        if deferred:
            st.divider()
            st.markdown("#### Deferred to Tomorrow")
            for d in deferred:
                st.markdown(f"**{d.get('student_name', '')}** — {d.get('reason', '')}")
# student_app.py
# Student view
# Fix: small delay after saving session log so Mem0 has time to index
# Fix: signal and reason shown after end session and persists till student changes

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from agent import build_agent_executor, generate_session_summary, extract_factual_memory
from memory import save_session_summary, save_factual_memory, get_all_student_memory, save_signal, save_session_log
from flagging_agent import run_flagging_agent

load_dotenv()

# ── Google Sheets — roster only ────────────────────────────────────────────
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
        st.error(f"Could not load student list: {e}")
        return []

def show_student_view():

    st.title("🎓 Success Coach AI")
    st.caption("Student View")

    roster = load_roster()
    if not roster:
        st.stop()

    # ── Student selector ───────────────────────────────────────────────────
    student_options = {
        f"{s['name']} ({s['student_id']})": s
        for s in roster
    }
    selected_label   = st.selectbox("Select your name to begin", list(student_options.keys()))
    selected_student = student_options[selected_label]

    st.write(f"Welcome, **{selected_student['name']}**")
    st.divider()

    # ── Chat history ───────────────────────────────────────────────────────
    chat_key = f"messages_{selected_student['student_id']}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    # ── Memory preview key — per student ──────────────────────────────────
    preview_key = f"memory_preview_{selected_student['student_id']}"
    if preview_key not in st.session_state:
        st.session_state[preview_key] = {"summary": "", "factual": ""}

    # ── Signal preview key — per student ──────────────────────────────────
    # Stores last signal so it stays visible until student changes
    signal_key = f"signal_preview_{selected_student['student_id']}"
    if signal_key not in st.session_state:
        st.session_state[signal_key] = None

    # ── Show last saved memory ─────────────────────────────────────────────
    memory_preview = st.session_state[preview_key]
    if memory_preview["summary"] or memory_preview["factual"]:
        with st.expander("Last Saved Memory", expanded=False):
            if memory_preview["factual"] and memory_preview["factual"] != "NO_FACTUAL_CONTENT":
                st.markdown("**Factual Memory:**")
                st.write(memory_preview["factual"])
            if memory_preview["summary"] and memory_preview["summary"] != "NO_SUMMARY":
                st.markdown("**Session Summary:**")
                st.write(memory_preview["summary"])

    # ── Show last signal ───────────────────────────────────────────────────
    # Stays visible until student selector changes
    last_signal = st.session_state[signal_key]
    if last_signal:
        severity = last_signal.get("severity")
        reason   = last_signal.get("reason", "")
        if severity == "high":
            st.error(f"🔴 Last Session Signal: HIGH — {reason}")
        elif severity == "medium":
            st.warning(f"🟡 Last Session Signal: MEDIUM — {reason}")
        else:
            st.success("🟢 Last Session Signal: No urgent concerns")

    # ── End Session ────────────────────────────────────────────────────────
    if st.session_state[chat_key]:
        if st.button("End Session"):
            with st.spinner("Saving session..."):
                import time

                messages = st.session_state[chat_key]

                # Generate both memory types
                summary = generate_session_summary(messages, selected_student["name"])
                factual = extract_factual_memory(messages, selected_student["name"])

                # Store for UI display
                st.session_state[preview_key] = {
                    "summary": summary,
                    "factual": factual
                }

                # Save to Mem0
                if summary != "NO_SUMMARY":
                    save_session_summary(selected_student["student_id"], summary)

                if factual != "NO_FACTUAL_CONTENT":
                    save_factual_memory(selected_student["student_id"], factual)

                # Run flagging agent
                signal = run_flagging_agent(
                    student_name=selected_student["name"],
                    student_id=selected_student["student_id"],
                    factual_memory=factual
                )

                # Save signal to Mem0
                save_signal(selected_student["student_id"], signal)

                # Save session log
                # Small wait after so Mem0 has time to index before coach fetches
                save_session_log(
                    selected_student["student_id"],
                    selected_student["name"]
                )
                time.sleep(3)

                # Store signal in session state for persistent display
                st.session_state[signal_key] = signal

                # Show signal
                severity = signal.get("severity")
                if severity == "high":
                    st.error("🔴 HIGH — Coach must meet today")
                    st.caption(signal.get("reason", ""))
                elif severity == "medium":
                    st.warning("🟡 MEDIUM — Meet today if slot available, otherwise tomorrow")
                    st.caption(signal.get("reason", ""))
                else:
                    st.success("Session saved — no urgent signals found")

            time.sleep(2)
            st.session_state[chat_key] = []
            st.rerun()

    # ── Display chat ───────────────────────────────────────────────────────
    for message in st.session_state[chat_key]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # ── Chat input ─────────────────────────────────────────────────────────
    user_input = st.chat_input("Ask me about your academics or the platform...")

    if user_input:
        st.session_state[chat_key].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):

                student_memory = get_all_student_memory(selected_student["student_id"])

                langchain_history = []

                if student_memory:
                    langchain_history.append(
                        HumanMessage(content=f"[STUDENT HISTORY — use this to personalise your responses]\n{student_memory}")
                    )
                    langchain_history.append(
                        AIMessage(content="Understood. I have reviewed this student's history and will personalise my responses accordingly.")
                    )

                for msg in st.session_state[chat_key][:-1]:
                    if msg["role"] == "user":
                        langchain_history.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        langchain_history.append(AIMessage(content=msg["content"]))

                langchain_history.append(HumanMessage(content=user_input))

                agent = build_agent_executor(
                    selected_student["name"],
                    selected_student["student_id"]
                )

                result = agent.invoke({"messages": langchain_history})
                reply = result["messages"][-1].content

            st.write(reply)

        st.session_state[chat_key].append({"role": "assistant", "content": reply})
        st.rerun()
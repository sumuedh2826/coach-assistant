# app.py
# Student view — LangChain 1.x + LangGraph + Mem0 2.0.7
# AI personalises responses using factual memory and session summaries
# Two memory types saved separately after every session

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from agent import build_agent_executor, generate_session_summary, extract_factual_memory
from memory import save_session_summary, save_factual_memory, get_all_student_memory

load_dotenv()

# ── Build RAG DB if not exists ─────────────────────────────────────────────
if not os.path.exists("chroma_db"):
    import subprocess
    subprocess.run(["python3", "rag_setup.py"])

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

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Success Coach AI", page_icon="🎓")
st.title("🎓 Success Coach AI")
st.caption("Student View")

roster = load_roster()
if not roster:
    st.stop()

# ── Student selector ───────────────────────────────────────────────────────
student_options = {
    f"{s['name']} ({s['student_id']})": s
    for s in roster
}
selected_label   = st.selectbox("Select your name to begin", list(student_options.keys()))
selected_student = student_options[selected_label]

st.write(f"Welcome, **{selected_student['name']}**")
st.divider()

# ── Chat history ───────────────────────────────────────────────────────────
chat_key = f"messages_{selected_student['student_id']}"
if chat_key not in st.session_state:
    st.session_state[chat_key] = []

# ── Memory preview — stays visible until student changes ──────────────────
# Stores what was saved last session so student can see it
preview_key = f"memory_preview_{selected_student['student_id']}"
if preview_key not in st.session_state:
    st.session_state[preview_key] = {"summary": "", "factual": ""}

memory_preview = st.session_state[preview_key]
if memory_preview["summary"] or memory_preview["factual"]:
    with st.expander("Last Saved Memory", expanded=False):
        if memory_preview["factual"] and memory_preview["factual"] != "NO_FACTUAL_CONTENT":
            st.markdown("**Factual Memory:**")
            st.write(memory_preview["factual"])
        if memory_preview["summary"] and memory_preview["summary"] != "NO_SUMMARY":
            st.markdown("**Session Summary:**")
            st.write(memory_preview["summary"])

# ── End Session ───────────────────────────────────────────────────────────
if st.session_state[chat_key]:
    if st.button("End Session"):
        with st.spinner("Saving session..."):

            messages = st.session_state[chat_key]

            # Generate both memory types from this conversation
            summary = generate_session_summary(messages, selected_student["name"])
            factual = extract_factual_memory(messages, selected_student["name"])

            # Store in session state for UI display
            st.session_state[preview_key] = {
                "summary": summary,
                "factual": factual
            }

            # Save to Mem0 only if meaningful content found
            if summary != "NO_SUMMARY":
                save_session_summary(selected_student["student_id"], summary)

            if factual != "NO_FACTUAL_CONTENT":
                save_factual_memory(selected_student["student_id"], factual)

            st.success("Session saved!")

        import time
        time.sleep(1)
        st.session_state[chat_key] = []
        st.rerun()

# ── Display chat ───────────────────────────────────────────────────────────
for message in st.session_state[chat_key]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ── Chat input ─────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask me about your academics or the platform...")

if user_input:
    st.session_state[chat_key].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            # Fetch all memory from past sessions
            # Injected before conversation so AI knows this student from message one
            student_memory = get_all_student_memory(selected_student["student_id"])

            langchain_history = []

            if student_memory:
                # Memory injected as first exchange before any current messages
                # This is what makes AI personalised from session one onwards
                langchain_history.append(
                    HumanMessage(content=f"[STUDENT HISTORY — use this to personalise your responses]\n{student_memory}")
                )
                langchain_history.append(
                    AIMessage(content="Understood. I have reviewed this student's history and will personalise my responses accordingly.")
                )

            # Add current conversation history
            for msg in st.session_state[chat_key][:-1]:
                if msg["role"] == "user":
                    langchain_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    langchain_history.append(AIMessage(content=msg["content"]))

            # Add current message
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
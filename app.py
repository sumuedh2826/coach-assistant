# app.py
# Step 3 final — LangChain 1.x + LangGraph
# UI only — all agent logic is in agent.py
# student_id never passed to AI — pre-filled in agent.py using partial()

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from agent import build_agent_executor

load_dotenv()

# ── Build RAG DB if not exists — needed for Streamlit Cloud ───────────────
if not os.path.exists("chroma_db"):
    import subprocess
    subprocess.run(["python3", "rag_setup.py"])

# ── Google Sheets — only for roster dropdown ──────────────────────────────
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
@st.cache_resource
def get_agent(student_name, student_id):
    return build_agent_executor(
        student_name,
        student_id
    )
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

# ── End Session ───────────────────────────────────────────────────────────
if st.session_state[chat_key]:
    if st.button("End Session"):
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

            # Convert stored chat history to LangChain message objects
            # Skip last message — that is the current input we pass separately
            langchain_history = []
            for msg in st.session_state[chat_key][:-1]:
                if msg["role"] == "user":
                    langchain_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    langchain_history.append(AIMessage(content=msg["content"]))

            # Add current message to history
            langchain_history.append(HumanMessage(content=user_input))

            # Build agent with this student's ID pre-filled in tools
            agent = get_agent(
                selected_student["name"],
                selected_student["student_id"]
            )

            # invoke passes full message history to agent
            # LangGraph handles tool calling loop internally
            result = agent.invoke({
                "messages": langchain_history
            })

            # Last message in result is always the final AI response
            reply = result["messages"][-1].content

        st.write(reply)

    st.session_state[chat_key].append({"role": "assistant", "content": reply})
    st.rerun()
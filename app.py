# app.py
# Step 2 updated:
# - Removed upfront data loading
# - Google Sheets is now a TOOL that AI calls only when it needs student data
# - AI decides on its own when to fetch data vs answer from its own knowledge

import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import gspread
from google.oauth2.service_account import Credentials

# ── Load environment variables ─────────────────────────────────────────────
load_dotenv()

# ── OpenAI client ──────────────────────────────────────────────────────────
api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# ── Google Sheets connection ───────────────────────────────────────────────
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

# ── Actual function that fetches student data from sheets ──────────────────
# This runs ONLY when AI decides to call the tool
def fetch_student_data(student_id):
    try:
        spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID") or st.secrets.get("GOOGLE_SPREADSHEET_ID")
        gc = get_google_sheet_client()
        spreadsheet = gc.open_by_key(spreadsheet_id)

        # Read all four sheets
        roster        = spreadsheet.worksheet("roster").get_all_records()
        exam_scores   = spreadsheet.worksheet("exam_scores").get_all_records()
        attendance    = spreadsheet.worksheet("attendance").get_all_records()
        exam_schedule = spreadsheet.worksheet("exam_schedule").get_all_records()

        # Filter to only this student's rows
        scores = [r for r in exam_scores   if r["student_id"] == student_id]
        attend = [r for r in attendance    if r["student_id"] == student_id]
        exams  = [r for r in exam_schedule if r["student_id"] == student_id]
        info   = next((r for r in roster   if r["student_id"] == student_id), {})

        # If no data found for this student return a clear message
        # AI will read this and tell the student accordingly
        if not scores and not attend and not exams:
            return "No academic data found for this student in the system."

        # Build plain text result that AI will read and use in its response
        result = f"""
STUDENT PROFILE:
Name: {info.get('name', 'Unknown')}
Program: {info.get('program', 'Unknown')}
Cohort: {info.get('cohort', 'Unknown')}

EXAM SCORES:
{chr(10).join([f"- {r['subject']}: {r['score']}/{r['max_score']} on {r['date']}" for r in scores]) or "No scores available"}

ATTENDANCE (recent weeks):
{chr(10).join([f"- Week of {r['week_of']}: {r['attendance_pct']}% ({r['classes_attended']}/{r['classes_scheduled']} classes)" for r in attend]) or "No attendance data available"}

UPCOMING EXAMS:
{chr(10).join([f"- {r['subject']} on {r['exam_date']} ({r['exam_type']})" for r in exams]) or "No upcoming exams found"}
"""
        return result

    except Exception as e:
        # If sheets connection fails AI will know and tell the student
        return f"Could not retrieve student data at this time: {str(e)}"

# ── Tool definition — this is what we tell OpenAI the tool does ───────────
# OpenAI reads this description and decides when to call it
tools = [
    {
        "type": "function",
        "function": {
            "name": "fetch_student_data",
            "description": """Fetches the student's academic data from the database.
            Call this tool when the student asks about:
            - Their exam scores or marks in any subject
            - Their attendance percentage or classes missed
            - Their upcoming exams or exam schedule
            - Their academic performance or progress
            - Anything related to their personal academic records
            - Any question that requires knowing their specific data
            Do NOT call this for general academic questions that don't need personal data.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "The unique student ID to fetch data for"
                    }
                },
                "required": ["student_id"]
            }
        }
    }
]

# ── System prompt ──────────────────────────────────────────────────────────
def build_system_prompt(student_name, student_id):
    # Notice we no longer inject data here directly
    # AI will call the tool itself when it needs data
    return f"""You are an academic success coach AI assistant for {student_name}.
Their student ID is {student_id}.

Your job is to:
- Help students understand their academic performance
- Answer general academic and educational questions
- Explain concepts, subjects, and course material
- Help with exam preparation and study plans
- Support students facing academic challenges
- Help students improve learning habits and performance

When you need the student's personal academic data (scores, attendance, exams), 
use the fetch_student_data tool with student_id: {student_id}

When answering with student data:
- Highlight anything that needs attention — a score below 50, attendance below 75%, or an exam coming up within 7 days
- Be supportive, empathetic, and constructive

You may answer questions related to:
- Academic concepts and subject explanations
- General educational questions
- Study strategies and exam preparation
- Course content and assignments
- Student performance, scores, attendance, and progress
- Academic stress, motivation, and learning difficulties
- Financial or family concerns affecting studies

You must refuse questions related to:
- Entertainment, sports, politics, news, celebrity gossip

If a question is outside your scope, respond with exactly:
"I'm here to support your academic journey and educational success. That topic is outside my scope. Feel free to ask me about your studies, learning goals, academic progress, or challenges affecting your education."

Never answer off-topic questions even if the student insists."""

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Success Coach AI", page_icon="🎓")
st.title("🎓 Success Coach AI")
st.caption("Student View")

# ── Load only roster for dropdown — lightweight, just names and IDs ────────
# We still need names for the dropdown but nothing else upfront
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

# ── Chat history key per student ───────────────────────────────────────────
chat_key = f"messages_{selected_student['student_id']}"

if chat_key not in st.session_state:
    st.session_state[chat_key] = []

# ── End Session button ─────────────────────────────────────────────────────
if st.session_state[chat_key]:
    if st.button("End Session"):
        st.session_state[chat_key] = []
        st.rerun()

# ── Display existing chat messages ─────────────────────────────────────────
for message in st.session_state[chat_key]:
    # Tool/system messages are internal
    if message["role"] in ("tool", "system"):
        continue

    # Skip assistant tool-call messages that have content=None
    if message.get("content") is None:
        continue

    with st.chat_message(message["role"]):
        st.write(message["content"])

# ── Chat input ─────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask me about your academics...")

if user_input:
    st.session_state[chat_key].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            system_prompt = build_system_prompt(
                selected_student["name"],
                selected_student["student_id"]
            )

            # First call — AI either replies directly OR decides to call the tool
            response = client.chat.completions.create(
                model="gpt-5.4-mini-2026-03-17",
                messages=[
                    {"role": "system", "content": system_prompt},
                    *st.session_state[chat_key]
                ],
                tools=tools,
                tool_choice="auto",       # AI decides on its own whether to use tool
                max_completion_tokens=500
            )

            message = response.choices[0].message

            # ── Check if AI wants to call the tool ────────────────────────
            if message.tool_calls:
                # AI decided to fetch student data
                tool_call = message.tool_calls[0]

                # Actually run the function and get the data
                tool_result = fetch_student_data(
                    selected_student["student_id"]
                )

                # Add AI's tool call decision to history
                st.session_state[chat_key].append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        }
                    ]
                })

                # Add tool result to history so AI can read it
                st.session_state[chat_key].append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

                # Second call — now AI has the data, generates final response
                second_response = client.chat.completions.create(
                    model="gpt-5.4-mini-2026-03-17",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        *st.session_state[chat_key]
                    ],
                    max_completion_tokens=500
                )
                reply = second_response.choices[0].message.content

            else:
                # AI answered directly without needing the tool
                reply = message.content

        st.write(reply)

    st.session_state[chat_key].append({"role": "assistant", "content": reply})
    st.rerun()
# app.py
# Step 1 updated:
# - Dropdown now shows "Name (ID)" to handle duplicate names safely
# - End Session button clears the current student's chat history

import streamlit as st
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
import os

# ── Load API key from .env ─────────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    api_key = st.secrets["OPENAI_API_KEY"]

client = OpenAI(api_key=api_key)

# ── Load students from Excel ───────────────────────────────────────────────
@st.cache_data
def load_students():
    df = pd.read_excel("data/Success_Coach_AI_Data.xlsx", sheet_name="roster")
    return df[["student_id", "name"]].to_dict("records")

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Success Coach AI", page_icon="🎓")
st.title("🎓 Success Coach AI")
st.caption("Student View")

# ── Student selector ───────────────────────────────────────────────────────
students = load_students()

# Build a dict like {"Arjun Kumar (STU001)": {"student_id":..., "name":...}}
# Key is unique even if two students share the same name
student_options = {
    f"{s['name']} ({s['student_id']})": s
    for s in students
}

selected_label = st.selectbox("Select your name to begin", list(student_options.keys()))
selected_student = student_options[selected_label]  # full student dict

st.write(f"Welcome, **{selected_student['name']}**")

st.divider()

# ── Chat history key per student ───────────────────────────────────────────
# Each student gets their own list in session_state
# So switching students never mixes up chat histories
chat_key = f"messages_{selected_student['student_id']}"

if chat_key not in st.session_state:
    st.session_state[chat_key] = []

# ── End Session button ─────────────────────────────────────────────────────
# Placed before the chat so it appears at the top
# Only shows if there are messages — no point ending an empty session
if st.session_state[chat_key]:
    if st.button("End Session"):
        # Clear this student's chat history from session_state
        st.session_state[chat_key] = []
        # st.rerun() forces Streamlit to rerun immediately
        # so the chat disappears right away without waiting for next action
        st.rerun()

# ── Display existing chat messages ────────────────────────────────────────
for message in st.session_state[chat_key]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ── Chat input ────────────────────────────────────────────────────────────
user_input = st.chat_input("Type your message here...")

if user_input:
    # Add user message to history
    st.session_state[chat_key].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # Send full history to OpenAI and get reply
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = client.chat.completions.create(
                model="gpt-5.4-mini-2026-03-17",
                messages=st.session_state[chat_key],
                max_completion_tokens=500
            )
            reply = response.choices[0].message.content
        st.write(reply)

    # Add assistant reply to history
    st.session_state[chat_key].append({"role": "assistant", "content": reply})
# agent.py
# Fix: replaced functools.partial with a closure function
# Closure = inner function that remembers variables from outer function
# This gives the function a proper __name__ which @tool requires

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langgraph.prebuilt import create_react_agent
from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import os
import json

# ── LLM ───────────────────────────────────────────────────────────────────
def get_llm():
    return ChatOpenAI(
        model="gpt-5.4-mini-2026-03-17",
        api_key=os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY"),
        temperature=0,
        max_tokens=500
    )

# ── Load RAG vector store ──────────────────────────────────────────────────

def load_vectorstore():
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
    )
    return Chroma(
        persist_directory="chroma_db",
        embedding_function=embeddings
    )

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

# ── RAG tool — stays as normal @tool since query comes from AI ─────────────
@tool
def search_platform_guide(query: str) -> str:
    """Searches the learning platform documentation to answer questions about platform features.
    Call this tool when the student asks about:
    - How to login to the learning portal
    - How to navigate the platform or find features
    - What is My Journey or Growth Cycles
    - How the Home Page works
    - How to use Search on the platform
    - Bonus Courses and how to access them
    - LastMinute Pro and placement preparation
    - Bookmarks feature
    - Any how-to or what-is question about the learning platform
    Do NOT call this for personal data questions or general academic concept questions."""

    try:
        vectorstore = load_vectorstore()
        print("=" * 50)
        print("RAG TOOL CALLED")
        print("QUERY:", query)
        print("=" * 50)
        results = vectorstore.similarity_search(query, k=3)

        if not results:
            return "No relevant information found in the platform guide for this question."

        combined = "\n\n---\n\n".join([doc.page_content for doc in results])
        return f"PLATFORM GUIDE INFORMATION:\n\n{combined}"

    except Exception as e:
        return f"Could not search platform guide at this time: {str(e)}"


# ── Build agent ────────────────────────────────────────────────────────────
def build_agent_executor(student_name: str, student_id: str):
    llm = get_llm()

    # ── Closure fix ───────────────────────────────────────────────────────
    # We define fetch_student_data INSIDE build_agent_executor
    # So it automatically remembers student_id from the outer function
    # This is a closure — inner function captures outer function's variable
    # It has a proper __name__ ("fetch_student_data") so @tool works fine
    # AI calls this tool with no parameters — student_id is already captured
    @tool
    def fetch_student_data() -> str:
        """Fetches this student's personal academic data from the database.
        Call this tool when the student asks about:
        - Their exam scores or marks in any subject
        - Their attendance percentage or classes missed
        - Their upcoming exams or exam schedule
        - Their academic performance or progress
        - Anything related to their personal academic records
        Do NOT call this for general academic questions or platform how-to questions.
        No parameters needed — student identity is already known."""

        try:
            spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID") or st.secrets.get("GOOGLE_SPREADSHEET_ID")
            gc = get_google_sheet_client()
            spreadsheet = gc.open_by_key(spreadsheet_id)

            roster        = spreadsheet.worksheet("roster").get_all_records()
            exam_scores   = spreadsheet.worksheet("exam_scores").get_all_records()
            attendance    = spreadsheet.worksheet("attendance").get_all_records()
            exam_schedule = spreadsheet.worksheet("exam_schedule").get_all_records()

            # student_id is captured from outer function — no parameter needed
            scores = [r for r in exam_scores   if r["student_id"] == student_id]
            attend = [r for r in attendance    if r["student_id"] == student_id]
            exams  = [r for r in exam_schedule if r["student_id"] == student_id]
            info   = next((r for r in roster   if r["student_id"] == student_id), {})

            if not scores and not attend and not exams:
                return "No academic data found for this student in the system."

            return f"""
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
        except Exception as e:
            return f"Could not retrieve student data at this time: {str(e)}"

    # ── System prompt ──────────────────────────────────────────────────────
    system_prompt = f"""You are an academic success coach AI assistant for {student_name}.

You have access to two tools:
1. fetch_student_data — call this when student asks about their personal scores, attendance, or exams. No parameters needed.
2. search_platform_guide — call this when student asks how to use the learning platform or about platform features.

For everything else — general academic concepts, study strategies, motivation — answer directly.

When answering with student data:
- Highlight anything needing attention: score below 50, attendance below 75%, exam within 7 days
- Be supportive, empathetic, and constructive
If fetch_student_data returns:
"No academic data found for this student in the system."

respond with exactly:
"I currently do not have that information in the student database."
Do not make up or assume any student records.

When answering from platform guide:
- If the tool returns no relevant information, tell the student honestly:
  "I don't have that specific information about the platform. Please contact your program coordinator."
- Never make up platform information

You may answer:
- Academic concepts and subject explanations
- Study strategies and exam preparation
- Student performance, scores, attendance, progress
- Academic stress, motivation, learning difficulties
- Financial or family concerns affecting studies
- Learning platform features and navigation

You must refuse:
- Entertainment, sports, politics, news, celebrity gossip

If outside scope respond with exactly:
"I'm here to support your academic journey and educational success. That topic is outside my scope. Feel free to ask me about your studies, learning goals, academic progress, or challenges affecting your education."
"""

    return create_react_agent(
        model=llm,
        tools=[fetch_student_data, search_platform_guide],
        prompt=system_prompt
    )
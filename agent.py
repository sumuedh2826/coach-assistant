# agent.py
# LangChain 1.x + LangGraph
# Tools: fetch_student_data (closure), search_platform_guide (RAG)
# Bottom: generate_session_summary, extract_factual_memory for Mem0

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

# ── RAG tool ───────────────────────────────────────────────────────────────
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

    # fetch_student_data is defined inside build_agent_executor
    # so it captures student_id from outer function automatically
    # AI calls this with no parameters — student_id is already locked in
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

    system_prompt = f"""You are an academic success coach AI assistant for {student_name}.

You have access to two tools:
1. fetch_student_data — call this when student asks about their personal scores, attendance, or exams. No parameters needed.
2. search_platform_guide — call this when student asks how to use the learning platform or about platform features.

For everything else — general academic concepts, study strategies, motivation — answer directly.

When answering with student data:
- Highlight anything needing attention: score below 50, attendance below 75%, exam within 7 days
- Be supportive, empathetic, and constructive

If fetch_student_data returns no data respond with:
"I currently do not have that information in the student database."

When answering from platform guide:
- If the tool returns no relevant information tell the student:
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

# ── Generate session summary ───────────────────────────────────────────────
# Called from app.py on End Session
# Saved as session_summary type in Mem0
def generate_session_summary(messages: list, student_name: str) -> str:
    try:
        llm = get_llm()

        transcript = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
            if msg.get("content")
        ])

        prompt = f"""You are summarising a coaching session for {student_name}.

Transcript:
{transcript}
Write 3-5 bullet points covering ONLY what was actually discussed in this session:

Questions or concerns raised by the student
Academic topics discussed
Personal academic information reviewed (scores, attendance, upcoming exams, deadlines, payment issues, etc.)
Any action items or next steps agreed upon
Overall student mood and engagement during the conversation

Focus on what happened in this specific session.

Do NOT include:

Stress triggers
Learning style
Long-term personality traits
Goals unless explicitly discussed in this session
Assumptions, interpretations, or guesses
Anything not clearly mentioned in the conversation

If an upcoming exam, attendance issue, low score, payment issue, or other urgent academic matter was discussed, include it.

If nothing meaningful was discussed, write exactly:
NO_SUMMARY

Write in third person using the student's name.

Example:

Priya Sharma asked about her upcoming exams and reviewed the exam schedule.
Priya Sharma discussed strategies for preparing for the System Design exam.
A revision plan for the next week was suggested.
Priya Sharma appeared engaged and motivated throughout the discussion. """

        result = llm.invoke([HumanMessage(content=prompt)])
        return result.content.strip()

    except Exception as e:
        print(f"Summary generation error: {e}")
        return "NO_SUMMARY"


# ── Extract factual memory ─────────────────────────────────────────────────
# Called from app.py on End Session
# Saved as factual_memory type in Mem0
# Used next version for urgency signals
def extract_factual_memory(messages: list, student_name: str) -> str:
    try:
        llm = get_llm()

        transcript = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
            if msg.get("content")
        ])

        prompt = f"""You are extracting persistent facts about {student_name} from a coaching session.

Transcript:
{transcript}

Extract ONLY persistent or important facts explicitly mentioned in the conversation.

Do NOT guess, infer, interpret, or assume anything that was not clearly stated by the student.

Do NOT create facts simply to fill categories.

If a category was not discussed, omit that category completely.

Only extract information that was directly mentioned during the conversation.

Prioritise:

* Stress, anxiety, worries, or emotional concerns
* Academic challenges or learning difficulties
* Upcoming exams within 7 days that the student is concerned about
* Attendance issues
* Low scores or academic performance concerns
* Payment, refund, financial, or subscription issues
* Concerns about leaving, dropping, or continuing the platform/program
* Personal circumstances affecting academic progress

Categories to extract if present:

STRESS TRIGGER: Situations that cause stress, anxiety, pressure, or worry.

PROBLEM: Academic, attendance, financial, payment/refund, platform-related, or personal challenges affecting progress.

PERSONAL CONTEXT: Job, family, finances, health, schedule constraints, or other circumstances affecting studies.

GOAL: What the student wants to achieve academically or professionally.

Rules:

* One fact per line.
* Start every line with the category label.
* Only include categories that were explicitly discussed.
* If only one category was discussed, output only that category.
* Never generate placeholder facts.
* Never infer emotions, goals, or problems from simple questions.
* Exam dates should only be extracted if the student expressed concern, urgency, pressure, confusion, or preparation challenges related to the exam.

Example output:

STRESS TRIGGER: Priya Sharma is anxious about an upcoming System Design exam scheduled within the next week.

PROBLEM: Priya Sharma is struggling with Data Structures and finds recursion difficult.

GOAL: Priya Sharma wants to secure a software engineering placement.

If no meaningful factual memory was explicitly discussed, write exactly:

NO_FACTUAL_CONTENT
"""

        result = llm.invoke([HumanMessage(content=prompt)])
        return result.content.strip()

    except Exception as e:
        print(f"Factual memory extraction error: {e}")
        return "NO_FACTUAL_CONTENT"
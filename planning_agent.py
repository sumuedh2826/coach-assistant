# planning_agent.py
# M7 — Planning Agent
# Takes today's sessions and generates a structured day plan for the coach
# Coach works: 9-10 prep, 10-11 meet, 11-12 prep, 12-1 meet, 1-2 lunch, 2-3 review, 3-4 prep, 4-5 meet
# Max 3 student meetings per day
# Priority: high signal first, then medium, then no signal if slot available

# planning_agent.py
# Separate LLM with higher token limit for plan generation
# 500 tokens is not enough for full JSON schedule — increased to 2000

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from agent import get_llm
import json
import os
import streamlit as st

# ── Higher token LLM just for planning ────────────────────────────────────
# Planning generates a full JSON schedule which needs more tokens
# Regular get_llm() uses 500 which causes unterminated JSON
def get_planning_llm():
    return ChatOpenAI(
        model="gpt-5.4-mini-2026-03-17",
        api_key=os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY"),
        temperature=0,
        max_completion_tokens=2000
    )

# Coach schedule — fixed slots
COACH_SCHEDULE = {
    "slot_1": {"prep": "9:00 AM - 10:00 AM", "meet": "10:00 AM - 11:00 AM"},
    "slot_2": {"prep": "11:00 AM - 12:00 PM", "meet": "12:00 PM - 1:00 PM"},
    "lunch":  "1:00 PM - 2:00 PM",
    "review": "2:00 PM - 3:00 PM",
    "slot_3": {"prep": "3:00 PM - 4:00 PM",  "meet": "4:00 PM - 5:00 PM"},
}

def run_planning_agent(todays_sessions: list) -> dict:
    """
    Takes list of today's student sessions with their signals
    Returns a structured day plan for the coach
    """
    llm = get_planning_llm()

    # Case: no students talked today
    if not todays_sessions:
        prompt = f"""You are a planning agent for a student success coach.

No students had sessions with the AI assistant today.

Generate a productive default day plan for the coach using this fixed schedule:
- 9:00 AM - 10:00 AM: Morning preparation
- 10:00 AM - 11:00 AM: Free slot
- 11:00 AM - 12:00 PM: Preparation time
- 12:00 PM - 1:00 PM: Free slot
- 1:00 PM - 2:00 PM: Lunch break
- 2:00 PM - 3:00 PM: Student progress review
- 3:00 PM - 4:00 PM: Preparation time
- 4:00 PM - 5:00 PM: Free slot

Fill the free slots and preparation times with useful coaching tasks like:
- Reviewing student progress reports
- Following up on previous session action items
- Preparing coaching materials
- Updating student records
- Planning upcoming sessions

Respond ONLY in this exact JSON format:
{{
  "plan_type": "default",
  "summary": "One sentence describing today since no students had sessions",
  "schedule": [
    {{"time": "9:00 AM - 10:00 AM", "activity": "task name", "detail": "what to do"}},
    {{"time": "10:00 AM - 11:00 AM", "activity": "task name", "detail": "what to do"}},
    {{"time": "11:00 AM - 12:00 PM", "activity": "task name", "detail": "what to do"}},
    {{"time": "12:00 PM - 1:00 PM", "activity": "task name", "detail": "what to do"}},
    {{"time": "1:00 PM - 2:00 PM", "activity": "Lunch Break", "detail": ""}},
    {{"time": "2:00 PM - 3:00 PM", "activity": "task name", "detail": "what to do"}},
    {{"time": "3:00 PM - 4:00 PM", "activity": "task name", "detail": "what to do"}},
    {{"time": "4:00 PM - 5:00 PM", "activity": "task name", "detail": "what to do"}}
  ],
  "deferred": []
}}"""

    else:
        # Format student list for the prompt
        students_text = ""
        for i, s in enumerate(todays_sessions, 1):
            severity = s.get("severity") or "no signal"
            students_text += f"""
Student {i}: {s['student_name']}
- Session time: {s['time']}
- Signal: {severity.upper()}
- Summary: {s.get('signal_summary') or 'No urgent concerns'}
- Reason: {s.get('reason') or ''}
"""

        prompt = f"""You are a planning agent for a student success coach.

Today the following students had sessions with the AI assistant:
{students_text}

The coach has exactly 3 meeting slots today:
- Slot 1: Prep 9:00 AM - 10:00 AM, Meeting 10:00 AM - 11:00 AM
- Slot 2: Prep 11:00 AM - 12:00 PM, Meeting 12:00 PM - 1:00 PM
- Lunch: 1:00 PM - 2:00 PM (fixed, cannot be changed)
- Review: 2:00 PM - 3:00 PM (coach reviews student details, no meetings)
- Slot 3: Prep 3:00 PM - 4:00 PM, Meeting 4:00 PM - 5:00 PM

RULES for assigning students to slots:
1. HIGH signal students must be assigned first — they take priority
2. MEDIUM signal students fill remaining slots
3. Students with no signal only get a slot if one is still free after high and medium are placed
4. If more than 3 students need meetings, defer the lowest priority ones to tomorrow
5. Deferred students must have a clear reason why they could not be fit in today

For each meeting slot include:
- Which student is meeting the coach
- Session type: "Urgent Check-in" for high signal, "Progress Review" for medium, "General Check-in" for no signal
- Plain reason why this student is meeting today

For prep slots before each meeting write what the coach should prepare based on the student's signal summary.

Respond ONLY in this exact JSON format with no extra text:
{{
  "plan_type": "student_sessions",
  "summary": "One sentence describing today's coaching focus",
  "schedule": [
    {{"time": "9:00 AM - 10:00 AM", "activity": "Preparation", "detail": "what to prepare for the 10am meeting"}},
    {{"time": "10:00 AM - 11:00 AM", "activity": "Meeting — Student Name", "detail": "session type and reason"}},
    {{"time": "11:00 AM - 12:00 PM", "activity": "Preparation", "detail": "what to prepare for the 12pm meeting"}},
    {{"time": "12:00 PM - 1:00 PM", "activity": "Meeting — Student Name", "detail": "session type and reason"}},
    {{"time": "1:00 PM - 2:00 PM", "activity": "Lunch Break", "detail": ""}},
    {{"time": "2:00 PM - 3:00 PM", "activity": "Student Progress Review", "detail": "review session notes and signals"}},
    {{"time": "3:00 PM - 4:00 PM", "activity": "Preparation", "detail": "what to prepare for the 4pm meeting"}},
    {{"time": "4:00 PM - 5:00 PM", "activity": "Meeting — Student Name", "detail": "session type and reason"}}
  ],
  "deferred": [
    {{"student_name": "name", "reason": "why deferred to tomorrow"}}
  ]
}}"""

    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        raw = result.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)

    except Exception as e:
        print(f"Planning agent error: {e}")
        return {
            "plan_type": "error",
            "summary": "Plan could not be generated. Please try again.",
            "schedule": [],
            "deferred": []
        }
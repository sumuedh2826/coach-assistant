# flagging_agent.py
# M6 — Flagging Agent
# Two signals only: high or medium
# HIGH — must meet coach today, will trigger rescheduling in future
# MEDIUM — meet today if slot available, otherwise tomorrow

from langchain_core.messages import HumanMessage
from agent import get_llm
import json

def run_flagging_agent(student_name: str, student_id: str, factual_memory: str) -> dict:
    """
    Takes factual memory extracted after a session
    Returns signal with severity (high/medium) and reason
    Returns None signal if nothing concerning found
    """

    # If no factual memory nothing to flag
    if not factual_memory or factual_memory.strip() == "NO_FACTUAL_CONTENT":
        return {
            "student_id":     student_id,
            "student_name":   student_name,
            "severity":       None,
            "reason":         "No concerning signals found in this session.",
            "signal_summary": "Session had no flaggable content."
        }

    llm = get_llm()

    prompt = f"""You are a flagging agent for a student success coaching system.

Your job is to read factual memory from a student session and decide if the coach needs to be alerted.

Student: {student_name}
Student ID: {student_id}

FACTUAL MEMORY:
{factual_memory}

Decide if this student needs a HIGH or MEDIUM signal, or no signal at all.

HIGH — coach must meet this student today, rescheduling will happen if needed:
- Payment issues, fee problems, or financial stress affecting continuation
- Student mentioned wanting to leave, drop out, or quit the program
- Severe stress, anxiety, burnout, or mental health concerns
- Student said they are not feeling well emotionally or physically
- Complete loss of motivation or confidence
- Family crisis directly impacting studies
- student is stressed or feeling unprepared abt exams or anything
- Attendance critically low below 60 percent

MEDIUM — meet today if coach has a free slot, otherwise tomorrow:
- Consistently struggling in one or more subjects
- Low scores or failing grades
- Moderate exam anxiety
- Attendance declining but above 60 percent
- Missing deadlines repeatedly
- Confusion about career path or course direction
- Motivation declining gradually

NO SIGNAL — if only general facts were found:
- Only learning style or goals mentioned
- Student seemed fine with no problems
- Nothing concerning was shared

Respond ONLY in this exact JSON format with no extra text outside the JSON:
{{
  "severity": "high" or "medium" or null,
  "reason": "One clear sentence explaining why this signal was assigned, or why no signal was needed.",
  "signal_summary": "Two to three sentences summarising what the coach needs to know. Leave empty string if no signal."
}}"""

    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        raw = result.content.strip()

        # Remove markdown code block if AI wrapped response in it
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        signal = json.loads(raw)
        signal["student_id"]   = student_id
        signal["student_name"] = student_name
        return signal

    except Exception as e:
        print(f"Flagging agent error: {e}")
        return {
            "student_id":     student_id,
            "student_name":   student_name,
            "severity":       None,
            "reason":         "Signal could not be generated due to an error.",
            "signal_summary": ""
        }
# memory.py
# mem0ai 2.0.7 compatible
# Key fix: use get_all() instead of search() for signals and session logs
# Mem0 fragments complex content — we now store simple plain text
# and filter by metadata.type in Python after fetching all

from mem0 import MemoryClient
import os
from dotenv import load_dotenv
load_dotenv()

def get_mem0_client():
    api_key = os.getenv("MEM0_API_KEY")
    return MemoryClient(api_key=api_key)

# ── Internal helper — get ALL memories for a user filtered by type ─────────
# Uses get_all() instead of search() — more reliable, no semantic matching
# Filters by metadata.type in Python after fetching
def _get_all_by_type(client, student_id: str, memory_type: str) -> list:
    try:
        results = client.get_all(
            filters={"user_id": student_id},
            limit=100
        )
        if isinstance(results, dict):
            results = results.get("results", [])

        # Filter by metadata type in Python
        return [
            m for m in results
            if isinstance(m, dict)
            and m.get("metadata", {}).get("type") == memory_type
        ]
    except Exception as e:
        print(f"get_all error for {memory_type}: {e}")
        return []

# ── Save session summary ───────────────────────────────────────────────────
def save_session_summary(student_id: str, summary: str) -> bool:
    try:
        client = get_mem0_client()
        client.add(
            messages=[{"role": "user", "content": summary}],
            user_id=student_id,
            metadata={"type": "session_summary"}
        )
        return True
    except Exception as e:
        print(f"Session summary save error: {e}")
        return False

# ── Save factual memory ────────────────────────────────────────────────────
def save_factual_memory(student_id: str, factual_text: str) -> bool:
    try:
        client = get_mem0_client()
        client.add(
            messages=[{"role": "user", "content": factual_text}],
            user_id=student_id,
            metadata={"type": "factual_memory"}
        )
        return True
    except Exception as e:
        print(f"Factual memory save error: {e}")
        return False

# ── Old search based fetch — kept for factual and summary only ─────────────
def _fetch_by_type(client, query: str, student_id: str, memory_type: str, limit: int) -> list:
    try:
        results = client.search(
            query=query,
            filters={
                "user_id": student_id,
                "metadata": {"type": memory_type}
            },
            limit=limit
        )
        if isinstance(results, dict):
            results = results.get("results", [])
        return results if results else []
    except Exception:
        try:
            results = client.search(
                query=query,
                filters={"user_id": student_id},
                limit=limit * 3
            )
            if isinstance(results, dict):
                results = results.get("results", [])
            return [
                m for m in results
                if isinstance(m, dict)
                and m.get("metadata", {}).get("type") == memory_type
            ]
        except Exception as e:
            print(f"Memory fetch fallback error for {memory_type}: {e}")
            return []

# ── Fetch factual memory ───────────────────────────────────────────────────
def get_factual_memory(student_id: str) -> str:
    try:
        client = get_mem0_client()
        results = _fetch_by_type(
            client=client,
            query="student stress triggers problems learning patterns personal facts",
            student_id=student_id,
            memory_type="factual_memory",
            limit=10
        )
        if not results:
            return ""
        facts = "\n".join([
            f"- {m['memory']}"
            for m in results
            if isinstance(m, dict) and "memory" in m
        ])
        return f"FACTUAL MEMORY ABOUT THIS STUDENT:\n{facts}" if facts else ""
    except Exception as e:
        print(f"Get factual memory error: {e}")
        return ""

# ── Fetch session summaries ────────────────────────────────────────────────
def get_session_summaries(student_id: str) -> str:
    try:
        client = get_mem0_client()
        results = _fetch_by_type(
            client=client,
            query="session summary what was discussed coaching decisions",
            student_id=student_id,
            memory_type="session_summary",
            limit=5
        )
        if not results:
            return ""
        summaries = "\n".join([
            f"- {m['memory']}"
            for m in results
            if isinstance(m, dict) and "memory" in m
        ])
        return f"PAST SESSION SUMMARIES:\n{summaries}" if summaries else ""
    except Exception as e:
        print(f"Get session summaries error: {e}")
        return ""

# ── Fetch all memory combined for AI context ───────────────────────────────
def get_all_student_memory(student_id: str) -> str:
    factual   = get_factual_memory(student_id)
    summaries = get_session_summaries(student_id)
    return "\n\n".join(filter(None, [factual, summaries]))

# ── Save signal ────────────────────────────────────────────────────────────
# Store as simple plain text so Mem0 does not fragment it
# All key info stored in metadata — we read from metadata not memory text
def save_signal(student_id: str, signal: dict) -> bool:
    try:
        from datetime import datetime
        import pytz
        tz   = pytz.timezone("Asia/Kolkata")
        now  = datetime.now(tz)
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M")

        client = get_mem0_client()
        severity = str(signal.get("severity") or "none")

        # Simple short content — Mem0 is less likely to fragment short text
        content = f"Coach signal for {signal.get('student_name', '')} on {date}: severity {severity}"

        client.add(
            messages=[{"role": "user", "content": content}],
            user_id=student_id,
            metadata={
                "type":           "signal",
                "severity":       severity,
                "reason":         signal.get("reason", ""),
                "signal_summary": signal.get("signal_summary", ""),
                "student_name":   signal.get("student_name", ""),
                "date":           date,
                "time":           time
            }
        )
        return True
    except Exception as e:
        print(f"Signal save error: {e}")
        return False

# ── Save session log ───────────────────────────────────────────────────────
# Simple short content so Mem0 does not fragment
# Date and time stored in metadata — read from there not memory text
def save_session_log(student_id: str, student_name: str) -> bool:
    try:
        from datetime import datetime
        import pytz
        tz   = pytz.timezone("Asia/Kolkata")
        now  = datetime.now(tz)
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M")

        client = get_mem0_client()

        # Very short content — just enough for Mem0 to store as one memory
        content = f"{student_name} session ended {date}"

        client.add(
            messages=[{"role": "user", "content": content}],
            user_id=student_id,
            metadata={
                "type":         "session_log",
                "date":         date,
                "time":         time,
                "student_name": student_name
            }
        )
        return True
    except Exception as e:
        print(f"Session log save error: {e}")
        return False

# ── Fetch latest signal using get_all ─────────────────────────────────────
# Uses get_all and filters in Python — reliable, no semantic search issues
# for_date filters to signals from today only
def get_latest_signal(student_id: str, for_date: str = None) -> dict:
    try:
        client = get_mem0_client()
        results = _get_all_by_type(client, student_id, "signal")

        if not results:
            return {}

        # Filter by date if provided
        if for_date:
            results = [
                m for m in results
                if m.get("metadata", {}).get("date") == for_date
            ]

        if not results:
            return {}

        # Sort by created_at descending — latest signal first
        results.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )

        # Read signal data from metadata — not from memory text
        # because Mem0 may have rewritten the memory text
        meta = results[0].get("metadata", {})
        severity = meta.get("severity", "none")

        return {
            "severity":       None if severity == "none" else severity,
            "reason":         meta.get("reason", ""),
            "signal_summary": meta.get("signal_summary", ""),
            "student_name":   meta.get("student_name", ""),
            "date":           meta.get("date", "")
        }

    except Exception as e:
        print(f"Get signal error: {e}")
        return {}

# ── Fetch today's sessions using get_all ──────────────────────────────────
# Uses get_all and filters in Python — reliable, no semantic search issues
# Takes latest session per student if multiple sessions today
def get_todays_sessions(student_ids: list) -> list:
    try:
        from datetime import datetime
        import pytz
        tz    = pytz.timezone("Asia/Kolkata")
        today = datetime.now(tz).strftime("%Y-%m-%d")
        client = get_mem0_client()

        todays_sessions = []

        for student_id in student_ids:
            # Get all session logs for this student
            results = _get_all_by_type(client, student_id, "session_log")

            if not results:
                continue

            # Filter to only today's logs
            todays = [
                m for m in results
                if m.get("metadata", {}).get("date") == today
            ]

            if not todays:
                continue

            # Sort by time descending — take latest session today
            todays.sort(
                key=lambda x: x.get("metadata", {}).get("time", ""),
                reverse=True
            )

            latest   = todays[0]
            metadata = latest.get("metadata", {})

            # Get signal for today
            signal = get_latest_signal(student_id, for_date=today)

            todays_sessions.append({
                "student_id":     student_id,
                "student_name":   metadata.get("student_name", student_id),
                "time":           metadata.get("time", ""),
                "severity":       signal.get("severity", None),
                "signal_summary": signal.get("signal_summary", ""),
                "reason":         signal.get("reason", "")
            })

        # Sort by priority: high first, medium second, no signal last
        severity_order = {"high": 0, "medium": 1, None: 2}
        todays_sessions.sort(
            key=lambda x: severity_order.get(x["severity"], 2)
        )

        return todays_sessions

    except Exception as e:
        print(f"Get today sessions error: {e}")
        return []
# memory.py
# mem0ai 2.0.7 compatible
# save: user_id as direct param, metadata as dict
# search: user_id inside filters dict
# type filter: filters={"user_id": ..., "metadata": {"type": ...}}
# fallback: fetch all and filter in Python if metadata filter not supported

from mem0 import MemoryClient
import os
from dotenv import load_dotenv
load_dotenv()

def get_mem0_client():
    api_key = os.getenv("MEM0_API_KEY")
    return MemoryClient(api_key=api_key)

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

# ── Internal helper — fetch by type with fallback ─────────────────────────
# Tries metadata filter first — correct for mem0ai 2.0.7
# Falls back to fetching all and filtering in Python if filter not supported
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
        # Fallback — fetch all for this user and filter in Python
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
# Called before every AI response
# AI reads this to personalise responses from first message
def get_all_student_memory(student_id: str) -> str:
    factual   = get_factual_memory(student_id)
    summaries = get_session_summaries(student_id)
    return "\n\n".join(filter(None, [factual, summaries]))
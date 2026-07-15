"""
main.py
-------
FastAPI app. Exposes:

  GET  /api/hcps?q=...          search the HCP directory (form autocomplete)
  GET  /api/interactions        list all logged interactions
  GET  /api/interactions/{id}   fetch one interaction
  POST /api/interactions        create one directly from the form's "Log" button
  PUT  /api/interactions/{id}   edit one directly from the form
  POST /api/chat                talk to the LangGraph agent (AI Assistant panel)

Run with:  uvicorn main:app --reload --port 8000
"""
import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

import storage
from agent import get_agent_graph

app = FastAPI(title="HCP Interaction Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo app: wide open. Lock this down in production.
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------- models --
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class InteractionIn(BaseModel):
    hcp_name: str = ""
    interaction_type: str = "Meeting"
    date: str = ""
    time: str = ""
    attendees: str = ""
    topics_discussed: str = ""
    materials_shared: List[str] = []
    samples_distributed: List[str] = []
    sentiment: str = "Neutral"
    outcomes: str = ""
    follow_up_actions: List[str] = []


# ----------------------------------------------------------------- HCPs --
@app.get("/api/hcps")
def get_hcps(q: str = ""):
    return {"hcps": storage.search_hcps(q)}


@app.post("/api/hcps")
def post_hcp(name: str, specialty: Optional[str] = None):
    return storage.add_hcp(name, specialty)


# --------------------------------------------------------- interactions --
@app.get("/api/interactions")
def get_interactions():
    return {"interactions": storage.list_interactions()}


@app.get("/api/interactions/{interaction_id}")
def get_interaction(interaction_id: int):
    record = storage.get_interaction(interaction_id)
    if record is None:
        raise HTTPException(404, "Interaction not found")
    return record


@app.post("/api/interactions")
def post_interaction(payload: InteractionIn):
    if payload.hcp_name:
        storage.add_hcp(payload.hcp_name)
    fields = payload.model_dump()
    fields["source"] = "manual"
    return storage.create_interaction(fields)


@app.put("/api/interactions/{interaction_id}")
def put_interaction(interaction_id: int, updates: Dict[str, Any]):
    record = storage.update_interaction(interaction_id, updates)
    if record is None:
        raise HTTPException(404, "Interaction not found")
    return record


# --------------------------------------------------------------- agent --
def _to_lc_messages(req: ChatRequest):
    messages = []
    for m in req.history:
        if m.role == "user":
            messages.append(HumanMessage(content=m.content))
        else:
            messages.append(AIMessage(content=m.content))
    messages.append(HumanMessage(content=req.message))
    return messages


@app.post("/api/chat")
def chat(req: ChatRequest):
    initial_state = {"messages": _to_lc_messages(req)}
    final_state = get_agent_graph().invoke(initial_state)
    messages = final_state["messages"]

    # The last message is the agent's final reply to the rep.
    reply = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            reply = m.content
            break

    # Collect a human-readable log of every tool call made this turn, and
    # pick out the latest logged/updated interaction so the frontend can
    # patch the form fields to match what the agent just did.
    tool_calls_summary = []
    form_update = None
    for m in messages:
        if isinstance(m, ToolMessage):
            try:
                payload = json.loads(m.content)
            except (json.JSONDecodeError, TypeError):
                payload = {"raw": m.content}
            tool_calls_summary.append({"tool": m.name, "result": payload})
            if isinstance(payload, dict) and "interaction" in payload:
                form_update = payload["interaction"]

    return {
        "reply": reply,
        "tool_calls": tool_calls_summary,
        "form_update": form_update,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash")}

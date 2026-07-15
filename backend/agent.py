"""
agent.py
--------
The LangGraph agent that powers the "AI Assistant" chat panel.

Role of the agent
------------------
It acts as the sales rep's in-app copilot for HCP-interaction management.
Given the running chat history (and the current message), it decides
whether it can just reply conversationally, or whether it needs to call
one of the five tools in tools.py (log_interaction, edit_interaction,
search_or_add_hcp, summarize_voice_note, suggest_followups) to actually
change data or fetch grounded information. It loops between "think" and
"act" (a standard ReAct-style graph) until it has a final answer for
the rep, then returns.

Graph shape:

    START -> agent -> (tool calls?) -> tools -> agent -> ... -> END
                 (no tool calls) -----------------------------> END
"""
import os
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from tools import ALL_TOOLS

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = """You are the AI Assistant embedded in a pharma sales rep's
"Log HCP Interaction" tool. Your job is to help the rep log, edit, and get
suggestions about their interactions with Health Care Professionals (HCPs),
using the tools available to you.

Guidelines:
- If the rep describes something that happened (a meeting, call, etc.),
  call log_interaction with their note in raw_notes.
- If they ask to change something about an interaction already logged,
  call edit_interaction with the interaction_id and the updates.
- If they mention an HCP name and you're unsure it exists, or they ask to
  add one, use search_or_add_hcp.
- If they paste/describe a voice note transcript, use summarize_voice_note
  (and only proceed if they've confirmed consent).
- After logging an interaction, proactively offer to suggest follow-up
  actions using suggest_followups.
- Keep replies short, professional, and specific to what changed.
"""


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _build_graph():
    llm = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    temperature=0.2,
    google_api_key=os.getenv("GEMINI_API_KEY"),
).bind_tools(ALL_TOOLS)
    def agent_node(state: AgentState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")

    return graph.compile()


# Built lazily on first use (not at import time) so the app can still start,
# and other endpoints keep working, even before OPENAI_API_KEY is configured.
_graph_cache = None


def get_agent_graph():
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = _build_graph()
    return _graph_cache

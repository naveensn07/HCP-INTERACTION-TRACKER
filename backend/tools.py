"""
tools.py
--------
Five tools the LangGraph agent can call while helping a pharma sales rep
log and manage HCP (Health Care Professional) interactions.

1. log_interaction      - creates a new interaction record. Uses the LLM to
                           turn a free-text note into structured fields
                           (entity extraction / summarization).
2. edit_interaction     - modifies fields on an already-logged interaction.
3. search_or_add_hcp    - looks up an HCP by name, or registers a new one.
4. summarize_voice_note - summarizes a (consented) voice-note transcript
                           into a "topics discussed" paragraph.
5. suggest_followups    - proposes next-step follow-up actions based on
                           an interaction's content.
"""
import json
import os
from typing import List, Optional

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

import storage

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _extraction_llm():
    # Low temperature: we want reliable structured extraction, not creativity.
    return ChatGoogleGenerativeAI(
        model=MODEL_NAME, temperature=0, google_api_key=os.getenv("GEMINI_API_KEY")
    )


def _chat_llm():
    return ChatGoogleGenerativeAI(
        model=MODEL_NAME, temperature=0.4, google_api_key=os.getenv("GEMINI_API_KEY")
    )


# ---------------------------------------------------------------------- #
# Schema the extraction LLM must fill in when parsing a free-text note.
# ---------------------------------------------------------------------- #
class ExtractedInteraction(BaseModel):
    hcp_name: str = Field(default="", description="Name of the HCP mentioned, e.g. 'Dr. Smith'")
    interaction_type: str = Field(
        default="Meeting", description="One of: Meeting, Call, Email, Conference, Other"
    )
    topics_discussed: str = Field(default="", description="Key discussion points, concise")
    materials_shared: List[str] = Field(default_factory=list, description="Brochures/materials shared")
    samples_distributed: List[str] = Field(default_factory=list, description="Drug samples given")
    sentiment: str = Field(default="Neutral", description="One of: Positive, Neutral, Negative")
    outcomes: str = Field(default="", description="Key outcomes or agreements reached")


@tool
def log_interaction(
    raw_notes: str,
    hcp_name: Optional[str] = None,
    interaction_type: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
    attendees: Optional[str] = None,
) -> str:
    """Log a new HCP interaction.

    Give the rep's free-text note in `raw_notes` (e.g. "Met Dr. Smith,
    discussed Product X efficacy, positive sentiment, shared brochure").
    This tool uses the LLM to extract structured fields (HCP name, topics,
    materials shared, samples distributed, sentiment, outcomes) from the
    note, merges them with any explicit fields you already know
    (hcp_name/interaction_type/date/time/attendees), and saves the
    interaction. Returns the created interaction record as JSON.
    """
    extractor = _extraction_llm().with_structured_output(ExtractedInteraction)
    extracted: ExtractedInteraction = extractor.invoke(
        "Extract structured HCP-interaction details from this sales rep note. "
        f"Note: {raw_notes}"
    )

    fields = extracted.model_dump()
    # Explicit args (if the caller already knows them) win over LLM guesses.
    if hcp_name:
        fields["hcp_name"] = hcp_name
    if interaction_type:
        fields["interaction_type"] = interaction_type
    fields["date"] = date or ""
    fields["time"] = time or ""
    fields["attendees"] = attendees or ""
    fields["source"] = "agent"

    # Make sure the HCP exists in our directory too.
    if fields.get("hcp_name"):
        storage.add_hcp(fields["hcp_name"])

    record = storage.create_interaction(fields)
    return json.dumps({"status": "logged", "interaction": record})


@tool
def edit_interaction(interaction_id: int, updates: dict) -> str:
    """Edit an already-logged HCP interaction.

    `interaction_id` is the numeric id of the interaction to change.
    `updates` is a dict of field -> new value, e.g.
    {"sentiment": "Positive", "outcomes": "Agreed to a follow-up demo"}.
    Valid fields: hcp_name, interaction_type, date, time, attendees,
    topics_discussed, materials_shared, samples_distributed, sentiment,
    outcomes, follow_up_actions.
    Returns the updated record as JSON, or an error if the id doesn't exist.
    """
    record = storage.update_interaction(interaction_id, updates)
    if record is None:
        return json.dumps({"status": "error", "message": f"No interaction with id {interaction_id}"})
    return json.dumps({"status": "updated", "interaction": record})


@tool
def search_or_add_hcp(query: str, add_new: bool = False, specialty: Optional[str] = None) -> str:
    """Search the HCP directory by name, or register a brand-new HCP.

    Set `add_new=True` to create a new HCP named `query` (optionally with
    a `specialty`) if they don't already exist. Otherwise this does a
    case-insensitive substring search and returns all matches as JSON.
    """
    if add_new:
        record = storage.add_hcp(query, specialty)
        return json.dumps({"status": "added", "hcp": record})
    matches = storage.search_hcps(query)
    return json.dumps({"status": "ok", "matches": matches})


@tool
def summarize_voice_note(transcript: str, consent_given: bool) -> str:
    """Summarize a voice-note transcript into a concise 'topics discussed' note.

    `consent_given` MUST be true — per compliance policy this tool refuses
    to process any voice note unless the HCP/rep has given consent for the
    recording to be summarized. Returns a short paragraph summary.
    """
    if not consent_given:
        return json.dumps(
            {
                "status": "refused",
                "message": "Consent required before a voice note can be summarized.",
            }
        )
    llm = _chat_llm()
    result = llm.invoke(
        "Summarize this sales-call voice-note transcript into a short, factual "
        "paragraph suitable for a CRM 'Topics Discussed' field. Do not invent "
        f"details that are not in the transcript.\n\nTranscript:\n{transcript}"
    )
    return json.dumps({"status": "ok", "summary": result.content})


@tool
def suggest_followups(interaction_id: Optional[int] = None, context: Optional[str] = None) -> str:
    """Suggest 2-4 concrete follow-up actions for a rep after an HCP interaction.

    Provide either `interaction_id` (to pull an already-logged interaction's
    topics/outcomes) or raw `context` text. Returns a JSON list of short,
    actionable follow-up suggestions, e.g. "Schedule follow-up meeting in 2
    weeks" or "Send Oncoboost Phase II PDF".
    """
    basis = context or ""
    if interaction_id is not None:
        record = storage.get_interaction(interaction_id)
        if record:
            basis = (
                f"HCP: {record.get('hcp_name')}\n"
                f"Topics: {record.get('topics_discussed')}\n"
                f"Outcomes: {record.get('outcomes')}\n"
                f"Sentiment: {record.get('sentiment')}"
            )
    if not basis:
        return json.dumps({"status": "error", "message": "No interaction_id or context provided"})

    llm = _chat_llm()
    result = llm.invoke(
        "Based on this HCP interaction, suggest 2-4 short, concrete follow-up "
        "actions a pharma sales rep should take next. Return ONLY a JSON array "
        f"of strings, nothing else.\n\n{basis}"
    )
    text = result.content.strip().strip("`")
    try:
        suggestions = json.loads(text)
        if not isinstance(suggestions, list):
            raise ValueError
    except Exception:
        suggestions = [line.strip("-* ") for line in text.splitlines() if line.strip()]

    if interaction_id is not None:
        storage.update_interaction(interaction_id, {"follow_up_actions": suggestions})

    return json.dumps({"status": "ok", "suggestions": suggestions})


ALL_TOOLS = [
    log_interaction,
    edit_interaction,
    search_or_add_hcp,
    summarize_voice_note,
    suggest_followups,
]

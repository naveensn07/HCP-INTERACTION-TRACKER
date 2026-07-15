# Fieldnote — Log HCP Interaction

A small full-stack app for pharma sales reps to log, edit, and get AI help
with their Health Care Professional (HCP) interactions — a "Log HCP
Interaction" form on the left, and an AI Assistant chat panel on the right
that is backed by a **LangGraph** agent (using Google **Gemini**) with five
tools.

```
hcp-interaction-tracker/
├── backend/          FastAPI + LangGraph + OpenAI
│   ├── main.py        REST API
│   ├── agent.py        LangGraph agent graph
│   ├── tools.py         The 5 tools the agent can call
│   ├── storage.py         JSON-file persistence (hcps + interactions)
│   └── requirements.txt
└── frontend/          Plain HTML/CSS/JS, no build step
    ├── index.html
    ├── style.css
    └── script.js
```

## How to run it

### 1. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set your GEMINI_API_KEY (get a free one at
# https://aistudio.google.com/app/apikey)

uvicorn main:app --reload --port 8000
```

The API is now on `http://localhost:8000`. Check `http://localhost:8000/api/health`.

### 2. Frontend

The frontend is plain static files — no build step. Simplest way to serve it:

```bash
cd frontend
python3 -m http.server 5500
```

Then open `http://localhost:5500` in your browser. It talks to the backend
at `http://localhost:8000` by default (see `API_BASE` at the top of
`script.js` if you need to change that).

## The LangGraph agent

**Role.** The agent is the brain behind the "AI Assistant" chat panel. A rep
can type a free-text note like *"Met Dr. Smith, discussed Product X
efficacy, positive sentiment, shared brochure"* and the agent figures out,
turn by turn, whether it should just respond conversationally or call one of
its tools to actually change data (log a new interaction, edit one, look up
or register an HCP, summarize a voice note, or suggest follow-ups). It's a
standard ReAct-style loop:

```
START -> agent (LLM decides) -> tool calls? --yes--> tools -> back to agent
                                      |
                                      no
                                      v
                                     END
```

The `agent` node calls `ChatGoogleGenerativeAI(...).bind_tools(ALL_TOOLS)` with
a system prompt describing its job; the `tools` node (a LangGraph
`ToolNode`)
actually executes whichever tool(s) the model asked for; `tools_condition`
routes back and forth until the model responds with plain text instead of
another tool call. The compiled graph lives in `backend/agent.py`.

The FastAPI `/api/chat` endpoint runs the whole conversation history through
this graph on every turn (LangGraph graphs are stateless between calls in
this setup — state is rebuilt from the chat history sent by the frontend),
and returns:
- `reply` — the agent's final text reply
- `tool_calls` — every tool the agent invoked this turn (shown as little
  `🛠 tool_name` chips in the chat feed, so it's obvious the tool actually
  ran, not just the LLM talking)
- `form_update` — if a `log_interaction`/`edit_interaction` tool ran, the
  resulting record, so the frontend form auto-fills to match

## The five tools (`backend/tools.py`)

1. **`log_interaction`** *(required)* — Takes the rep's free-text note
   (`raw_notes`) plus any fields already known (HCP name, date, time,
   attendees). It uses the LLM with a structured-output schema
   (`ExtractedInteraction`) to do **entity extraction**: pulling out the HCP
   name, interaction type, topics discussed, materials shared, samples
   distributed, sentiment, and outcomes from the free text. Explicit args
   win over LLM guesses. It then saves the record via `storage.py` and
   returns it as JSON.

2. **`edit_interaction`** *(required)* — Takes an `interaction_id` and a
   dict of `field: new_value` updates (e.g. `{"sentiment": "Positive"}`),
   validates the record exists, applies the patch, and returns the updated
   record. Both the chat ("change that last meeting's sentiment to
   positive") and the "Edit" button on each row in the "Logged Interactions"
   list use this same tool/endpoint.

3. **`search_or_add_hcp`** — Case-insensitive substring search over the HCP
   directory (powers the autocomplete under the "HCP Name" field), or,
   with `add_new=True`, registers a brand-new HCP on the fly.

4. **`summarize_voice_note`** — Summarizes a voice-note transcript into a
   short "Topics Discussed" paragraph, but **refuses unless
   `consent_given=True`** — this mirrors the "(Requires Consent)" label
   next to the "Summarize from Voice Note" button in the form.

5. **`suggest_followups`** — Given an `interaction_id` (or raw context),
   asks the LLM for 2–4 concrete next-step suggestions (e.g. *"Schedule
   follow-up meeting in 2 weeks"*), matching the "AI Suggested Follow-ups"
   box under the form. Suggestions are also written back onto the
   interaction record.

## Data storage

For this assessment, `backend/storage.py` persists everything to a single
`backend/db.json` file (auto-created on first run, git-ignored) instead of
a real database — enough to demonstrate the HCP/interaction data model and
survive a server restart, while keeping the project dependency-free.

## Pushing this to GitHub

```bash
cd hcp-interaction-tracker
git init                      # skip if already a git repo
git add -A
git commit -m "Initial commit: HCP interaction tracker"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## Notes / possible next steps

- Swap `storage.py`'s JSON file for a real database (Postgres + SQLAlchemy)
  for multi-user/production use.
- Add auth (the API is wide open / CORS `*` for this demo).
- Stream the agent's tokens back to the chat panel instead of waiting for
  the full turn to complete.

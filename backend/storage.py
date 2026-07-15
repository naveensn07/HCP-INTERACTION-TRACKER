"""
storage.py
----------
A tiny, dependency-free persistence layer.

For a real product this would be a proper database (Postgres, etc).
For this assessment a JSON file is enough to demonstrate the data model,
while still surviving server restarts.

Data shape
----------
db.json
{
  "hcps": [ {id, name, specialty}, ... ],
  "interactions": [ {id, hcp_name, interaction_type, date, time, attendees,
                      topics_discussed, materials_shared, samples_distributed,
                      sentiment, outcomes, follow_up_actions, source, created_at,
                      updated_at}, ... ]
}
"""
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "db.json")
_lock = threading.Lock()

_SEED = {
    "hcps": [
        {"id": 1, "name": "Dr. Smith", "specialty": "Oncology"},
        {"id": 2, "name": "Dr. Sharma", "specialty": "Cardiology"},
        {"id": 3, "name": "Dr. Patel", "specialty": "Endocrinology"},
    ],
    "interactions": [],
}


def _load() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        _save(_SEED)
        return json.loads(json.dumps(_SEED))
    with open(DB_PATH, "r") as f:
        return json.load(f)


def _save(data: Dict[str, Any]) -> None:
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_id(items: List[Dict[str, Any]]) -> int:
    return (max((i["id"] for i in items), default=0)) + 1


# ---------------------------------------------------------------- HCPs ----
def search_hcps(query: str = "") -> List[Dict[str, Any]]:
    with _lock:
        data = _load()
        query = (query or "").strip().lower()
        if not query:
            return data["hcps"]
        return [h for h in data["hcps"] if query in h["name"].lower()]


def add_hcp(name: str, specialty: Optional[str] = None) -> Dict[str, Any]:
    with _lock:
        data = _load()
        existing = next(
            (h for h in data["hcps"] if h["name"].strip().lower() == name.strip().lower()),
            None,
        )
        if existing:
            return existing
        record = {"id": _next_id(data["hcps"]), "name": name, "specialty": specialty or ""}
        data["hcps"].append(record)
        _save(data)
        return record


# --------------------------------------------------------- Interactions --
def list_interactions() -> List[Dict[str, Any]]:
    with _lock:
        return _load()["interactions"]


def get_interaction(interaction_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        data = _load()
        return next((i for i in data["interactions"] if i["id"] == interaction_id), None)


def create_interaction(fields: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        data = _load()
        record = {
            "id": _next_id(data["interactions"]),
            "hcp_name": fields.get("hcp_name", ""),
            "interaction_type": fields.get("interaction_type", "Meeting"),
            "date": fields.get("date", ""),
            "time": fields.get("time", ""),
            "attendees": fields.get("attendees", ""),
            "topics_discussed": fields.get("topics_discussed", ""),
            "materials_shared": fields.get("materials_shared", []),
            "samples_distributed": fields.get("samples_distributed", []),
            "sentiment": fields.get("sentiment", "Neutral"),
            "outcomes": fields.get("outcomes", ""),
            "follow_up_actions": fields.get("follow_up_actions", []),
            "source": fields.get("source", "manual"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["interactions"].append(record)
        _save(data)
        return record


def update_interaction(interaction_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with _lock:
        data = _load()
        record = next((i for i in data["interactions"] if i["id"] == interaction_id), None)
        if record is None:
            return None
        for key, value in updates.items():
            if key in record and key not in ("id", "created_at"):
                record[key] = value
        record["updated_at"] = _now()
        _save(data)
        return record

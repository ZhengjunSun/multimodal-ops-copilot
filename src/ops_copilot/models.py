from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionStatus(str, Enum):
    OPEN = "open"
    ANALYZING = "analyzing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    session_id: str
    kind: str
    original_name: str
    stored_path: str
    sha256: str
    size: int
    metadata: dict


@dataclass
class IncidentSession:
    session_id: str
    title: str
    status: SessionStatus
    operator_message: str = ""
    timeline: list[dict] = field(default_factory=list)
    result: dict | None = None
    pending_action: dict | None = None
    trace: list[dict] = field(default_factory=list)

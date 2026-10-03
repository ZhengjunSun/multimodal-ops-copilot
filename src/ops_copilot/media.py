from __future__ import annotations

import hashlib
import json
import re
import uuid
import wave
from pathlib import Path

from PIL import Image

from .models import Artifact


ALLOWED = {".log":"log",".txt":"log",".json":"log",".png":"image",".jpg":"image",".jpeg":"image",".wav":"audio",".webm":"audio"}


def safe_name(name: str) -> str:
    base = Path(name).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120] or "artifact.bin"


def ingest_bytes(session_id: str, name: str, content: bytes, root: Path, max_bytes: int = 10_000_000) -> Artifact:
    if len(content) > max_bytes:
        raise ValueError("artifact exceeds size limit")
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError(f"unsupported artifact type: {extension}")
    artifact_id = uuid.uuid4().hex
    directory = root / session_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{artifact_id}-{safe_name(name)}"
    path.write_bytes(content)
    kind = ALLOWED[extension]
    metadata = inspect_artifact(kind, path)
    return Artifact(artifact_id,session_id,kind,name,str(path),hashlib.sha256(content).hexdigest(),len(content),metadata)


def inspect_artifact(kind: str, path: Path) -> dict:
    if kind == "image":
        with Image.open(path) as image:
            return {"width":image.width,"height":image.height,"format":image.format}
    if kind == "audio":
        if path.suffix.lower() != ".wav":
            return {"container": path.suffix.lower().lstrip("."), "duration_seconds": None, "requires_stt_adapter": True}
        with wave.open(str(path),"rb") as audio:
            frames=audio.getnframes(); rate=audio.getframerate()
            return {"channels":audio.getnchannels(),"sample_rate":rate,"duration_seconds":round(frames/rate,3) if rate else 0}
    text=path.read_text(encoding="utf-8",errors="replace")
    lines=text.splitlines()
    severity={level:sum(level in line.upper() for line in lines) for level in ("ERROR","WARN","CRITICAL")}
    return {"lines":len(lines),"severity_counts":severity,"preview":lines[:8]}


def timeline_from_logs(artifacts: list[Artifact]) -> list[dict]:
    timeline=[]
    timestamp=re.compile(r"\b(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\b")
    for artifact in artifacts:
        if artifact.kind!="log": continue
        for index,line in enumerate(Path(artifact.stored_path).read_text(encoding="utf-8",errors="replace").splitlines(),start=1):
            upper=line.upper()
            if any(level in upper for level in ("ERROR","WARN","CRITICAL","RECOVERED")):
                match=timestamp.search(line)
                timeline.append({"time":match.group(1) if match else None,"artifact_id":artifact.artifact_id,"line":index,"event":line[:300]})
    return timeline[:200]

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Protocol

import httpx

from .models import Artifact


class MultimodalProvider(Protocol):
    async def analyze(self, message: str, artifacts: list[Artifact], timeline: list[dict]) -> tuple[str, dict]: ...


class OfflineProvider:
    async def analyze(self, message: str, artifacts: list[Artifact], timeline: list[dict]) -> tuple[str, dict]:
        kinds={kind:sum(a.kind==kind for a in artifacts) for kind in ("log","image","audio")}
        summary=f"Offline analysis inspected {len(artifacts)} artifacts and {len(timeline)} evidence events. Operator request: {message}"
        return summary,{"provider":"offline","input_artifacts":kinds,"estimated_input_tokens":max(1,(len(message)+sum(a.size for a in artifacts if a.kind=='log'))//4),"estimated_cost_usd":0}


class OpenAICompatibleProvider:
    def __init__(self,base_url:str,api_key:str,model:str):
        self.base_url=base_url.rstrip("/"); self.api_key=api_key; self.model=model

    async def analyze(self,message:str,artifacts:list[Artifact],timeline:list[dict])->tuple[str,dict]:
        content:list[dict]=[{"type":"text","text":f"{message}\nEvidence timeline: {timeline[:30]}"}]
        for artifact in artifacts:
            if artifact.kind=="image":
                suffix=Path(artifact.stored_path).suffix.lower().replace("jpg","jpeg").lstrip(".")
                encoded=base64.b64encode(Path(artifact.stored_path).read_bytes()).decode()
                content.append({"type":"image_url","image_url":{"url":f"data:image/{suffix};base64,{encoded}"}})
        async with httpx.AsyncClient(timeout=60) as client:
            response=await client.post(f"{self.base_url}/chat/completions",headers={"Authorization":f"Bearer {self.api_key}"},json={"model":self.model,"messages":[{"role":"user","content":content}],"temperature":0})
            response.raise_for_status(); data=response.json()
        usage=data.get("usage",{})
        return data["choices"][0]["message"]["content"],{"provider":"openai-compatible","model":self.model,"input_tokens":usage.get("prompt_tokens"),"output_tokens":usage.get("completion_tokens")}


def provider_from_environment():
    if os.getenv("OPS_MODEL_PROVIDER")=="openai-compatible":
        return OpenAICompatibleProvider(os.environ["OPS_MODEL_BASE_URL"],os.environ["OPS_MODEL_API_KEY"],os.environ["OPS_MODEL_NAME"])
    return OfflineProvider()

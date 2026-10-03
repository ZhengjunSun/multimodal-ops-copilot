from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI,File,HTTPException,UploadFile,WebSocket,WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field

from .media import ingest_bytes
from .providers import provider_from_environment
from .runtime import EventHub,IncidentRuntime
from .store import IncidentStore


class NewSession(BaseModel): title:str=Field(min_length=3,max_length=120)
class AnalyzeRequest(BaseModel): message:str=Field(min_length=3,max_length=4000)
class Approval(BaseModel): approved:bool; reviewer:str=Field(min_length=2,max_length=100); comment:str=Field(default="",max_length=500)


def serialize(session,store):
    output=asdict(session); output["status"]=session.status.value; output["artifacts"]=[asdict(a) for a in store.artifacts(session.session_id)]; output["events"]=store.events(session.session_id); return output


def create_app(database:str|None=None,artifact_root:str|None=None)->FastAPI:
    store=IncidentStore(database or os.getenv("OPS_DATABASE","ops-copilot.db")); hub=EventHub(); runtime=IncidentRuntime(store,provider_from_environment(),hub)
    root=Path(artifact_root or os.getenv("OPS_ARTIFACT_ROOT","artifacts")); root.mkdir(parents=True,exist_ok=True)
    app=FastAPI(title="Multimodal Ops Copilot",version="0.1.0"); app.state.store=store; app.state.runtime=runtime

    @app.get("/api/health")
    async def health(): return {"status":"ok","provider":type(runtime.provider).__name__}
    @app.post("/api/sessions",status_code=201)
    async def new_session(body:NewSession): return serialize(store.create(body.title),store)
    @app.get("/api/sessions")
    async def list_sessions(): return [serialize(s,store) for s in store.list()]
    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id:str):
        try:return serialize(store.get(session_id),store)
        except KeyError:raise HTTPException(404,"session not found")
    @app.post("/api/sessions/{session_id}/artifacts",status_code=201)
    async def upload_artifact(session_id:str,file:UploadFile=File(...)):
        try:store.get(session_id)
        except KeyError:raise HTTPException(404,"session not found")
        try:artifact=ingest_bytes(session_id,file.filename or "artifact.bin",await file.read(),root); store.add_artifact(artifact); await hub.publish(session_id,{"event":"artifact_ingested","kind":artifact.kind,"name":artifact.original_name}); return asdict(artifact)
        except ValueError as exc:raise HTTPException(400,str(exc))
    @app.post("/api/sessions/{session_id}/analyze",status_code=202)
    async def analyze(session_id:str,body:AnalyzeRequest):
        try:return serialize(await runtime.start_analysis(session_id,body.message),store)
        except KeyError:raise HTTPException(404,"session not found")
        except ValueError as exc:raise HTTPException(409,str(exc))
    @app.post("/api/sessions/{session_id}/interrupt")
    async def interrupt(session_id:str):
        try:return serialize(await runtime.interrupt(session_id),store)
        except KeyError:raise HTTPException(404,"session not found")
    @app.post("/api/sessions/{session_id}/approval")
    async def approval(session_id:str,body:Approval):
        try:return serialize(await runtime.decide(session_id,body.approved,body.reviewer,body.comment),store)
        except KeyError:raise HTTPException(404,"session not found")
        except ValueError as exc:raise HTTPException(409,str(exc))
    @app.websocket("/ws/{session_id}")
    async def websocket(websocket:WebSocket,session_id:str):
        await websocket.accept(); queue=hub.subscribe(session_id)
        try:
            await websocket.send_json({"event":"connected","session_id":session_id})
            while True: await websocket.send_json(await queue.get())
        except WebSocketDisconnect: pass
        finally: hub.unsubscribe(session_id,queue)
    web=Path(__file__).with_name("web"); app.mount("/assets",StaticFiles(directory=web),name="assets")
    @app.get("/")
    async def index():return FileResponse(web/"index.html")
    return app


app=create_app()

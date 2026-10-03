from __future__ import annotations

import asyncio
import re
import time
import uuid

from .media import timeline_from_logs
from .models import IncidentSession, SessionStatus
from .providers import MultimodalProvider, OfflineProvider
from .store import IncidentStore


class EventHub:
    def __init__(self): self.queues:dict[str,list[asyncio.Queue]]={}
    def subscribe(self,session_id:str)->asyncio.Queue:
        queue=asyncio.Queue(); self.queues.setdefault(session_id,[]).append(queue); return queue
    def unsubscribe(self,session_id:str,queue:asyncio.Queue)->None:
        if session_id in self.queues and queue in self.queues[session_id]: self.queues[session_id].remove(queue)
    async def publish(self,session_id:str,event:dict)->None:
        for queue in self.queues.get(session_id,[]): await queue.put(event)


class IncidentRuntime:
    def __init__(self,store:IncidentStore,provider:MultimodalProvider|None=None,hub:EventHub|None=None):
        self.store=store; self.provider=provider or OfflineProvider(); self.hub=hub or EventHub(); self.running:dict[str,asyncio.Task]={}

    async def start_analysis(self,session_id:str,message:str)->IncidentSession:
        current=self.store.get(session_id)
        if current.status==SessionStatus.ANALYZING: raise ValueError("analysis already running")
        current.operator_message=message; current.status=SessionStatus.ANALYZING; current.result=None
        self.store.update(current,"analysis_started",{"message":message})
        task=asyncio.create_task(self._analyze(session_id)); self.running[session_id]=task
        return current

    async def wait(self,session_id:str)->IncidentSession:
        if session_id in self.running:
            try: await self.running[session_id]
            except asyncio.CancelledError: pass
        return self.store.get(session_id)

    async def interrupt(self,session_id:str)->IncidentSession:
        task=self.running.get(session_id)
        if task and not task.done(): task.cancel()
        session=self.store.get(session_id); session.status=SessionStatus.INTERRUPTED
        self.store.update(session,"analysis_interrupted",{}); await self.hub.publish(session_id,{"event":"analysis_interrupted"})
        return session

    async def decide(self,session_id:str,approved:bool,reviewer:str,comment:str="")->IncidentSession:
        session=self.store.get(session_id)
        if session.status!=SessionStatus.WAITING_APPROVAL: raise ValueError("session is not waiting for approval")
        self.store.decide(session_id,approved,reviewer,comment)
        if approved:
            session.status=SessionStatus.COMPLETED
            session.result={**(session.result or {}),"approved_action":session.pending_action,"action_executed":False,"safety_note":"Portfolio demo never changes an operational system."}
        else:
            session.status=SessionStatus.COMPLETED
            session.result={**(session.result or {}),"approved_action":None,"action_executed":False,"safety_note":"Proposed action rejected by reviewer."}
        session.pending_action=None; self.store.update(session,"incident_completed",{"approved":approved})
        await self.hub.publish(session_id,{"event":"incident_completed","approved":approved})
        return session

    async def _analyze(self,session_id:str)->None:
        started=time.time(); trace=[]
        try:
            artifacts=self.store.artifacts(session_id)
            await self.hub.publish(session_id,{"event":"stage","stage":"ingestion","artifacts":len(artifacts)})
            await asyncio.sleep(0)
            timeline=timeline_from_logs(artifacts)
            session=self.store.get(session_id); session.timeline=timeline
            trace.append({"span_id":uuid.uuid4().hex[:16],"name":"timeline","kind":"agent","duration_ms":round((time.time()-started)*1000,3),"evidence":len(timeline)})
            self.store.update(session,"timeline_built",{"events":len(timeline)})
            await self.hub.publish(session_id,{"event":"stage","stage":"model_analysis","timeline_events":len(timeline)})
            model_started=time.time(); summary,usage=await self.provider.analyze(session.operator_message,artifacts,timeline)
            trace.append({"span_id":uuid.uuid4().hex[:16],"name":"multimodal_analysis","kind":"model","duration_ms":round((time.time()-model_started)*1000,3),"usage":usage})
            summary=re.sub(r"(?i)(api[_-]?key|password)\s*[=:]\s*\S+",r"\1=[REDACTED]",summary)
            high_risk=any(word in session.operator_message.lower() for word in ("restart","delete","execute","修复","重启","执行"))
            session.result={"incident_brief":summary,"evidence_count":len(timeline),"artifacts":[{"id":a.artifact_id,"kind":a.kind,"sha256":a.sha256} for a in artifacts],"usage":usage}
            session.trace=trace
            if high_risk:
                session.status=SessionStatus.WAITING_APPROVAL; session.pending_action={"type":"remediation_proposal","description":"Isolate the synthetic affected component and start a controlled restart."}
                self.store.request_approval(session_id); self.store.update(session,"waiting_approval",{})
                await self.hub.publish(session_id,{"event":"waiting_approval","action":session.pending_action})
            else:
                session.status=SessionStatus.COMPLETED; self.store.update(session,"incident_completed",{})
                await self.hub.publish(session_id,{"event":"incident_completed"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            session=self.store.get(session_id); session.status=SessionStatus.FAILED; session.result={"error":f"{type(exc).__name__}: {exc}"}; session.trace=trace
            self.store.update(session,"analysis_failed",{"error_type":type(exc).__name__}); await self.hub.publish(session_id,{"event":"analysis_failed"})

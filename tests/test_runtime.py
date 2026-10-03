import tempfile
import unittest
from pathlib import Path

from ops_copilot.media import ingest_bytes
from ops_copilot.models import SessionStatus
from ops_copilot.runtime import IncidentRuntime
from ops_copilot.store import IncidentStore


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.store=IncidentStore(str(self.root/"test.db")); self.runtime=IncidentRuntime(self.store)

    async def asyncTearDown(self): self.temp.cleanup()

    async def test_analysis_completes(self):
        session=self.store.create("demo")
        self.store.add_artifact(ingest_bytes(session.session_id,"x.log",b"2026-01-01 00:00:00 ERROR demo",self.root/"artifacts"))
        await self.runtime.start_analysis(session.session_id,"analyze evidence")
        result=await self.runtime.wait(session.session_id)
        self.assertEqual(result.status,SessionStatus.COMPLETED); self.assertEqual(len(result.timeline),1)

    async def test_remediation_requires_approval(self):
        session=self.store.create("demo"); await self.runtime.start_analysis(session.session_id,"analyze and restart component")
        paused=await self.runtime.wait(session.session_id); self.assertEqual(paused.status,SessionStatus.WAITING_APPROVAL)
        completed=await self.runtime.decide(session.session_id,True,"tester")
        self.assertEqual(completed.status,SessionStatus.COMPLETED); self.assertFalse(completed.result["action_executed"])

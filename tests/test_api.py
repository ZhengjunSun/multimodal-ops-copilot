import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from ops_copilot.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name)
        self.client=TestClient(create_app(str(root/"api.db"),str(root/"artifacts"))); self.client.__enter__()
    def tearDown(self): self.client.__exit__(None,None,None); self.temp.cleanup()

    def test_upload_and_analyze(self):
        created=self.client.post("/api/sessions",json={"title":"Synthetic incident"}).json(); sid=created["session_id"]
        upload=self.client.post(f"/api/sessions/{sid}/artifacts",files={"file":("x.log",b"2026-01-01 00:00:00 ERROR failure","text/plain")})
        self.assertEqual(upload.status_code,201)
        self.assertEqual(self.client.post(f"/api/sessions/{sid}/analyze",json={"message":"analyze evidence"}).status_code,202)
        for _ in range(30):
            state=self.client.get(f"/api/sessions/{sid}").json()
            if state["status"]=="completed":break
            time.sleep(.02)
        self.assertEqual(state["status"],"completed"); self.assertEqual(len(state["timeline"]),1)

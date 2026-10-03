import io
import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image

from ops_copilot.media import ingest_bytes,timeline_from_logs


class MediaTests(unittest.TestCase):
    def test_log_ingestion_and_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact=ingest_bytes("s","incident.log",b"2026-01-01 10:00:00 WARN link flap\n2026-01-01 10:00:03 RECOVERED",Path(directory))
            self.assertEqual(artifact.metadata["lines"],2)
            self.assertEqual(len(timeline_from_logs([artifact])),2)

    def test_image_metadata(self):
        buffer=io.BytesIO(); Image.new("RGB",(32,20),"red").save(buffer,format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            artifact=ingest_bytes("s","screen.png",buffer.getvalue(),Path(directory))
            self.assertEqual((artifact.metadata["width"],artifact.metadata["height"]),(32,20))

    def test_wav_metadata(self):
        buffer=io.BytesIO()
        with wave.open(buffer,"wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b"\0\0"*8000)
        with tempfile.TemporaryDirectory() as directory:
            artifact=ingest_bytes("s","voice.wav",buffer.getvalue(),Path(directory))
            self.assertEqual(artifact.metadata["duration_seconds"],1.0)

    def test_unsupported_type(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): ingest_bytes("s","secret.exe",b"x",Path(directory))

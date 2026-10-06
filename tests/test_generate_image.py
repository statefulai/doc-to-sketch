"""Offline integration tests for the fallback image generator."""

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.sh"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/"
    "lXcAAAAASUVORK5CYII="
)


class ImageStub(BaseHTTPRequestHandler):
    requests = 0

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        type(self).requests += 1
        body = (
            {"error": {"message": "local stub failure"}}
            if payload["prompt"] == "fail"
            else {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}
        )
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


class GenerateImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ImageStub)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.run_dir = self.root / "run"
        self.env = os.environ.copy()
        for name in ("DOC_TO_SKETCH_UNATTENDED", "DOC_TO_SKETCH_MAX_IMAGES", "DOC_TO_SKETCH_RUN_DIR"):
            self.env.pop(name, None)
        self.env.update({
            "IMAGE_API_KEY": "local-test-key",
            "IMAGE_API_URL": f"http://127.0.0.1:{self.server.server_port}/images",
            "IMAGE_MODEL": "stub-model",
        })
        ImageStub.requests = 0

    def generate(self, prompt="图解", *extra):
        return subprocess.run(
            ["bash", str(SCRIPT), "--prompt", prompt, "--size", "1x1",
             "--output-dir", str(self.output), *extra],
            env=self.env, text=True, capture_output=True, timeout=10,
        )

    def receipts(self):
        return [json.loads(line) for line in
                (self.output / "sketch-receipt.jsonl").read_text().splitlines()]

    def test_unattended_cap_rejects_second_call(self):
        self.env.update({"DOC_TO_SKETCH_UNATTENDED": "1", "DOC_TO_SKETCH_MAX_IMAGES": "1",
                         "DOC_TO_SKETCH_RUN_DIR": str(self.run_dir)})
        first = self.generate()
        second = self.generate()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("上限", second.stderr)
        self.assertEqual(ImageStub.requests, 1)
        self.assertEqual((self.run_dir / ".doc-to-sketch-count").read_text().strip(), "1")
        self.assertEqual(len(self.receipts()), 1)

    def test_unattended_requires_run_dir(self):
        self.env.update({"DOC_TO_SKETCH_UNATTENDED": "1", "DOC_TO_SKETCH_MAX_IMAGES": "1"})
        result = self.generate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DOC_TO_SKETCH_RUN_DIR", result.stderr)
        self.assertEqual(ImageStub.requests, 0)
        self.assertFalse(self.output.exists())

    def test_shared_run_dir_caps_different_output_dirs(self):
        self.env.update({"DOC_TO_SKETCH_UNATTENDED": "1", "DOC_TO_SKETCH_MAX_IMAGES": "1",
                         "DOC_TO_SKETCH_RUN_DIR": str(self.run_dir)})
        first_output = self.output
        first = self.generate()
        self.output = self.root / "another-output"
        second = self.generate()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("上限", second.stderr)
        self.assertEqual(ImageStub.requests, 1)
        self.assertEqual((self.run_dir / ".doc-to-sketch-count").read_text().strip(), "1")
        self.assertEqual(len(list(first_output.glob("*.png"))), 1)
        self.assertFalse(list(self.output.glob("*.png")))

    def test_attended_mode_does_not_count(self):
        self.env["DOC_TO_SKETCH_MAX_IMAGES"] = "1"
        self.assertEqual(self.generate().returncode, 0)
        self.assertEqual(self.generate().returncode, 0)
        self.assertFalse((self.output / ".doc-to-sketch-count").exists())
        self.assertEqual([row["mode"] for row in self.receipts()], ["attended", "attended"])

    def test_receipt_fields_and_hashes(self):
        required = self.root / "required.json"
        required.write_text('["标题", "准确文字"]', encoding="utf-8")
        self.env.update({"DOC_TO_SKETCH_UNATTENDED": "1", "DOC_TO_SKETCH_MAX_IMAGES": "2",
                         "DOC_TO_SKETCH_RUN_DIR": str(self.run_dir)})
        result = self.generate("准确 prompt", "--required-text-file", str(required))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.receipts()[0]
        self.assertEqual(set(row), {
            "timestamp", "mode", "model", "size", "prompt_sha256", "output_file",
            "image_sha256", "bytes", "required_text", "review_status",
        })
        datetime.fromisoformat(row["timestamp"])
        self.assertEqual(row["mode"], "unattended")
        self.assertEqual(row["model"], "stub-model")
        self.assertEqual(row["size"], "1x1")
        self.assertEqual(row["prompt_sha256"], hashlib.sha256("准确 prompt".encode()).hexdigest())
        self.assertEqual(row["image_sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(row["bytes"], len(PNG))
        self.assertFalse(Path(row["output_file"]).is_absolute())
        self.assertEqual(Path(row["output_file"]).name, row["output_file"])
        self.assertEqual((self.output / row["output_file"]).read_bytes(), PNG)
        self.assertEqual(row["required_text"], ["标题", "准确文字"])
        self.assertEqual(row["review_status"], "pending_cross_audit")

    def test_failed_image_releases_slot(self):
        self.env.update({"DOC_TO_SKETCH_UNATTENDED": "1", "DOC_TO_SKETCH_MAX_IMAGES": "1",
                         "DOC_TO_SKETCH_RUN_DIR": str(self.run_dir)})
        failed = self.generate("fail")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual((self.run_dir / ".doc-to-sketch-count").read_text().strip(), "0")
        self.assertEqual(self.generate().returncode, 0)


if __name__ == "__main__":
    unittest.main()

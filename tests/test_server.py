import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_web, self.previous_artifacts = server.WEB, server.ARTIFACTS
        root = Path(self.temp.name)
        server.WEB = root / "web"
        server.ARTIFACTS = root / "artifacts"
        server.WEB.mkdir()
        server.ARTIFACTS.mkdir()
        (server.WEB / "index.html").write_text("OpsWatch", encoding="utf-8")
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        server.WEB, server.ARTIFACTS = self.previous_web, self.previous_artifacts
        self.temp.cleanup()

    def test_dashboard_and_empty_state(self):
        with urlopen(self.base + "/") as response:
            self.assertEqual(response.read(), b"OpsWatch")
        with urlopen(self.base + "/api/report") as response:
            self.assertEqual(json.load(response)["status"], "not_ready")

    def test_artifact_served_without_directory_access(self):
        (server.ARTIFACTS / "report.json").write_text('{"status":"ready"}', encoding="utf-8")
        with urlopen(self.base + "/api/report") as response:
            self.assertEqual(json.load(response)["status"], "ready")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/artifacts/report.json")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

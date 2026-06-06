import unittest
import urllib.request
import urllib.error
import threading
import socket
import time
import os
import sys

# Ensure server path is in sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(script_dir), "back-end"))

from http.server import ThreadingHTTPServer
from server import DashboardHandler
from shared.config import BASE_DIR

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class TestUnifiedServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We start the HTTP server in a daemon thread so it doesn't block the test process.
        cls.port = get_free_port()
        cls.server = ThreadingHTTPServer(('127.0.0.1', cls.port), DashboardHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        # Small sleep to let the server start
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1.0)

    def test_health_endpoint(self):
        url = f"{self.base_url}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("application/json", response.headers.get("Content-Type", ""))
            body = response.read().decode('utf-8')
            self.assertIn("ok", body)

    def test_static_html_serving(self):
        url = f"{self.base_url}/dashboard.html"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("text/html", response.headers.get("Content-Type", ""))
                body = response.read().decode('utf-8')
                self.assertTrue("<html" in body.lower() or "<!doctype" in body.lower())
        except urllib.error.HTTPError as e:
            self.fail(f"HTTPError raised: {e.code} {e.reason}")

    def test_static_css_serving(self):
        url = f"{self.base_url}/style.css"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("text/css", response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            self.fail(f"HTTPError raised: {e.code} {e.reason}")

    def test_static_js_serving(self):
        url = f"{self.base_url}/company_profile.js"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("javascript", response.headers.get("Content-Type", "").lower())
        except urllib.error.HTTPError as e:
            self.fail(f"HTTPError raised: {e.code} {e.reason}")

    def test_log_endpoint(self):
        import logging
        test_msg = "UNIQUE_TEST_LOG_MESSAGE_XYZ"
        logging.getLogger("bvb-server").info(test_msg)
        
        url = f"{self.base_url}/api/monitor/logs"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("application/json", response.headers.get("Content-Type", ""))
            body = response.read().decode('utf-8')
            import json
            logs = json.loads(body)
            self.assertTrue(isinstance(logs, list))
            found = False
            for log_entry in logs:
                if test_msg in log_entry:
                    found = True
                    break
            self.assertTrue(found, f"Message '{test_msg}' not found in logs: {logs}")

    def test_sse_endpoint(self):
        url = f"{self.base_url}/api/monitor/events"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=2.0) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("text/event-stream", response.headers.get("Content-Type", ""))
                line = response.readline()
                self.assertTrue(len(line) > 0)
                body = line.decode('utf-8')
                self.assertTrue("data:" in body or "event:" in body or "log" in body)
        except socket.timeout:
            pass
        except Exception as e:
            self.fail(f"Unexpected error in SSE test: {e}")

    def test_price_streaming(self):
        import server
        import json
        url = f"{self.base_url}/api/monitor/events"
        req = urllib.request.Request(url)
        received_events = []
        def listen():
            try:
                with urllib.request.urlopen(req, timeout=2.0) as response:
                    for line in response:
                        line = line.decode('utf-8').strip()
                        if line:
                            received_events.append(line)
                            if "2.205" in line:
                                break
            except Exception:
                pass
        t = threading.Thread(target=listen, daemon=True)
        t.start()
        time.sleep(0.2)
        mock_tick = {"sim": "TLV", "pret": 2.205, "volz": 1000, "updtype": "CA"}
        server.sse_manager.broadcast("price", mock_tick)
        time.sleep(0.2)
        found_price_event = False
        for ev in received_events:
            if "event: price" in ev or "TLV" in ev or "2.205" in ev:
                found_price_event = True
                break
        self.assertTrue(found_price_event, f"Price event not found in: {received_events}")

    def test_task_tracker_and_ping(self):
        import json
        url_ping = f"{self.base_url}/api/monitor/task-ping"
        payload = {"task": "Test Task", "status": "running"}
        req = urllib.request.Request(
            url_ping,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                body = response.read().decode('utf-8')
                self.assertIn("success", body)
        except urllib.error.HTTPError as e:
            self.fail(f"HTTPError raised in task-ping: {e.code} {e.reason}")

    def test_monitor_control_endpoints(self):
        import json
        for path in ["reconnect", "sync-portfolio", "sync-history", "reset-subscriptions"]:
            url = f"{self.base_url}/api/monitor/{path}"
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={'Content-Type': 'application/json'}
            )
            try:
                with urllib.request.urlopen(req) as response:
                    self.assertEqual(response.status, 200)
                    body = response.read().decode('utf-8')
                    self.assertIn("success", body)
            except urllib.error.HTTPError as e:
                self.fail(f"HTTPError on {path}: {e.code} {e.reason}")

    def test_search_symbol(self):
        import json
        url = f"{self.base_url}/api/tradeville/request"
        payload = {
            "cmd": "SearchSymbol",
            "prm": {
                "search": "electric"
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                body = response.read().decode('utf-8')
                res = json.loads(body)
                self.assertTrue("cmd" in res or "error" in res)
        except urllib.error.HTTPError as e:
            if e.code == 500:
                body = e.read().decode('utf-8')
                res = json.loads(body)
                self.assertTrue("error" in res)
            else:
                self.fail(f"HTTPError on SearchSymbol: {e.code} {e.reason}")
    def test_directory_traversal_protection(self):
        url = f"{self.base_url}/../back-end/server.py"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(url)
        self.assertIn(cm.exception.code, [400, 403, 404])

if __name__ == "__main__":
    unittest.main()

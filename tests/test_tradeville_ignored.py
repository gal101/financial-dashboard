import unittest
import os
import sys
import json
import time
import logging
from unittest.mock import MagicMock

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(script_dir), "back-end"))

from shared.tradeville_streamer import TradevilleStreamer
from shared.config import BASE_DIR

class TestTradevilleIgnoredMessages(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.temp_dir.name, "ignored_messages_test.log")
        self.streamer = TradevilleStreamer()
        # Override the handler to write to our temp file instead of the production file
        for handler in list(self.streamer.ignored_logger.handlers):
            handler.close()
            self.streamer.ignored_logger.removeHandler(handler)
        fh = logging.FileHandler(self.log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        self.streamer.ignored_logger.addHandler(fh)
        # Set running to True but don't call .start() to avoid starting background threads/connection loop
        self.streamer.running = True
    def tearDown(self):
        self.streamer.running = False
        # Remove file handlers to release the file lock on Windows
        for handler in list(self.streamer.ignored_logger.handlers):
            handler.close()
            self.streamer.ignored_logger.removeHandler(handler)
        self.temp_dir.cleanup()

    def test_ignored_messages_logging(self):
        # Setup mock WebSocket
        mock_ws = MagicMock()
        
        # We want to yield two ignored messages, one CA message (not ignored), and then raise an exception to stop loop
        messages = [
            '{"updtype":"AS","sim":"TVBETETF","":"pret"}', # Ignored (no cmd, type AS)
            '{"updtype":"CA","sim":"TLV","pret":2.2}',    # Not ignored (handled by push_queue)
            '{"cmd":"UnknownCommandResponse","data":{}}',   # Ignored (has cmd but not pending)
        ]
        
        def mock_recv():
            if messages:
                return messages.pop(0)
            raise Exception("Stop Loop")
            
        mock_ws.recv.side_effect = mock_recv
        self.streamer.ws = mock_ws
        
        # Run the receiver loop in the main thread (it will process 3 messages and then break on mock Exception)
        self.streamer._receiver_loop()
        
        # Flush/close handlers to ensure logs are written
        for handler in self.streamer.ignored_logger.handlers:
            handler.flush()
            
        # Verify log file contents
        self.assertTrue(os.path.exists(self.log_path), "Log file was not created")
        
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        self.assertEqual(len(lines), 2, f"Expected 2 lines in ignored_messages.log, got {len(lines)}")
        
        # Verify first message is logged
        self.assertIn('"updtype":"AS"', lines[0])
        self.assertIn('"sim":"TVBETETF"', lines[0])
        # Verify second message (UnknownCommandResponse) is logged
        self.assertIn('"cmd":"UnknownCommandResponse"', lines[1])

if __name__ == "__main__":
    unittest.main()

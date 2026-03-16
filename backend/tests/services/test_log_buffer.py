"""Tests for services/log_buffer.py — LogBufferHandler, redaction, query API."""

import asyncio
import logging

import pytest

from app.services.log_buffer import LogBufferHandler, _redact, get_log_buffer_handler


class TestRedact:
    def test_redacts_password(self):
        assert "password=***REDACTED***" in _redact("password=secret123")

    def test_redacts_token(self):
        assert "token=***REDACTED***" in _redact("token=abc.def.ghi")

    def test_redacts_api_key(self):
        assert "api_key=***REDACTED***" in _redact("api_key=sk-12345")

    def test_redacts_authorization(self):
        assert "authorization=***REDACTED***" in _redact("authorization=Bearer xyz")

    def test_preserves_non_sensitive(self):
        msg = "User logged in from 10.0.0.1"
        assert _redact(msg) == msg

    def test_redacts_multiple_patterns(self):
        msg = "password=abc token=def"
        result = _redact(msg)
        assert "password=***REDACTED***" in result
        assert "token=***REDACTED***" in result

    def test_case_insensitive(self):
        assert "PASSWORD=***REDACTED***" in _redact("PASSWORD=secret")


class TestLogBufferHandler:
    def _make_handler(self, maxlen: int = 100) -> LogBufferHandler:
        return LogBufferHandler(maxlen=maxlen)

    def _emit_record(self, handler: LogBufferHandler, message: str, level: int = logging.INFO):
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )
        handler.emit(record)

    def test_emit_stores_entry(self):
        h = self._make_handler()
        self._emit_record(h, "Hello world")

        assert h.get_total_buffered() == 1
        logs = h.get_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "Hello world"
        assert logs[0]["level"] == "INFO"

    def test_emit_increments_id(self):
        h = self._make_handler()
        self._emit_record(h, "first")
        self._emit_record(h, "second")

        logs = h.get_logs()
        assert logs[0]["id"] == 1
        assert logs[1]["id"] == 2

    def test_ring_buffer_maxlen(self):
        h = self._make_handler(maxlen=3)
        for i in range(5):
            self._emit_record(h, f"msg-{i}")

        assert h.get_total_buffered() == 3
        logs = h.get_logs()
        messages = [e["message"] for e in logs]
        assert messages == ["msg-2", "msg-3", "msg-4"]

    def test_emit_redacts_sensitive_data(self):
        h = self._make_handler()
        self._emit_record(h, "login password=hunter2")

        logs = h.get_logs()
        assert "hunter2" not in logs[0]["message"]
        assert "***REDACTED***" in logs[0]["message"]

    def test_get_latest_id_empty(self):
        h = self._make_handler()
        assert h.get_latest_id() == 0

    def test_get_latest_id(self):
        h = self._make_handler()
        self._emit_record(h, "a")
        self._emit_record(h, "b")
        assert h.get_latest_id() == 2

    def test_clear(self):
        h = self._make_handler()
        self._emit_record(h, "hello")
        h.clear()
        assert h.get_total_buffered() == 0
        assert h.get_latest_id() == 0


class TestLogBufferGetLogs:
    def _setup_handler(self) -> LogBufferHandler:
        h = LogBufferHandler(maxlen=100)
        levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
        for i, level in enumerate(levels):
            record = logging.LogRecord(
                name=f"test.mod{i}",
                level=level,
                pathname="test.py",
                lineno=1,
                msg=f"message-{i}",
                args=(),
                exc_info=None,
            )
            h.emit(record)
        return h

    def test_since_id_filter(self):
        h = self._setup_handler()
        logs = h.get_logs(since_id=3)
        assert all(e["id"] > 3 for e in logs)

    def test_level_filter(self):
        h = self._setup_handler()
        logs = h.get_logs(level="WARNING")
        assert all(e["level"] in ("WARNING", "ERROR", "CRITICAL") for e in logs)
        assert len(logs) == 3

    def test_search_filter_message(self):
        h = self._setup_handler()
        logs = h.get_logs(search="message-2")
        assert len(logs) == 1
        assert logs[0]["message"] == "message-2"

    def test_search_filter_logger_name(self):
        h = self._setup_handler()
        logs = h.get_logs(search="mod3")
        assert len(logs) == 1

    def test_search_case_insensitive(self):
        h = self._setup_handler()
        logs = h.get_logs(search="MESSAGE-0")
        assert len(logs) == 1

    def test_limit(self):
        h = self._setup_handler()
        logs = h.get_logs(limit=2)
        assert len(logs) == 2

    def test_combined_filters(self):
        h = self._setup_handler()
        # Only WARNING+ and containing "message"
        logs = h.get_logs(level="ERROR", search="message", limit=10)
        assert all(e["level"] in ("ERROR", "CRITICAL") for e in logs)


class TestLogBufferSubscribers:
    def test_subscribe_unsubscribe(self):
        h = LogBufferHandler(maxlen=100)
        queue = h.subscribe()
        assert queue in h._subscribers
        h.unsubscribe(queue)
        assert queue not in h._subscribers

    def test_emit_fans_out_to_subscriber(self):
        h = LogBufferHandler(maxlen=100)
        queue = h.subscribe()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="fan-out", args=(), exc_info=None,
        )
        h.emit(record)

        assert not queue.empty()
        entry = queue.get_nowait()
        assert entry["message"] == "fan-out"


class TestFormatEntry:
    def test_entry_has_expected_keys(self):
        h = LogBufferHandler(maxlen=100)
        record = logging.LogRecord(
            name="mylogger", level=logging.ERROR, pathname="file.py", lineno=42,
            msg="an error", args=(), exc_info=None,
        )
        h.emit(record)
        entry = h.get_logs()[0]
        assert set(entry.keys()) == {"id", "timestamp", "level", "logger_name", "message", "exc_info"}
        assert entry["logger_name"] == "mylogger"
        assert entry["exc_info"] is None


class TestGetLogBufferHandlerSingleton:
    def test_returns_same_instance(self):
        a = get_log_buffer_handler()
        b = get_log_buffer_handler()
        assert a is b

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtWidgets import QApplication, QWidget

from openai_usage import TrackedResponsesClient
from usage_popup import UsagePopup
from usage_tracker import UsageDelta, UsageTracker


def usage(incoming=820, outgoing=464):
    return {"input_tokens": incoming, "output_tokens": outgoing,
            "total_tokens": incoming + outgoing,
            "input_tokens_details": {"cached_tokens": 100, "future_field": 2},
            "output_tokens_details": {"reasoning_tokens": 20}}


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = UsageTracker()

    def tearDown(self):
        self.tracker.close()

    def test_delta_snapshot_and_dedup(self):
        response = {"id": "response-1", "usage": usage()}
        self.assertTrue(self.tracker.record_response(response, "0.001234"))
        self.assertFalse(self.tracker.record_response(response, "0.001234"))
        self.assertEqual(self.tracker.snapshot().total_tokens, 1284)
        delta = self.tracker.consume_delta()
        self.assertEqual((delta.input_tokens, delta.output_tokens, delta.total_tokens), (820, 464, 1284))
        self.assertEqual((delta.cached_tokens, delta.reasoning_tokens), (100, 20))
        self.assertEqual(delta.estimated_cost, Decimal("0.001234"))
        self.assertEqual(self.tracker.consume_delta().total_tokens, 0)
        self.assertEqual(self.tracker.snapshot().session_total, 1284)
        self.assertTrue(delta.last_update)

    def test_sdk_object_missing_usage_and_unknown_cost(self):
        class SDKUsage:
            def model_dump(self):
                return usage()
        self.assertTrue(self.tracker.record_response(SimpleNamespace(id="sdk", usage=SDKUsage())))
        self.assertFalse(self.tracker.record_response({"id": "not-done", "usage": None}))
        self.assertIsNone(self.tracker.snapshot().estimated_cost)
        self.tracker.record_usage(usage(), estimated_cost="0.01")
        self.assertIsNone(self.tracker.consume_delta().estimated_cost)

    def test_installed_sdk_usage_object(self):
        try:
            from openai.types.responses.response_usage import ResponseUsage
        except ImportError:
            self.skipTest("可选 OpenAI SDK 未安装")
        raw = usage()
        raw["input_tokens_details"]["cache_write_tokens"] = 0
        obj = ResponseUsage.model_validate(raw)
        self.tracker.record_usage(obj)
        self.assertEqual(self.tracker.consume_delta().total_tokens, 1284)

    def test_invalid_usage_never_changes_totals(self):
        for value in ({"input_tokens": -1, "output_tokens": 0, "total_tokens": -1},
                      {"input_tokens": 1, "output_tokens": 1, "total_tokens": 5},
                      {"input_tokens": "10", "output_tokens": 1, "total_tokens": 11}):
            with self.assertRaises(ValueError):
                self.tracker.record_usage(value)
        self.assertEqual(self.tracker.snapshot().total_tokens, 0)

    def test_threaded_recording_has_no_loss(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.tracker.record_usage(usage(), response_id=str(i)), range(24)))
        self.assertEqual(self.tracker.consume_delta().total_tokens, 24 * 1284)

    def test_persistence_new_session_and_midnight(self):
        with tempfile.TemporaryDirectory() as directory:
            current = [datetime(2026, 9, 22, 23, 59, 59).timestamp()]
            path = Path(directory) / "usage.sqlite3"
            first = UsageTracker(path, clock=lambda: current[0])
            first.record_usage(usage(), response_id="persist")
            first.close()
            second = UsageTracker(path, clock=lambda: current[0])
            self.assertEqual(second.snapshot().session_total, 0)
            self.assertEqual(second.snapshot().today_total, 1284)
            self.assertEqual(second.consume_delta().total_tokens, 0)
            self.assertFalse(second.record_usage(usage(), response_id="persist"))
            current[0] += 2
            self.assertEqual(second.snapshot().today_total, 0)
            second.record_usage(usage(), response_id="next-day")
            self.assertEqual(second.snapshot().today_total, 1284)
            current[0] += 301
            self.assertEqual(second.snapshot().recent_rate, 0)
            second.close()


class APIAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_estimate_does_not_lose_real_usage(self):
        tracker = UsageTracker()
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value={"id": "cost-error", "usage": usage()})))
        await TrackedResponsesClient(tracker, client).create(model="test", input="test", cost_estimator=lambda response: "invalid")
        self.assertEqual(tracker.snapshot().total_tokens, 1284)
        self.assertIsNone(tracker.snapshot().estimated_cost)
        tracker.close()

    async def test_response_recorded_without_network(self):
        tracker = UsageTracker()
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value={"id": "api", "usage": usage()})))
        adapter = TrackedResponsesClient(tracker, client)
        await adapter.create(model="test-model", input="test", cost_estimator=lambda response: Decimal("0.001"))
        self.assertEqual(tracker.consume_delta().total_tokens, 1284)
        with self.assertRaises(ValueError):
            await adapter.create(model="test-model", input="test", stream=True)
        self.assertEqual(client.responses.create.await_count, 1)
        tracker.close()

    async def test_request_failure_does_not_invent_usage(self):
        tracker = UsageTracker()
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("request failed"))))
        with self.assertRaises(RuntimeError):
            await TrackedResponsesClient(tracker, client).create(model="test", input="test")
        self.assertEqual(tracker.snapshot().total_tokens, 0)
        tracker.close()

    async def test_missing_key_fails_before_sdk_request(self):
        tracker = UsageTracker()
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                TrackedResponsesClient(tracker)
        tracker.close()


class PopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.owner = QWidget()
        self.owner.setGeometry(700, 400, 220, 340)
        self.popup = UsagePopup(self.owner, demo=True)
        self.delta = UsageDelta(820, 464, 1284, estimated_cost=Decimal("0.00328"))

    def tearDown(self):
        self.popup.dismiss()
        self.owner.close()
        self.owner.deleteLater()

    def test_zero_silent_and_exact_timeline(self):
        self.popup.push(UsageDelta())
        self.assertEqual(self.popup.phase, "hidden")
        self.popup.push(self.delta)
        self.popup.advance(100)
        self.assertAlmostEqual(self.popup.opacity, 0.5)
        self.assertAlmostEqual(self.popup.offset, 3)
        self.popup.advance(100)
        self.assertEqual(self.popup.phase, "hold")
        self.assertEqual(self.popup.opacity, 1)
        self.popup.advance(1600)
        self.assertEqual(self.popup.phase, "out")
        self.popup.advance(300)
        self.assertAlmostEqual(self.popup.opacity, 0.5)
        self.assertAlmostEqual(self.popup.offset, -2)
        self.popup.advance(300)
        self.assertFalse(self.popup.isVisible())
        self.assertFalse(self.popup.timer.isActive())

    def test_merge_during_fade_preserves_opacity_and_extends(self):
        self.popup.push(self.delta)
        self.popup.advance(2000)
        alpha, offset = self.popup.opacity, self.popup.offset
        self.popup.push(self.delta)
        self.assertEqual(self.popup.delta.total_tokens, 2568)
        self.assertEqual(self.popup.opacity, alpha)
        self.assertEqual(self.popup.offset, offset)
        self.popup.advance(200)
        self.assertEqual(self.popup.phase, "hold")
        self.assertEqual(self.popup.opacity, 1)
        self.popup.advance(2000)
        self.assertNotEqual(self.popup.phase, "hidden")
        self.popup.advance(200)
        self.assertEqual(self.popup.phase, "hidden")

    def test_merge_hold_and_follow(self):
        self.popup.push(self.delta)
        self.popup.advance(1600)
        self.popup.push(self.delta)
        self.assertEqual(self.popup.phase_ms, 0)
        before = self.popup.pos()
        self.owner.move(self.owner.pos() + QPoint(10, 10))
        self.popup.follow()
        self.assertEqual(self.popup.pos(), before + QPoint(10, 10))

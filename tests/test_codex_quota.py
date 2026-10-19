import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from codex_quota import CodexQuotaClient, QuotaSnapshot, QuotaWindow, parse_quota


def window(duration, used=25):
    return {"windowDurationMins": duration, "usedPercent": used, "resetsAt": 1800000000}


class QuotaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_duration_not_slot_determines_window(self):
        snapshot = parse_quota({"rateLimits": {"primary": window(10080, 30), "secondary": window(300, 80)}})
        self.assertEqual(snapshot.five_hour.remaining_percent, 20)
        self.assertEqual(snapshot.weekly.remaining_percent, 70)

    def test_multi_bucket_preferred_without_substituting_other_products(self):
        result = {"rateLimits": {"primary": window(300, 5)},
                  "rateLimitsByLimitId": {"codex": {"primary": window(10080, 40)},
                                          "other": {"primary": window(300, 5)}}}
        snapshot = parse_quota(result)
        self.assertIsNone(snapshot.five_hour)
        self.assertEqual(snapshot.weekly.remaining_percent, 60)
        del result["rateLimitsByLimitId"]["codex"]
        self.assertIsNone(parse_quota(result).five_hour)

    def test_missing_invalid_and_bounds(self):
        self.assertIsNone(parse_quota({}).five_hour)
        self.assertIsNone(parse_quota({"rateLimits": {"primary": window(300, None)}}).five_hour)
        self.assertEqual(parse_quota({"rateLimits": {"primary": window(300, 120)}}).five_hour.remaining_percent, 0)
        self.assertIsNone(parse_quota({"rateLimits": {"primary": window(300, float("nan"))}}).five_hour)

    def test_initialize_order_and_read_only_protocol(self):
        client = CodexQuotaClient()
        client.stopped = False
        sent = []
        with patch.object(client, "_send", side_effect=sent.append), patch.object(client, "refresh") as refresh:
            client._initialize()
            self.assertEqual(sent[0]["method"], "initialize")
            client._handle({"id": 999, "result": {}})
            self.assertFalse(client.ready)
            client._handle({"id": sent[0]["id"], "result": {}})
            self.assertTrue(client.ready)
            self.assertEqual(sent[1]["method"], "initialized")
            refresh.assert_called_once()
            client._request("account/rateLimits/read")
            self.assertEqual(sent[2]["method"], "account/rateLimits/read")
            client._handle({"id": sent[2]["id"], "result": {"rateLimits": {"primary": window(300)}}})
            self.assertEqual(client.snapshot.five_hour.remaining_percent, 75)
        client.stop()

    def test_errors_preserve_snapshot_without_exposing_server_message(self):
        client = CodexQuotaClient()
        client.stopped = False
        client.snapshot = QuotaSnapshot(QuotaWindow(38, 1800000000), updated_at=1)
        client.pending = (1, "account/rateLimits/read")
        client._handle({"id": 1, "error": {"message": "sensitive server detail"}})
        self.assertEqual(client.snapshot.five_hour.remaining_percent, 38)
        self.assertNotIn("sensitive", client.snapshot.error)
        self.assertEqual(client.timer.interval(), 60000)
        client.stop()

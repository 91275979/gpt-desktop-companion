import unittest
from dataclasses import replace
from datetime import datetime

from PySide6.QtWidgets import QApplication
from codex_quota import parse_quota
from quota_provider import CodexQuotaProvider, QuotaSnapshot, QuotaUpdate, normalize_codex
from usage_tracker import UsageTracker, QuotaChange
from main import DesktopPet


class QuotaProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.now = 1000
        self.tracker = UsageTracker(clock=lambda: self.now)
        self.base = QuotaSnapshot(100, 20, 80, 20, 2000, self.now)

    def tearDown(self):
        self.tracker.close()

    def record(self, used, **kwargs):
        self.now += 2
        snapshot = replace(self.base, used=used, remaining=100-used,
                           percentage=used, fetched_at=self.now, **kwargs)
        self.tracker.record_quota(QuotaUpdate((snapshot,)))
        return snapshot

    def test_provider_normalizes_and_polls_two_seconds(self):
        provider = CodexQuotaProvider()
        self.assertEqual(provider.timer.interval(), 2000)
        raw = parse_quota({'rateLimits': {'primary': {
            'windowDurationMins': 300, 'usedPercent': 27, 'resetsAt': 2000}}})
        update = normalize_codex(raw)
        self.assertEqual(update.snapshots[0].used, 27)
        self.assertEqual(update.snapshots[0].remaining, 73)
        self.assertEqual(update.snapshots[0].unit, 'percent')
        self.assertIsNotNone(normalize_codex(parse_quota({})).error)
        provider.stop()

    def test_baseline_unchanged_and_positive_delta(self):
        self.record(20)
        self.record(20)
        self.assertEqual(self.tracker.consume_quota_changes(), [])
        self.record(21.25)
        self.record(21.5)
        changes = self.tracker.consume_quota_changes()
        self.assertEqual(changes[0].consumed, 1.5)
        self.assertEqual(self.tracker.consume_quota_changes(), [])
        self.assertEqual(self.tracker.snapshot().session_total, 0)

    def test_reset_decrease_and_capacity_change_are_new_baselines(self):
        self.record(20)
        self.record(21)
        self.record(1, reset_time=3000)
        self.assertEqual(self.tracker.consume_quota_changes(), [])
        self.record(0)
        self.assertEqual(self.tracker.consume_quota_changes(), [])
        self.record(50, total=200)
        self.assertEqual(self.tracker.consume_quota_changes(), [])

    def test_failure_keeps_last_success_and_recovery_compares_it(self):
        last = self.record(20)
        self.tracker.record_quota(QuotaUpdate(error='secret detail'))
        self.assertEqual(self.tracker.quota_error, '额度数据暂不可用')
        self.assertEqual(self.tracker.quota_details(), [(last, 0, True)])
        self.record(21)
        self.assertIsNone(self.tracker.quota_error)
        self.assertEqual(self.tracker.consume_quota_changes()[0].consumed, 1)

    def test_recent_minute_expires_without_another_response(self):
        self.record(20)
        self.record(22)
        self.assertEqual(self.tracker.quota_details()[0][1], 2)
        self.now += 60
        self.assertEqual(self.tracker.quota_details()[0][1], 0)

    def test_out_of_order_and_invalid_data_do_not_replace_success(self):
        last = self.record(20)
        self.tracker.record_quota(QuotaUpdate((self.base,)))
        self.assertEqual(self.tracker.quota_details()[0][0], last)
        for invalid in (float('nan'), -1, 'bad'):
            self.tracker.record_quota(QuotaUpdate((replace(last, used=invalid),)))
            self.assertEqual(self.tracker.quota_details()[0][0], last)
            self.assertIsNotNone(self.tracker.quota_error)

    def test_periods_stay_separate(self):
        self.tracker.record_quota(QuotaUpdate((self.base, replace(self.base, period='week'))))
        self.tracker.record_quota(QuotaUpdate((replace(self.base, used=21, fetched_at=1002),
                                             replace(self.base, period='week', used=22, fetched_at=1002))))
        self.assertEqual([c.consumed for c in self.tracker.consume_quota_changes()], [1, 2])

    def test_real_unit_tokens_does_not_use_percentage_conversion(self):
        first = replace(self.base, total=10000, used=200, unit='tokens')
        self.tracker.record_quota(QuotaUpdate((first,)))
        self.tracker.record_quota(QuotaUpdate((replace(first, used=245, fetched_at=1002),)))
        self.assertEqual(self.tracker.consume_quota_changes()[0].consumed, 45)

    def test_popup_integration_merges_and_keeps_timeline(self):
        pet = DesktopPet(tracker=self.tracker)
        try:
            pet.show()
            pet.update_quota(QuotaUpdate((self.base,)))
            pet.settle_usage()
            expected_time = datetime.fromtimestamp(self.base.fetched_at).strftime('%H:%M:%S')
            self.assertEqual(pet.panel.usage.updated_at_label.text(), f'更新 {expected_time}')
            self.assertEqual(pet.usage_popup.phase, 'hidden')
            next_snapshot = replace(self.base, used=21, remaining=79, fetched_at=1002)
            pet.update_quota(QuotaUpdate((next_snapshot,)))
            pet.settle_usage()
            popup = pet.usage_popup
            self.assertEqual(popup.display_lines()[0], '本轮消耗 1.00%')
            popup.advance(1900)
            alpha = popup.opacity
            popup.push_quota(QuotaChange(next_snapshot, 0.5))
            self.assertEqual(popup.opacity, alpha)
            self.assertEqual(popup.quota_change.consumed, 1.5)
            popup.advance(2500)
            self.assertEqual(popup.phase, 'hidden')
            popup.push_quota(QuotaChange(replace(next_snapshot, unit='tokens'), 42))
            self.assertEqual(popup.display_lines()[0], '- 42 tokens')
            popup.advance(2500)
            self.assertEqual(popup.phase, 'hidden')
            self.assertEqual(self.tracker.snapshot().session_total, 0)
        finally:
            pet.close()

    def test_two_period_popup_timeline_follow_and_empty_tokens(self):
        pet = DesktopPet(tracker=self.tracker)
        try:
            pet.show()
            pet.show_info_panel()
            self.assertFalse(pet.panel.token_area.isVisible())
            self.assertFalse(pet.panel.token_unavailable.isVisible())
            popup = pet.usage_popup
            week = replace(self.base, period='week', remaining=66)
            popup.push_quotas([QuotaChange(self.base, 1), QuotaChange(week, 1)])
            self.assertEqual(len(popup.quota_changes), 2)
            popup.advance(90)
            self.assertAlmostEqual(popup.opacity, .5)
            self.assertAlmostEqual(popup.offset, 2.5)
            popup.advance(90)
            self.assertEqual(popup.phase, 'hold')
            pet.move(pet.x()-100, pet.y()-100)
            popup.follow()
            self.assertTrue(pet.screen().availableGeometry().contains(popup.geometry()))
            popup.advance(1620)
            self.assertEqual(popup.phase, 'out')
            popup.advance(350)
            self.assertAlmostEqual(popup.opacity, .5)
            self.assertAlmostEqual(popup.offset, -2.5)
            popup.push_quota(QuotaChange(replace(week, remaining=65), 1))
            self.assertEqual(len(popup.quota_changes), 2)
            self.assertEqual(popup.quota_changes[week.key].consumed, 2)
            self.assertAlmostEqual(popup.opacity, .5)
            popup.advance(2500)
            self.assertEqual(popup.phase, 'hidden')
            popup.push_quotas([])
            self.assertEqual(popup.phase, 'hidden')
        finally:
            pet.close()

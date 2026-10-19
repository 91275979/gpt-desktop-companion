"""空闲时间必须覆盖启动和情绪恢复，不能由台词寿命或连击重置。"""
import random
import unittest

from interaction_manager import InteractionManager, SLEEP_AFTER_IDLE


class SleepClockTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.manager = InteractionManager(random.Random(1), clock=lambda: self.now)

    def test_startup_without_any_click_reaches_sleep_deadline(self):
        self.assertIsNone(self.manager.last_click_time)
        self.now += 29.9
        self.manager.advance()
        self.assertLess(self.manager.idle_seconds(), SLEEP_AFTER_IDLE)
        self.now += .1
        self.manager.advance()
        self.assertAlmostEqual(self.manager.idle_seconds(), SLEEP_AFTER_IDLE)

    def test_anger_reset_preserves_last_interaction_for_sleep(self):
        for _ in range(25):
            self.manager.click()
            self.now += .1
        self.assertEqual(self.manager.anger_level, 5)
        last_click = self.manager.last_interaction_time
        self.now = last_click + 6
        self.manager.advance()
        self.assertFalse(self.manager.fast_click_mode)
        self.assertIsNone(self.manager.last_click_time)
        self.assertEqual(self.manager.last_interaction_time, last_click)
        self.now = last_click + 30
        self.manager.advance()
        self.assertEqual(self.manager.idle_seconds(), SLEEP_AFTER_IDLE)

    def test_click_restarts_full_sleep_interval(self):
        self.now += 29
        self.manager.click()
        self.assertEqual(self.manager.idle_seconds(), 0)
        self.now += 29
        self.manager.advance()
        self.assertLess(self.manager.idle_seconds(), SLEEP_AFTER_IDLE)
        self.now += 1
        self.assertEqual(self.manager.idle_seconds(), SLEEP_AFTER_IDLE)
        result = self.manager.click()
        self.assertEqual(self.manager.idle_seconds(), 0)
        self.assertIn(result.category, ('greeting', 'idle'))

    def test_quota_update_does_not_restart_sleep_clock(self):
        self.now += 25
        self.manager.quota_changed()
        self.now += 5
        self.manager.advance()
        self.assertEqual(self.manager.idle_seconds(), SLEEP_AFTER_IDLE)


if __name__ == '__main__':
    unittest.main()

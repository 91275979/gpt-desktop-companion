import unittest
import uuid
from instance import SingleInstance, Event, is_running, signal
from watcher import Monitor, matches_target


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.now, self.target, self.pet = 0, False, False
        self.started, self.stopped = 0, 0
        def start():
            self.started += 1
        def stop():
            self.stopped += 1
        self.monitor = Monitor(lambda:self.target, lambda:self.pet, start, stop, lambda:self.now)

    def test_absent_launch_exit_and_manual_restart_delay(self):
        self.monitor.tick()
        self.assertEqual(self.started, 0)
        self.target = True
        self.monitor.tick()
        self.assertEqual(self.started, 1)
        self.now = 2
        self.monitor.tick()
        self.assertEqual(self.started, 1)
        self.pet = True
        self.monitor.tick()
        self.pet = False
        self.now = 4
        self.monitor.tick()
        self.now = 6
        self.monitor.tick()
        self.assertEqual(self.started, 1)
        self.now = 8
        self.monitor.tick()
        self.assertEqual(self.started, 2)
        self.pet = True
        self.target = False
        self.monitor.tick()
        self.assertEqual(self.stopped, 1)

    def test_pause_until_next_target_session(self):
        self.target, self.pet = True, True
        self.monitor.tick(pause=True)
        self.pet = False
        self.now = 30
        self.monitor.tick()
        self.assertEqual(self.started, 0)
        self.target = False
        self.monitor.tick()
        self.target = True
        self.monitor.tick()
        self.assertEqual(self.started, 1)

    def test_unknown_read_never_closes_pet(self):
        self.target, self.pet = None, True
        self.monitor.tick()
        self.assertEqual(self.stopped, 0)

    def test_same_name_other_install_is_not_target(self):
        self.assertTrue(matches_target(r'C:\Program Files\WindowsApps\OpenAI.Codex_26.915.4065.0_x64__2p2nqsd0c76g0\app\ChatGPT.exe'))
        self.assertFalse(matches_target(r'C:\Other\ChatGPT.exe'))
        self.assertFalse(matches_target(r'C:\Program Files\WindowsApps\Other.App_1_x64__2p2nqsd0c76g0\app\ChatGPT.exe'))

    def test_mutex_and_event_cleanup(self):
        role = 'test.' + uuid.uuid4().hex
        first, second = SingleInstance(role), SingleInstance(role)
        try:
            self.assertTrue(first.acquired)
            self.assertFalse(second.acquired)
            self.assertTrue(is_running(role))
            event = Event(role+'.close')
            try:
                self.assertTrue(signal(role+'.close'))
                self.assertTrue(event.consume())
                self.assertFalse(event.consume())
            finally:
                event.close()
        finally:
            first.close()
            second.close()
        self.assertFalse(is_running(role))

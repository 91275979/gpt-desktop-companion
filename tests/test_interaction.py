import random
import unittest
from types import SimpleNamespace
from interaction_manager import InteractionManager
from character import CharacterAnimation
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


class InteractionTests(unittest.TestCase):
    def manager(self):
        stamp = [0.0]
        return stamp, InteractionManager(random.Random(1), lambda: stamp[0])

    def test_stages_fixed_targets_and_maximum(self):
        stamp, m = self.manager()
        self.assertIn(m.click().category, ('greeting', 'idle'))
        for level in range(1, 6):
            target = m.stage_target
            self.assertIn(target, (3, 4))
            for progress in range(1, target+1):
                stamp[0] += .2
                result = m.click()
                self.assertNotIn(result.category, ('greeting','idle','weather','usage','market'))
                if progress < target:
                    self.assertEqual(m.stage_target, target)
                    self.assertEqual(m.stage_progress, progress)
            self.assertEqual(m.anger_level, level)
        target, progress = m.stage_target, m.stage_progress
        for _ in range(20):
            stamp[0] += .2
            self.assertEqual(m.click().category, 'ANGER_5')
            self.assertEqual((m.stage_target,m.stage_progress), (target,progress))

    def test_intervals_combo_break_and_casual_clicks(self):
        for interval in (.451, .6, 1, 2.9):
            stamp, m = self.manager()
            for _ in range(20):
                stamp[0] += interval
                m.click()
                self.assertFalse(m.fast_click_mode)
                self.assertEqual(m.anger_level, 0)
        stamp, m = self.manager()
        m.click()
        stamp[0] = .45
        m.click()
        self.assertEqual(m.stage_progress, 1)
        stamp[0] += .6
        m.click()
        self.assertEqual(m.stage_progress, 1)
        stamp[0] += .91
        m.click()
        self.assertEqual(m.stage_progress, 0)
        self.assertTrue(m.fast_click_mode)

    def test_hold_cooling_resume_and_reset(self):
        stamp, m = self.manager()
        for _ in range(25):
            m.click()
            stamp[0] += .1
        last = m.last_interaction_time
        stamp[0] = last+2.5
        m.advance()
        self.assertEqual(m.anger_level, 5)
        stamp[0] = last+4
        m.advance()
        self.assertTrue(0 < m.anger_level < 5)
        cooled = m.anger_level
        self.assertTrue(m.click().category.startswith('ANGER_'))
        self.assertEqual(m.anger_level, cooled)
        stamp[0] += .2
        m.click()
        self.assertEqual(m.stage_progress, 1)
        stamp[0] += 6
        m.advance()
        self.assertEqual(m.mood_state, 'CALM')
        self.assertFalse(m.fast_click_mode)
        self.assertEqual(m.stage_progress, 0)
        self.assertIn(m.click().category, ('greeting','idle'))

    def test_context_weights_expire_and_no_network_needed(self):
        stamp = [0]
        manager = InteractionManager(clock=lambda: stamp[0])
        self.assertEqual(set(manager.weights()), {'idle', 'greeting'})
        manager.quota_changed()
        risk = SimpleNamespace(fetched_at=100, apparent=2, rain_probability=60, precipitation=0, wind=30)
        weights = manager.weights(risk, [SimpleNamespace(fetched_at=100)], now=120)
        for key in ('usage', 'weather', 'market'):
            self.assertGreater(weights[key], weights['greeting'])
        stamp[0] = 121
        self.assertEqual(set(manager.weights(risk, [SimpleNamespace(fetched_at=100)], now=4000)), {'idle','greeting'})

    def test_feedback_and_missing_expression_recover(self):
        app = QApplication.instance() or QApplication([])
        image = QImage(20, 40, QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.white)
        animation = CharacterAnimation({'idle':image}, QRectF(0,0,20,40))
        animation.interact('talk', 2000)
        self.assertEqual(animation.displayed_state, 'idle')
        animation.advance(.11)
        self.assertAlmostEqual(animation.current_rect().height()/40, 1.03, delta=.001)
        self.assertEqual(animation.current_rect().bottom(), 40)
        animation.hold()
        frozen = animation.current_rect()
        animation.advance(.5)
        self.assertEqual(animation.current_rect(), frozen)
        animation.release(False)
        self.assertEqual(animation.click_elapsed, .22)
        animation.advance(2)
        self.assertEqual(animation.state, 'idle')

    def test_persistent_anger_blocks_blink_until_explicit_recovery(self):
        app = QApplication.instance() or QApplication([])
        image = QImage(20, 40, QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.white)
        animation = CharacterAnimation({'idle':image, 'happy':image}, QRectF(0,0,20,40))
        animation.interact('strong_angry', 1500, persistent=True)
        animation.advance(20)
        self.assertEqual(animation.state, 'strong_angry')
        self.assertEqual(animation.displayed_state, 'idle')
        animation.set_state('idle')
        animation.advance(animation.blink_remaining+.01)
        self.assertEqual(animation.state, 'blink')

    def test_idle_seconds_tracks_last_interaction(self):
        stamp, manager = self.manager()
        self.assertEqual(manager.idle_seconds(), 0.0)
        manager.click()
        stamp[0] += 29.9
        self.assertAlmostEqual(manager.idle_seconds(), 29.9, places=2)
        stamp[0] += .1
        self.assertAlmostEqual(manager.idle_seconds(), 30.0, places=2)

    def test_repeated_anger_clicks_keep_clip_playing(self):
        app = QApplication.instance() or QApplication([])
        image = QImage(20, 40, QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.white)
        animation = CharacterAnimation({'idle': image, 'strong_angry': image}, QRectF(0,0,20,40),
            frames={'strong_angry': (image, image, image)}, frame_rate=10)
        animation.interact('strong_angry', 1500, persistent=True)
        animation.advance(.11)
        self.assertEqual(animation.frame_index, 1)
        animation.interact('strong_angry', 2000, persistent=True)
        self.assertEqual(animation.frame_index, 1)
        animation.advance(.1)
        self.assertEqual(animation.frame_index, 2)

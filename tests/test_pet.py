import unittest
import tempfile
import random
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, QEvent, Qt
from PySide6.QtGui import QMouseEvent, QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import DesktopPet
from context_menu import create_context_menu
from character import CHARACTER_PATH, CharacterAnimation, CharacterAssets, load_character, character_bounds, align_characters


class DesktopPetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.pet = DesktopPet()
        self.pet.show()
        self.app.processEvents()

    def tearDown(self):
        self.pet.close()
        self.pet.tracker.close()
        self.pet.deleteLater()
        self.app.processEvents()

    def character_point(self, opaque=True):
        rect = self.pet.character_rect
        for y in range(int(rect.top()) + 5, int(rect.bottom()) - 5, 5):
            for x in range(int(rect.left()) + 5, int(rect.right()) - 5, 5):
                point = QPoint(x, y)
                if self.pet.contains_pet(point) == opaque:
                    return point
        self.fail("角色图片缺少用于测试的透明/不透明区域")

    def test_window_and_initial_position(self):
        self.assertTrue(self.pet.isVisible())
        for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint):
            self.assertTrue(self.pet.windowFlags() & flag)
        self.assertTrue(self.pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        area = self.app.primaryScreen().availableGeometry()
        self.assertEqual(self.pet.x(), max(area.left(), area.right() + 1 - self.pet.width() - 24))
        self.assertEqual(self.pet.y(), max(area.top(), area.bottom() + 1 - self.pet.height() - 24))
        self.assertEqual(self.pet.character_rect.height(), 180)
        source = self.pet.character_image
        self.assertAlmostEqual(self.pet.character_rect.width(), source.width() * 180 / source.height(), delta=0.5)

    def test_click_shows_greeting_and_happy(self):
        def alpha_at(image, x, y):
            scale = image.devicePixelRatio()
            return image.pixelColor(round(x * scale), round(y * scale)).alpha()

        self.assertFalse(self.pet.greeting_visible)
        hidden = self.pet.grab().toImage()
        self.assertEqual(alpha_at(hidden, 0, 0), 0)
        bubble_x = self.pet.width() // 2
        self.assertEqual(alpha_at(hidden, bubble_x, 25), 0)
        point = self.character_point()
        QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
        self.assertTrue(self.pet.greeting_visible)
        self.assertGreaterEqual(alpha_at(self.pet.grab().toImage(), bubble_x, 25), 240)
        QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
        self.assertTrue(self.pet.greeting_visible)
        self.assertTrue(self.pet.interactions.fast_click_mode)
        self.pet.animation.advance(2.6)
        self.assertEqual(self.pet.animation.state, "thinking")

    def test_transparent_area_does_not_toggle_or_drag(self):
        point = self.character_point(opaque=False)
        origin = self.pet.pos()
        QTest.mousePress(self.pet, Qt.MouseButton.LeftButton, pos=point)
        self.assertIsNone(self.pet._press_position)
        QTest.mouseRelease(self.pet, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(self.pet.pos(), origin)
        # QTest 将空 QPoint(0, 0) 当作“点击中心”，使用明确的边角坐标。
        QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
        self.assertFalse(self.pet.greeting_visible)

    def test_drag_moves_without_toggling(self):
        local = self.character_point()
        origin = self.pet.pos()
        start = self.pet.mapToGlobal(local)
        delta = QPoint(-90, -60)
        QTest.mousePress(self.pet, Qt.MouseButton.LeftButton, pos=local)
        frozen = self.pet.animation.current_rect()
        self.pet.animation.advance(0.2)
        self.assertEqual(self.pet.animation.current_rect(), frozen)
        move = QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(self.pet, move)
        QTest.mouseRelease(self.pet, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(self.pet.pos(), origin + delta)
        self.assertFalse(self.pet.greeting_visible)
        self.assertFalse(self.pet.animation.held)
        self.assertEqual(self.pet.animation.state, "idle")

    def test_idle_timeout_enters_sleep_and_click_wakes(self):
        self.pet.interactions.last_interaction_time = self.pet.interactions.clock() - 30.1
        self.pet.update_mood()
        self.assertEqual(self.pet.animation.state.value, "sleep")
        point = self.character_point()
        QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
        self.assertNotEqual(self.pet.animation.state.value, "sleep")
        self.assertTrue(self.pet.greeting_visible)

    def test_public_state_interface(self):
        self.pet.set_character_state("talk")
        self.assertEqual(self.pet.animation.state, "talk")
        self.pet.set_character_state("thinking")
        self.assertEqual(self.pet.animation.state, "thinking")

    def test_codex_quota_does_not_count_as_api_tokens(self):
        from codex_quota import parse_quota
        from quota_provider import normalize_codex
        snapshot = parse_quota({"rateLimits": {"primary": {"windowDurationMins": 300, "usedPercent": 62, "resetsAt": 1800000000}}})
        self.pet.update_quota(normalize_codex(snapshot))
        self.assertIn("38%", self.pet.panel.quota_five.text())
        self.assertFalse(self.pet.panel.quota_week.isVisible())
        self.assertEqual(self.pet.tracker.snapshot().total_tokens, 0)
        self.assertFalse(self.pet.usage_popup.isVisible())
        self.assertFalse(self.pet.quota_client.timer.isActive())  # 测试默认离线。

    def test_usage_settlement_silent_without_delta_and_merges(self):
        self.assertEqual(self.pet.usage_timer.interval(), 2000)
        self.pet.settle_usage()
        self.assertFalse(self.pet.usage_popup.isVisible())
        data = {"input_tokens": 820, "output_tokens": 464, "total_tokens": 1284}
        self.pet.tracker.record_usage(data)
        self.pet.settle_usage()
        self.pet.usage_popup.advance(2000)
        self.pet.tracker.record_usage(data)
        self.pet.settle_usage()
        self.assertEqual(self.pet.usage_popup.delta.total_tokens, 2568)
        phase = self.pet.usage_popup.phase
        self.pet.settle_usage()
        self.assertEqual(self.pet.usage_popup.phase, phase)
        self.assertEqual(self.pet.usage_popup.delta.total_tokens, 2568)
        self.assertEqual(self.pet.panel.values["session"].text(), "2,568")

    def test_panel_visibility_follow_and_no_overlap(self):
        self.assertFalse(self.pet.panel.isVisible())
        self.pet.show_info_panel()
        self.app.processEvents()
        self.assertTrue(self.pet.panel.isVisible())
        self.assertEqual(self.pet.panel.width(), 230)
        self.assertEqual(self.pet.panel.height(), 180)
        self.assertEqual(self.pet.panel.header_title.text(), 'GPT Companion')
        self.assertGreater(self.pet.panel.header_title.width(), 70)
        self.assertLess(self.pet.panel.geometry().bottom(), self.pet.y() + self.pet.character_rect.top())
        before = self.pet.panel.pos()
        self.pet.move(self.pet.pos() + QPoint(-30, -30))
        self.app.processEvents()
        self.assertEqual(self.pet.panel.pos(), before + QPoint(-30, -30))
        character_global = self.pet.character_rect.toRect().translated(self.pet.pos())
        self.assertFalse(self.pet.panel.geometry().intersects(character_global))
        area = self.pet.screen().availableGeometry()
        self.pet.move(area.left() + 10, self.pet.y())
        self.app.processEvents()
        self.assertGreaterEqual(self.pet.panel.x(), area.left())
        self.assertLess(self.pet.panel.geometry().bottom(), self.pet.y() + self.pet.character_rect.top())
        self.pet.hide_info_panel()
        self.assertFalse(self.pet.panel.isVisible())

    def test_menu_actions_size_anchor_and_topmost(self):
        menu = create_context_menu(self.pet)
        actions = {a.text(): a for a in menu.actions() if not a.isSeparator()}
        from instance import is_running
        self.assertEqual(len(actions), 8 if is_running('watcher') else 7)
        actions["使用详情"].trigger()
        self.assertTrue(self.pet.panel.isVisible())
        anchor = self.pet.pos() + QPoint(self.pet.width() // 2, self.pet.height() - 20)
        for label, height in (("小尺寸", 150), ("大尺寸", 220), ("中尺寸", 180)):
            actions[label].trigger()
            self.assertEqual(self.pet.character_rect.height(), height)
            self.assertEqual(self.pet.pos() + QPoint(self.pet.width() // 2, self.pet.height() - 20), anchor)
            self.assertEqual(self.pet.animation.base_rect, self.pet.character_rect)
        for enabled in (False, True):
            actions["始终置顶"].setChecked(enabled)
            self.app.processEvents()
            for window in (self.pet, self.pet.panel):
                self.assertEqual(bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint), enabled)
                self.assertTrue(window.isVisible())
        actions["退出程序"].trigger()
        self.assertFalse(self.pet.panel.isVisible())
        self.assertFalse(self.pet.isVisible())
        self.assertFalse(self.pet.animation.timer.isActive())
        menu.deleteLater()

    def test_right_button_does_not_greet_or_change_state(self):
        point = self.character_point()
        QTest.mouseClick(self.pet, Qt.MouseButton.RightButton, pos=point)
        self.assertFalse(self.pet.greeting_visible)
        self.assertIsNone(self.pet._press_position)
        self.assertEqual(self.pet.animation.state, "idle")

    def test_panel_does_not_interrupt_blink_and_hides_with_pet(self):
        self.pet.show_info_panel()
        self.pet.animation.advance(self.pet.animation.blink_remaining + 0.01)
        self.assertEqual(self.pet.animation.state, "blink")
        self.pet.animation.advance(0.17)
        self.assertEqual(self.pet.animation.state, "idle")
        self.pet.hide()
        self.assertFalse(self.pet.panel.isVisible())
        self.pet.show()
        self.assertTrue(self.pet.panel.isVisible())

    def test_greeting_expires_and_repeated_click_restarts_timeout(self):
        self.assertEqual(self.pet.GREETING_TEXT, "主人好！")
        point = self.character_point()
        QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(800)
        QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=self.character_point())
        QTest.qWait(800)
        self.assertTrue(self.pet.greeting_visible)
        QTest.qWait(2600)
        self.assertFalse(self.pet.greeting_visible)

    def test_double_click_is_two_immediate_interactions_without_panel_toggle(self):
        point = self.character_point()
        for visible in (False, True):
            if visible:
                self.pet.show_info_panel()
            before = self.pet.interactions.click_count
            QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
            QTest.mouseDClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
            QTest.mouseRelease(self.pet, Qt.MouseButton.LeftButton, pos=point)
            self.assertEqual(self.pet.panel_requested, visible)
            self.assertTrue(self.pet.greeting_visible)
            self.assertEqual(self.pet.interactions.click_count, before + 2)

    def test_fast_clicks_replace_dialogue_without_queue(self):
        point = self.pet.character_rect.center().toPoint()
        for count in range(1, 10):
            previous = self.pet.greeting_text
            QTest.mouseClick(self.pet, Qt.MouseButton.LeftButton, pos=point)
            self.assertTrue(self.pet.greeting_visible)
            self.assertEqual(self.pet.interactions.click_count, count)
            if count >= 5:
                from interaction_manager import ANGER_LINES
                self.assertIn(self.pet.greeting_text, ANGER_LINES[self.pet.interactions.anger_level])
                self.assertNotEqual(previous, self.pet.greeting_text)
            self.assertTrue(self.pet.greeting_timer.isActive())
        self.assertFalse(hasattr(self.pet, 'click_timer'))

    def test_real_states_share_visible_height_and_anchor(self):
        bounds = [character_bounds(self.pet.assets.images[name]) for name in ("idle", "blink", "happy")]
        reference = bounds[0]
        for rect in bounds[1:]:
            self.assertAlmostEqual(rect.height(), reference.height(), delta=1)
            self.assertAlmostEqual(rect.bottom(), reference.bottom(), delta=1)
            self.assertAlmostEqual(rect.center().x(), reference.center().x(), delta=1)

    def test_timer_animates_without_moving_window_and_stops_when_hidden(self):
        origin = self.pet.pos()
        before = self.pet.animation.elapsed
        QTest.qWait(160)
        self.assertGreater(self.pet.animation.elapsed, before)
        self.assertEqual(self.pet.pos(), origin)
        self.pet.hide()
        self.assertFalse(self.pet.animation.timer.isActive())
        self.pet.show()
        self.assertTrue(self.pet.animation.timer.isActive())

    def test_animation_stays_inside_window_and_below_bubble(self):
        for frame in range(600):
            if frame % 9 == 0:
                self.pet.animation.release(clicked=True)
            self.pet.animation.advance(1 / 30)
            rect = self.pet.animation.current_rect()
            self.assertTrue(QRectF(self.pet.rect()).contains(rect))
            self.assertGreater(rect.top(), 50)

    def test_real_character_has_alpha(self):
        source = QImage(str(CHARACTER_PATH))
        self.assertTrue(source.hasAlphaChannel())
        self.assertEqual(source.pixelColor(0, 0).alpha(), 0)
        self.assertGreaterEqual(self.pet.character_image.height(), 640)

    def test_provided_expression_assets_render_distinct_frames(self):
        self.pet.animation.stop()
        geometry = self.pet.animation.current_rect()
        frames = []
        for state in ("idle", "blink", "happy"):
            self.assertIn(state, self.pet.assets.images)
            self.pet.set_character_state(state)
            self.assertEqual(self.pet.animation.displayed_state, state)
            self.assertEqual(self.pet.animation.current_rect(), geometry)
            self.assertEqual(self.pet.animation.image.size(), self.pet.character_image.size())
            frames.append(self.pet.grab().toImage())
        self.assertNotEqual(frames[0], frames[1])
        self.assertNotEqual(frames[0], frames[2])
        self.assertNotEqual(frames[1], frames[2])


class CharacterLoadingTests(unittest.TestCase):
    def test_invalid_assets_have_actionable_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.png"
            with self.assertRaisesRegex(ValueError, "找不到角色图片"):
                load_character(path)
            path.write_bytes(b"broken png")
            with self.assertRaisesRegex(ValueError, "无法读取"):
                load_character(path)
            source = QImage(40, 60, QImage.Format.Format_RGBA8888)
            source.fill(Qt.GlobalColor.white)
            source.save(str(path))
            with self.assertRaisesRegex(ValueError, "没有透明背景"):
                load_character(path)
            source.fill(Qt.GlobalColor.transparent)
            source.save(str(path))
            with self.assertRaisesRegex(ValueError, "完全透明"):
                load_character(path)

    def test_crop_preserves_white_character_and_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "padded.png"
            source = QImage(40, 60, QImage.Format.Format_RGBA8888)
            source.fill(Qt.GlobalColor.transparent)
            for y in range(10, 50):
                for x in range(10, 30):
                    source.setPixelColor(x, y, QColor("white"))
            source.setPixelColor(15, 20, QColor(255, 255, 255, 0))
            source.setPixelColor(16, 20, QColor(255, 255, 255, 12))
            source.save(str(path))
            cropped = load_character(path)
            self.assertEqual((cropped.width(), cropped.height()), (20, 40))
            self.assertEqual(cropped.pixelColor(0, 0), QColor("white"))
            self.assertEqual(cropped.pixelColor(5, 10).alpha(), 0)
            self.assertEqual(cropped.pixelColor(6, 10).alpha(), 12)


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        image = QImage(100, 200, QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.white)
        image.setPixelColor(50, 100, QColor(0, 0, 0, 0))
        self.animation = CharacterAnimation({"idle": image}, QRectF(20, 80, 120, 240), rng=random.Random(42))

    def test_idle_range_and_continuity(self):
        previous = self.animation.current_rect()
        for _ in range(600):
            self.animation.advance(1 / 30)
            rect = self.animation.current_rect()
            self.assertGreaterEqual(rect.height(), 240)
            self.assertLessEqual(rect.height(), 240 * 1.004 + 1e-9)
            self.assertAlmostEqual(rect.width() / rect.height(), 0.5)
            self.assertAlmostEqual(rect.center().x(), 80)
            self.assertAlmostEqual(rect.bottom(), 320)
            self.assertLess(abs(rect.top() - previous.top()), 0.3)
            previous = rect

    def test_happy_timeout_and_drag_freeze(self):
        self.animation.release(clicked=True)
        self.animation.advance(0.14)
        self.assertEqual(self.animation.state, "happy")
        self.animation.hold()
        frozen = self.animation.current_rect()
        self.animation.advance(1)
        self.assertEqual(self.animation.current_rect(), frozen)
        self.animation.release(clicked=False)
        self.assertEqual(self.animation.current_rect(), frozen)
        self.animation.advance(0.5)
        self.assertEqual(self.animation.state, "happy")
        self.animation.release(clicked=True)
        self.animation.advance(0.9)
        self.assertEqual(self.animation.state, "happy")
        self.animation.advance(0.11)
        self.assertEqual(self.animation.state, "idle")

    def test_random_blinks_restore_idle(self):
        intervals = []
        for _ in range(20):
            delay = self.animation.blink_remaining
            intervals.append(delay)
            self.assertGreaterEqual(delay, 3)
            self.assertLessEqual(delay, 6)
            self.animation.advance(delay - 0.01)
            self.assertEqual(self.animation.state, "idle")
            self.animation.advance(0.02)
            self.assertEqual(self.animation.state, "blink")
            self.animation.advance(0.17)
            self.assertEqual(self.animation.state, "idle")
        self.assertGreater(len(set(intervals)), 1)

    def test_explicit_states_cancel_previous_timeout_and_blinks(self):
        self.animation.set_state("happy")
        self.animation.set_state("talk")
        self.animation.advance(20)
        self.assertEqual(self.animation.state, "talk")
        self.animation.set_state("thinking")
        self.animation.advance(20)
        self.assertEqual(self.animation.state, "thinking")
        self.animation.set_state("idle")
        self.animation.set_state("blink")
        self.animation.release(clicked=True)
        self.animation.advance(0.2)
        self.assertEqual(self.animation.state, "happy")
        with self.assertRaises(ValueError):
            self.animation.set_state("unknown")
        self.assertEqual(self.animation.state, "happy")

    def test_missing_states_fall_back_without_geometry_change(self):
        self.animation.advance(1.4)
        rect = self.animation.current_rect()
        for state in ("blink", "happy", "talk", "thinking", "idle"):
            self.animation.set_state(state)
            self.assertEqual(self.animation.displayed_state, "idle")
            self.assertEqual(self.animation.current_rect(), rect)

    def test_alpha_hit_testing_follows_animated_geometry(self):
        self.animation.advance(1.4)
        rect = self.animation.current_rect()
        def mapped(x, y):
            return QPointF(rect.x() + x * rect.width() / 100,
                           rect.y() + y * rect.height() / 200)
        self.assertFalse(self.animation.contains(mapped(50.5, 100.5)))
        self.assertTrue(self.animation.contains(mapped(60.5, 100.5)))
        self.assertFalse(self.animation.contains(QPointF(rect.right() + 1, rect.center().y())))

    def test_real_state_loading_switches_pixels_and_alpha_without_recropping(self):
        # 临时几何测试图，不作为项目角色素材，也不写入 assets。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            from character import CharacterState
            for index, name in enumerate(state.value for state in CharacterState):
                image = QImage(40, 60, QImage.Format.Format_RGBA8888)
                image.fill(Qt.GlobalColor.transparent)
                image.setPixelColor(10 + index, 20, QColor("white"))
                image.save(str(root / f"{name}.png"))
            assets = CharacterAssets(root / "idle.png")
            self.assertFalse(assets.unavailable)
            animation = CharacterAnimation(assets.images, QRectF(0, 0, 40, 60))
            for index, state in enumerate(state.value for state in CharacterState):
                animation.set_state(state)
                self.assertEqual(animation.displayed_state, state)
                self.assertEqual(animation.image.size(), assets.images["idle"].size())
                self.assertEqual(animation.current_rect(), QRectF(0, 0, 40, 60))
                self.assertTrue(animation.contains(QPointF(20, 30)))
                self.assertFalse(animation.contains(QPointF(1, 1)))
                # 文件移走后依然从内存缓存读取。
                (root / f"{state}.png").unlink()
                self.assertFalse(animation.pixmaps[state].isNull())

    def test_numbered_png_clips_loop_and_keep_each_frames_motion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            idle = QImage(40, 60, QImage.Format.Format_RGBA8888)
            idle.fill(Qt.GlobalColor.transparent)
            for y in range(20, 40):
                for x in range(10, 30):
                    idle.setPixelColor(x, y, QColor("white"))
            idle.save(str(root / "idle.png"))
            clip_dir = root / "animations" / "talk"
            clip_dir.mkdir(parents=True)
            idle.save(str(clip_dir / "000.png"))
            moved = QImage(idle)
            moved.fill(Qt.GlobalColor.transparent)
            for y in range(18, 38):
                for x in range(10, 30):
                    moved.setPixelColor(x, y, QColor("white"))
            moved.save(str(clip_dir / "001.png"))
            (clip_dir / "notes.png").write_bytes(b"not an animation frame")

            assets = CharacterAssets(root / "idle.png")
            self.assertIn("talk", assets.frames)
            self.assertEqual(len(assets.frames["talk"]), 2)
            self.assertEqual(assets.frames["talk"][0].size(), assets.frames["talk"][1].size())
            self.assertNotEqual(assets.frames["talk"][0], assets.frames["talk"][1])
            animation = CharacterAnimation(assets.images, QRectF(0, 0, 40, 60),
                                           frames=assets.frames)
            animation.set_state("talk")
            self.assertEqual(animation.frame_index, 0)
            animation.advance(1 / 12 + 0.001)
            self.assertEqual(animation.frame_index, 1)
            animation.hold()
            animation.advance(1)
            self.assertEqual(animation.frame_index, 1)
            animation.release(False)
            animation.advance(1 / 12)
            self.assertEqual(animation.frame_index, 0)
            animation.set_state("sleep")
            self.assertEqual(animation.displayed_state, "idle")

    def test_animation_manifest_sets_clip_fps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = QImage(40, 60, QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            image.setPixelColor(20, 30, QColor("white"))
            image.save(str(root / "idle.png"))
            animation_root = root / "animations"
            clip_dir = animation_root / "talk"
            clip_dir.mkdir(parents=True)
            image.save(str(clip_dir / "000.png"))
            image.save(str(clip_dir / "001.png"))
            (animation_root / "manifest.json").write_text(
                '{"default_fps": 12, "fps": {"talk": 5}}', encoding="utf-8")
            assets = CharacterAssets(root / "idle.png")
            self.assertEqual(assets.frame_rates["talk"], 5)
            animation = CharacterAnimation(assets.images, QRectF(0, 0, 40, 60),
                                           frames=assets.frames,
                                           frame_rates=assets.frame_rates)
            animation.set_state("talk")
            animation.advance(0.1)
            self.assertEqual(animation.frame_index, 0)
            animation.advance(0.1)
            self.assertEqual(animation.frame_index, 1)

    def test_invalid_clip_keeps_static_state_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = QImage(40, 60, QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            image.setPixelColor(20, 30, QColor("white"))
            image.save(str(root / "idle.png"))
            image.save(str(root / "talk.png"))
            clip_dir = root / "animations" / "talk"
            clip_dir.mkdir(parents=True)
            image.save(str(clip_dir / "000.png"))
            (clip_dir / "001.png").write_bytes(b"invalid")
            assets = CharacterAssets(root / "idle.png")
            self.assertIn("talk", assets.images)
            self.assertNotIn("talk", assets.frames)
            self.assertIn("talk", assets.invalid_animations)

    def test_missing_invalid_and_mismatched_assets_use_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = QImage(40, 60, QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            image.setPixelColor(20, 30, QColor("white"))
            image.save(str(root / "idle.png"))
            (root / "happy.png").write_bytes(b"invalid")
            image.copy(0, 0, 30, 40).save(str(root / "talk.png"))
            assets = CharacterAssets(root / "idle.png")
            self.assertEqual(set(assets.unavailable), {"blink", "happy", "thinking", "embarrassed", "shy_angry", "angry", "strong_angry", "sleep"})
            self.assertEqual(assets.images["talk"].size(), assets.images["idle"].size())
            animation = CharacterAnimation(assets.images, QRectF(0, 0, 40, 60))
            for state in assets.unavailable:
                animation.set_state(state)
                self.assertEqual(animation.displayed_state, "idle")
            (root / "idle.png").rename(root / "gpt_assistant.png")
            self.assertIn("idle", CharacterAssets(root / "idle.png").images)
            (root / "gpt_assistant.png").unlink()
            with self.assertRaisesRegex(ValueError, "找不到角色图片"):
                CharacterAssets(root / "idle.png")

    def test_hover_does_not_reset_on_blink_or_happy_and_freezes_during_drag(self):
        self.animation.set_hovered(True)
        self.animation.advance(1)
        self.assertAlmostEqual(self.animation.hover_amount, 1, places=4)
        rect = self.animation.current_rect()
        self.animation.set_state("blink")
        self.assertEqual(self.animation.current_rect(), rect)
        self.animation.set_state("happy")
        self.assertEqual(self.animation.current_rect(), rect)
        self.animation.hold()
        self.animation.set_hovered(False)
        self.animation.advance(1)
        self.assertEqual(self.animation.current_rect(), rect)
        self.animation.release(False)
        self.animation.advance(1)
        self.assertAlmostEqual(self.animation.hover_amount, 0, places=4)

    def test_different_canvas_sizes_and_offsets_normalize_once(self):
        images = {}
        for name, width, height, left, top, size in (
            ("idle", 100, 200, 20, 30, 40),
            ("blink", 220, 320, 50, 70, 80),
            ("happy", 150, 300, 80, 120, 30),
        ):
            image = QImage(width, height, QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            for y in range(top, top + size):
                for x in range(left, left + size):
                    image.setPixelColor(x, y, QColor("white"))
            images[name] = image
        aligned = align_characters(images)
        for image in aligned.values():
            self.assertEqual(image.size(), aligned["idle"].size())
            self.assertEqual(character_bounds(image), character_bounds(aligned["idle"]))


if __name__ == "__main__":
    unittest.main()

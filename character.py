"""角色 PNG 加载：保留原始分辨率，裁掉透明外边距。"""

from pathlib import Path
import json
import math
import random
import re
from enum import Enum

from PySide6.QtCore import QObject, QElapsedTimer, QRectF, QTimer, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QPainter


CHARACTER_PATH = Path(__file__).resolve().parent / "assets" / "characters" / "idle.png"
ANIMATION_CACHE_HEIGHT = 768
_NONZERO_ALPHA = re.compile(rb"[\x01-\xff]")
_VISIBLE_ALPHA = re.compile(rb"[\x18-\xff]")


def _alpha_bounds(image, pattern):
    """Find alpha bounds using byte searches rather than a Python loop per pixel."""
    data = image.constBits()
    stride, width = image.bytesPerLine(), image.width()
    left, top, right, bottom = width, image.height(), -1, -1
    for y in range(image.height()):
        row = bytes(data[y * stride + 3:y * stride + width * 4:4])
        first = pattern.search(row)
        if first is None:
            continue
        last = pattern.search(row[::-1])
        left, right = min(left, first.start()), max(right, width - last.start() - 1)
        top, bottom = min(top, y), y
    return left, top, right, bottom


class CharacterState(str, Enum):
    IDLE = "idle"
    BLINK = "blink"
    HAPPY = "happy"
    TALK = "talk"
    THINKING = "thinking"
    EMBARRASSED = "embarrassed"
    SHY_ANGRY = "shy_angry"
    ANGRY = "angry"
    STRONG_ANGRY = "strong_angry"
    SLEEP = "sleep"


def load_character(path, crop=True):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"找不到角色图片：\n{path}\n\n请放入仅含角色本体的透明背景 PNG 后重新启动。")
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"无法读取角色图片，请检查 PNG 文件是否损坏：\n{path}")
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    # 按 alpha 裁剪，不删除白色：银白色头发和服装也属于角色。
    data, stride = image.constBits(), image.bytesPerLine()
    alpha = b"".join(bytes(data[y * stride + 3:y * stride + image.width() * 4:4])
                     for y in range(image.height()))
    if not any(alpha):
        raise ValueError("角色图片完全透明，没有可显示的角色。")
    if alpha.count(255) == len(alpha):
        raise ValueError("角色图片没有透明背景。请先去除背景、说明文字和装饰，导出仅含角色的透明 PNG。")
    if crop:
        left, top, right, bottom = _alpha_bounds(image, _NONZERO_ALPHA)
        image = image.copy(left, top, right - left + 1, bottom - top + 1)
    image.setDevicePixelRatio(1.0)
    return image


def character_bounds(image):
    """忽略近透明边缘噪声，测量角色落点，仅在加载阶段调用。"""
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    left, top, right, bottom = _alpha_bounds(rgba, _VISIBLE_ALPHA)
    if right < 0:
        raise ValueError("角色图片没有足够不透明的可见区域。")
    return QRectF(left, top, right - left + 1, bottom - top + 1)


def align_characters(images):
    """一次性对齐到共同透明画布；运行时所有状态使用完全相同的缩放。"""
    bounds = {name: character_bounds(image) for name, image in images.items()}
    height = bounds["idle"].height()
    widths = {name: rect.width() * height / rect.height() for name, rect in bounds.items()}
    # 两像素保护边距；保留等比形状，以脚底和水平中心为共同锚点。
    canvas_width, canvas_height = math.ceil(max(widths.values())) + 4, int(height) + 4
    aligned = {}
    for name, image in images.items():
        canvas = QImage(canvas_width, canvas_height, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = QRectF((canvas_width - widths[name]) / 2, 2, widths[name], height)
        painter.drawImage(target, image, bounds[name])
        painter.end()
        aligned[name] = canvas
    return aligned


def align_character_sequences(images, sequences):
    """Align every frame of a state with one transform, preserving motion within a clip."""
    if not sequences:
        return align_characters(images), {}
    bounds = {}
    for name, image in images.items():
        state_frames = sequences.get(name)
        if state_frames:
            rect = character_bounds(state_frames[0])
            for frame in state_frames[1:]:
                rect = rect.united(character_bounds(frame))
            bounds[name] = rect
        else:
            bounds[name] = character_bounds(image)
    height = character_bounds(images["idle"]).height()
    widths = {name: rect.width() * height / rect.height() for name, rect in bounds.items()}
    canvas_width, canvas_height = math.ceil(max(widths.values())) + 4, int(height) + 4

    def draw(name, image):
        canvas = QImage(canvas_width, canvas_height, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = QRectF((canvas_width - widths[name]) / 2, 2, widths[name], height)
        painter.drawImage(target, image, bounds[name])
        painter.end()
        return canvas

    aligned = {name: draw(name, image) for name, image in images.items()}
    # The pet is at most 220 logical pixels high. A 768 px playback cache
    # stays sharp on high-DPI screens without duplicating every full-size PNG.
    cache_height = min(canvas_height, ANIMATION_CACHE_HEIGHT)
    aligned_sequences = {name: tuple(draw(name, frame).scaledToHeight(
        cache_height, Qt.TransformationMode.SmoothTransformation)
        for frame in frames) for name, frames in sequences.items()}
    return aligned, aligned_sequences


class CharacterAssets:
    """加载时统一角色高度、画布和脚底锚点；状态切换只取缓存。"""

    def __init__(self, idle_path=CHARACTER_PATH):
        idle_path = Path(idle_path)
        directory = idle_path.parent
        # 兼容升级前的素材；不是为缺失表情生成或复制图片。
        if not idle_path.exists() and (directory / "gpt_assistant.png").is_file():
            idle_path = directory / "gpt_assistant.png"
        idle = load_character(idle_path, crop=False)
        character_bounds(idle)
        self.images = {"idle": idle}
        self.unavailable = {}
        for state in CharacterState:
            if state == CharacterState.IDLE:
                continue
            path = directory / f"{state.value}.png"
            try:
                image = load_character(path, crop=False)
                character_bounds(image)
                self.images[state.value] = image
            except ValueError as error:
                self.unavailable[state.value] = str(error)
        # A numbered PNG sequence takes precedence over the single state PNG.
        # Each clip is decoded and aligned once, before the display timer starts.
        self.frames = {}
        self.frame_rates = {}
        self.invalid_animations = {}
        manifest_path = directory / "animations" / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("动画帧率配置必须是 JSON 对象。")
                default_fps = manifest.get("default_fps", 12)
                rates = manifest.get("fps", {})
                if not isinstance(rates, dict) or not isinstance(default_fps, (int, float)):
                    raise ValueError("动画帧率配置格式错误。")
                for name, rate in rates.items():
                    if name not in CharacterState._value2member_map_:
                        continue
                    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
                        raise ValueError(f"动画 {name} 的 fps 必须是正数。")
                if not math.isfinite(default_fps) or default_fps <= 0:
                    raise ValueError("default_fps 必须是正数。")
                self.frame_rates = {name: rates.get(name, default_fps)
                                    for name in CharacterState._value2member_map_}
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                self.invalid_animations["manifest"] = str(error)
        for state in CharacterState:
            frame_dir = directory / "animations" / state.value
            paths = sorted(
                (path for path in frame_dir.glob("*.png") if path.stem.isdecimal()),
                key=lambda path: int(path.stem),
            ) if frame_dir.is_dir() else []
            if not paths:
                continue
            try:
                frames = []
                source_size = None
                for path in paths:
                    frame = load_character(path, crop=False)
                    if source_size is None:
                        source_size = frame.size()
                    elif frame.size() != source_size:
                        raise ValueError(f"动画 {state.value} 的所有帧必须使用相同画布。")
                    character_bounds(frame)
                    if frame.height() > ANIMATION_CACHE_HEIGHT:
                        frame = frame.scaledToHeight(
                            ANIMATION_CACHE_HEIGHT, Qt.TransformationMode.SmoothTransformation)
                    frames.append(frame)
                frames = tuple(frames)
            except ValueError as error:
                self.invalid_animations[state.value] = str(error)
                continue
            self.frames[state.value] = frames
            self.images[state.value] = frames[0]
            self.unavailable.pop(state.value, None)
        self.images, self.frames = align_character_sequences(self.images, self.frames)


class CharacterAnimation(QObject):
    """PNG 状态控制器。窗口只调用状态/绘制接口，未来可替换渲染后端。"""

    changed = Signal()
    state_changed = Signal(str)
    BLINK_DURATION = 0.16
    HAPPY_DURATION = 1.0

    def __init__(self, images, rect, parent=None, rng=None, frames=None,
                 frame_rate=12, frame_rates=None):
        super().__init__(parent)
        self.images = dict(images)
        self.pixmaps = {name: QPixmap.fromImage(image) for name, image in images.items()}
        self.frames = {name: tuple(clip) for name, clip in (frames or {}).items()}
        self.frame_pixmaps = {name: tuple(QPixmap.fromImage(frame) for frame in clip)
                              for name, clip in self.frames.items()}
        self.frame_rate = frame_rate
        self.frame_rates = dict(frame_rates or {})
        self.frame_elapsed = 0.0
        self.rng = rng or random.Random()
        self.state = CharacterState.IDLE
        self.state_remaining = None
        self.blink_remaining = self.rng.uniform(3.0, 6.0)
        self.base_rect = QRectF(rect)
        self.elapsed = 0.0
        self.held = False
        self.hovered = False
        self.hover_amount = 0.0
        self.click_elapsed = 0.22
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.clock.start()
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def _tick(self):
        self.advance(self.clock.restart() / 1000.0)

    def advance(self, seconds):
        if self.held:
            return
        self.elapsed += seconds
        self.frame_elapsed += seconds
        self.click_elapsed = min(0.22, self.click_elapsed + seconds)
        self.hover_amount += (float(self.hovered) - self.hover_amount) * (1 - math.exp(-seconds / 0.1))
        if self.state_remaining is not None:
            self.state_remaining -= seconds
            if self.state_remaining <= 0:
                self.set_state(CharacterState.IDLE)
        elif self.state == CharacterState.IDLE:
            self.blink_remaining -= seconds
            if self.blink_remaining <= 0:
                self.set_state(CharacterState.BLINK)
        self.changed.emit()

    @property
    def displayed_state(self):
        fallbacks = {
            'embarrassed': ('thinking', 'idle'),
            'shy_angry': ('embarrassed', 'thinking', 'idle'),
            'angry': ('shy_angry', 'thinking', 'idle'),
            'strong_angry': ('angry', 'shy_angry', 'thinking', 'idle'),
            'sleep': ('idle',),
        }
        if self.state.value not in self.images:
            for name in fallbacks.get(self.state.value, ('idle',)):
                if name in self.images:
                    return name
        return self.state.value if self.state.value in self.images else "idle"

    @property
    def image(self):
        name = self.displayed_state
        frames = self.frames.get(name)
        return frames[self.frame_index] if frames else self.images[name]

    @property
    def frame_index(self):
        frames = self.frames.get(self.displayed_state)
        fps = self.frame_rates.get(self.displayed_state, self.frame_rate)
        return int(self.frame_elapsed * fps) % len(frames) if frames else 0

    def set_state(self, state):
        """talk/thinking 持续到下一次调用；happy/blink 自动恢复 idle。

        state 是逻辑状态，displayed_state 是缺图回退后的实际图片。
        显式状态切换会覆盖旧的恢复计时，不会被之前的 happy/blink 打断。
        """
        state = CharacterState(state)
        self.state = state
        self.frame_elapsed = 0.0
        self.state_remaining = {
            CharacterState.BLINK: self.BLINK_DURATION,
            CharacterState.HAPPY: self.HAPPY_DURATION,
        }.get(state)
        if state == CharacterState.IDLE:
            self.blink_remaining = self.rng.uniform(3.0, 6.0)
        self.state_changed.emit(state.value)
        self.changed.emit()

    def hold(self):
        # 从按下起冻结姿态，保证鼠标与所抓住的角色部位相对稳定。
        self.held = True

    def interact(self, expression, duration_ms, persistent=False):
        # 同等级连点只刷新互动，不打断正在播放的表情片段。
        if self.state != CharacterState(expression):
            self.set_state(expression)
        self.state_remaining = None if persistent else duration_ms / 1000.0
        self.click_elapsed = 0.0

    def set_hovered(self, hovered):
        self.hovered = hovered

    def release(self, clicked):
        self.held = False
        self.click_elapsed = 0.22
        self.clock.start()
        if clicked:
            self.set_state(CharacterState.HAPPY)

    def current_rect(self):
        phase = self.elapsed
        breathing = 0.002 * (1 - math.cos(math.tau * phase / 5.6))
        scale = (1 + breathing) * (1 + 0.025 * self.hover_amount)
        scale *= 1 + 0.03 * math.sin(math.pi * self.click_elapsed / 0.22) ** 2
        width, height = self.base_rect.width() * scale, self.base_rect.height() * scale
        # 脚底为缩放锚点；避免呼吸时脚底上下跳动。
        return QRectF(self.base_rect.center().x() - width / 2,
                      self.base_rect.bottom() - height, width, height)

    def contains(self, position, alpha_threshold=24):
        rect = self.current_rect()
        if not rect.contains(position):
            return False
        x = int((position.x() - rect.x()) * self.image.width() / rect.width())
        y = int((position.y() - rect.y()) * self.image.height() / rect.height())
        return (0 <= x < self.image.width() and 0 <= y < self.image.height()
                and self.image.pixelColor(x, y).alpha() >= alpha_threshold)

    def paint(self, painter):
        name = self.displayed_state
        frames = self.frame_pixmaps.get(name)
        pixmap = frames[self.frame_index] if frames else self.pixmaps[name]
        painter.drawPixmap(self.current_rect(), pixmap, QRectF(pixmap.rect()))

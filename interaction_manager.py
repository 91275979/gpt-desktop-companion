"""轻量交互决策：只返回台词、表情和时长，不操作界面或请求网络。"""
from dataclasses import dataclass
import random
import time
import math
from enum import Enum

FAST_CLICK_INTERVAL = 0.45
COMBO_BREAK_INTERVAL = 0.90
ANGER_HOLD_TIME = 2.5
FULL_RESET_TIME = 6.0
SLEEP_AFTER_IDLE = 30.0
ANGER_STAGE_COUNT = 5
ANGER_STAGE_TARGETS = (3, 4)
WEATHER_REMINDER_INTERVAL = 4 * 60 * 60
WEATHER_CHANGED_INTERVAL = 30 * 60


def weather_dialogue(snapshot):
    """简短的规则型穿衣提醒，便于角色气泡阅读。"""
    temp = min(snapshot.temperature, snapshot.apparent)
    if temp < 5: outfit = '穿厚外套保暖'
    elif temp < 12: outfit = '穿外套和长袖'
    elif temp < 20: outfit = '穿薄外套和长袖'
    elif temp <= 28: outfit = '穿短袖薄衣'
    else: outfit = '穿轻薄透气衣物'
    text = f'体感{snapshot.apparent:g}℃，{outfit}。'
    if snapshot.rain_probability >= 40 or snapshot.precipitation > 0 or snapshot.code >= 51:
        text += '记得带伞。'
    if snapshot.wind >= 25:
        text += '注意防风。'
    return text


class MoodState(str, Enum):
    CALM = 'CALM'
    ANGER_1 = 'ANGER_1'
    ANGER_2 = 'ANGER_2'
    ANGER_3 = 'ANGER_3'
    ANGER_4 = 'ANGER_4'
    ANGER_5 = 'ANGER_5'


ANGER_LINES = {
    0: ('嗯？怎么连续戳我呀？', '怎么啦，主人？'),
    1: ('嗯？', '主人怎么一直点我……', '怎么啦？', '你是不是在戳我？'),
    2: ('别一直点我呀……', '主人真是的……', '怎么还在点……', '我都注意到了啦。'),
    3: ('别、别一直戳啦！', '我会害羞的……', '主人不要闹啦！', '你是不是故意的……'),
    4: ('主人真的很过分！', '还在点？！', '再这样我要生气了！', '不许再戳我啦！'),
    5: ('还点？！', '我真的生气啦！', '再点我就不理你了！', '主人太坏了！', '不要一直欺负我啦！', '我、我真的要生气了！'),
}
ANGER_EXPRESSIONS = ('thinking', 'thinking', 'embarrassed', 'shy_angry', 'angry', 'strong_angry')


LINES = {
    'greeting': ('主人好～', '今天也一起加油吧。', '我一直都在哦。'),
    'weather': ('要看看今天的天气吗？', '出门前记得看看天气哦。'),
    'usage': ('刚刚又用了点额度。', '我有在帮你看使用情况。'),
    'market': ('今天市场也在波动呢。', '要看看主要指数吗？'),
    'idle': ('你是不是又点我了？', '嗯？', '我有在认真工作哦。', '要休息一下吗？'),
}


@dataclass(frozen=True)
class Interaction:
    text: str
    expression: str
    duration_ms: int
    category: str


class InteractionManager:
    def __init__(self, rng=None, clock=time.monotonic):
        self.rng, self.clock = rng or random.Random(), clock
        self.last_click_time = None
        # 启动即开始空闲计时；情绪恢复不能清除这个时间戳。
        self.last_interaction_time = self.clock()
        self.fast_click_mode = False
        self.stage_progress = 0
        self.stage_target = self.rng.choice(ANGER_STAGE_TARGETS)
        self.anger_level = 0
        self._held_level = 0
        self.click_count = 0
        self.last_text = None
        self.quota_changed_at = None
        self.pending_weather = None
        self.last_weather_reminder = None
        self.last_weather_message = None

    def receive_weather(self, snapshot, error=''):
        # 错误时页面可以保留旧数据，但不据此发送新的天气提醒。
        self.pending_weather = None if error else snapshot

    def automatic_weather_dialogue(self, blocked=False):
        snapshot = self.pending_weather
        if snapshot is None:
            return None
        if not 0 <= time.time()-snapshot.fetched_at < 3600:
            self.pending_weather = None
            return None
        if blocked or self.fast_click_mode:
            return None
        text = weather_dialogue(snapshot)
        signature = (snapshot.location, text)
        elapsed = (self.clock()-self.last_weather_reminder
                   if self.last_weather_reminder is not None else float('inf'))
        changed = signature != self.last_weather_message
        if elapsed < (WEATHER_CHANGED_INTERVAL if changed else WEATHER_REMINDER_INTERVAL):
            return None
        self.last_weather_reminder = self.clock()
        self.last_weather_message = signature
        self.pending_weather = None
        return Interaction(text, 'thinking', 4500, 'weather')

    def idle_seconds(self):
        """返回距最近一次左键互动的秒数；启动后从零开始计时。"""
        if self.last_interaction_time is None:
            return 0.0
        return max(0.0, self.clock() - self.last_interaction_time)

    def quota_changed(self):
        self.quota_changed_at = self.clock()

    @property
    def mood_state(self):
        return MoodState(f'ANGER_{self.anger_level}') if self.anger_level else MoodState.CALM

    @property
    def expression(self):
        return ANGER_EXPRESSIONS[self.anger_level] if self.fast_click_mode else 'idle'

    def advance(self):
        """按真实闲置时间冷却；与气泡寿命、动画帧数无关。"""
        if self.last_interaction_time is None:
            return
        quiet = self.clock() - self.last_interaction_time
        if quiet > COMBO_BREAK_INTERVAL and self.anger_level < ANGER_STAGE_COUNT:
            self.stage_progress = 0
        if not self.fast_click_mode:
            return
        if quiet >= FULL_RESET_TIME:
            self.fast_click_mode = False
            self.anger_level = self._held_level = self.stage_progress = 0
            self.last_click_time = None
            self.click_count = 0
            self.stage_target = self.rng.choice(ANGER_STAGE_TARGETS)
        elif quiet > ANGER_HOLD_TIME:
            self.anger_level = math.ceil(self._held_level *
                (FULL_RESET_TIME-quiet)/(FULL_RESET_TIME-ANGER_HOLD_TIME))

    def weights(self, weather=None, market_quotes=(), now=None):
        now = time.time() if now is None else now
        weights = {'greeting': 3, 'idle': 3}
        if weather and 0 <= now-weather.fetched_at < 3600:
            weights['weather'] = 4
        if self.quota_changed_at is not None and self.clock()-self.quota_changed_at < 120:
            weights['usage'] = 9
        if weather and now-weather.fetched_at < 3600 and (
            weather.apparent < 5 or weather.apparent > 28 or weather.rain_probability >= 40
            or weather.precipitation > 0 or weather.wind >= 25):
            weights['weather'] = 9
        if any(0 <= now-q.fetched_at < 180 for q in market_quotes):
            weights['market'] = 7
        return weights

    def click(self, weather=None, market_quotes=()):
        self.advance()
        stamp = self.clock()
        interval = stamp-self.last_click_time if self.last_click_time is not None else float('inf')
        self.click_count = self.click_count+1 if interval <= COMBO_BREAK_INTERVAL else 1
        if interval <= FAST_CLICK_INTERVAL:
            self.fast_click_mode = True
            if self.anger_level < ANGER_STAGE_COUNT:
                self.stage_progress += 1
                if self.stage_progress >= self.stage_target:
                    self.anger_level += 1
                    self.stage_progress = 0
                    self.stage_target = self.rng.choice(ANGER_STAGE_TARGETS)
        self.last_click_time = self.last_interaction_time = stamp
        self._held_level = self.anger_level
        if self.fast_click_mode:
            category = self.mood_state.value if self.anger_level else 'fast_click'
            text = self.rng.choice([line for line in ANGER_LINES[self.anger_level] if line != self.last_text])
            expression = self.expression
        else:
            weights = self.weights(weather, market_quotes)
            if weather is not None and weather_dialogue(weather) == self.last_text:
                weights.pop('weather', None)
            category = self.rng.choices(list(weights), weights=list(weights.values()))[0]
            text = self.rng.choice([line for line in LINES[category] if line != self.last_text])
            if category == 'weather' and weather is not None:
                text = weather_dialogue(weather)
            expression = {'greeting': 'happy', 'weather': 'thinking', 'usage': 'talk',
                          'market': 'thinking', 'idle': 'idle'}[category]
        self.last_text = text
        return Interaction(text, expression, self.rng.randint(1500, 2500), category)

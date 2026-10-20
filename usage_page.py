"""展示 tracker 快照的详情卡片，不读取账户或网络数据。"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QFrame, QProgressBar
from usage_popup import cost_text


class UsagePage(QWidget):
    WIDTH = 230
    GAP = 9

    def __init__(self, owner):
        super().__init__(owner)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        title_row = QHBoxLayout()
        title_row.setSpacing(5)
        self.add_label(title_row, "Usage", "font-size: 15px; font-weight: 600;")
        self.subtitle = self.add_label(title_row, "Codex 额度", "color: #999; font-size: 9px;")
        title_row.addStretch()
        self.updated_at_label = self.add_label(title_row, "尚未更新", "color: #888; font-size: 8px;")
        self.updated_at_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(title_row)
        self.cards = {}
        cards_row = QVBoxLayout()
        cards_row.setSpacing(4)
        for period, title in (("5h", "5 小时"), ("week", "每周")):
            card = QFrame()
            card.setMinimumWidth(0)
            card.setFixedHeight(45)
            card.setObjectName("quotaCard")
            card.setStyleSheet("QFrame#quotaCard { background: rgba(255,255,255,9); border: 1px solid #48484b; border-radius: 9px; }")
            inner = QVBoxLayout(card)
            inner.setContentsMargins(7, 2, 7, 3)
            inner.setSpacing(0)
            summary = QHBoxLayout()
            summary.setSpacing(4)
            self.add_label(summary, title, "color: #bbb; font-size: 9px;")
            summary.addStretch()
            remaining = self.add_label(summary, "暂不可用", "font-size: 14px; font-weight: 600;")
            inner.addLayout(summary)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            bar.setStyleSheet("QProgressBar { border: none; background: #48484c; border-radius: 2px; } QProgressBar::chunk { background: #c5c5cb; border-radius: 2px; }")
            inner.addWidget(bar)
            detail = self.add_label(inner, "", "color: #aaa; font-size: 8px;")
            cards_row.addWidget(card)
            self.cards[period] = (card, remaining, detail, bar)
        layout.addLayout(cards_row)
        self.quota_five = self.cards["5h"][1]
        self.quota_week = self.cards["week"][1]
        self.recent_title = self.add_label(layout, "最近变化 · 近 1 分钟", "color: #aaa; font-size: 9px;")
        self.recent_label = self.add_label(layout, "暂无变化", "font-size: 10px;")
        self.quota_status = self.add_label(layout, "额度数据暂不可用", "color: #999; font-size: 9px;")
        self.token_unavailable = self.add_label(layout, "Token\n暂不可用", "color: #888; font-size: 11px;")
        self.token_area = QWidget()
        token_layout = QVBoxLayout(self.token_area)
        token_layout.setContentsMargins(0, 0, 0, 0)
        token_layout.setSpacing(3)
        self.values = {}
        for key, title in (("session", "本次会话 Token"), ("today", "今日 Token"),
                           ("split", "Input / Output"), ("cost", "估算费用"), ("rate", "最近使用速度")):
            self.add_label(token_layout, title, "color: #999; font-size: 10px;")
            self.values[key] = self.add_label(token_layout, "—", "font-size: 12px;")
        layout.addWidget(self.token_area)
        self.token_area.hide()
        self.token_unavailable.hide()
        # 矮条模式显示核心数字；完整明细保留在额度卡悬停提示中。
        self.recent_title.hide()
        self.recent_label.hide()
        self.quota_status.hide()
        for card, _, detail, _ in self.cards.values():
            detail.hide()


    def update_quota(self, details, error=None):
        from datetime import datetime
        rows = {row[0].period: row for row in details}
        recent_lines = []
        for period, (card, remaining, detail, bar) in self.cards.items():
            row = rows.get(period)
            card.setVisible(row is not None or not details)
            if row is None:
                continue
            snapshot, recent, stale = row
            unit = {"percent": "%", "tokens": " tokens"}.get(snapshot.unit, "")
            value = f"{snapshot.remaining:g}{unit}" if snapshot.remaining is not None else "未知"
            remaining.setText(f"剩余 {value}")
            reset = datetime.fromtimestamp(snapshot.reset_time).strftime("%m-%d %H:%M") if snapshot.reset_time else "未提供"
            detail.setText(f"已用 {snapshot.used:g}{unit}\n重置 {reset}" + (" · 旧数据" if stale else ""))
            card.setToolTip(f"{remaining.text()}\n{detail.text()}")
            bar.setVisible(snapshot.percentage is not None)
            bar.setValue(round((100-(snapshot.percentage or 0))*10))
            title = "5 小时" if period == "5h" else "每周"
            amount = f"-{recent:g}" if recent else "0"
            recent_lines.append(f"{title}    {amount}{unit}")
        self.recent_label.setText("\n".join(recent_lines) or "暂无变化")
        stamp = max((row[0].fetched_at for row in details), default=None)
        status = "数据更新时间  " + datetime.fromtimestamp(stamp).strftime("%H:%M:%S") if stamp else "额度数据暂不可用"
        if error:
            status = "额度数据暂不可用" + (" · 保留上次结果\n" + status if stamp else "")
        self.quota_status.setText(status)
        if stamp:
            prefix = "上次" if error else "更新"
            self.updated_at_label.setText(f'{prefix} {datetime.fromtimestamp(stamp):%H:%M:%S}')
            self.updated_at_label.setToolTip(status)
        else:
            self.updated_at_label.setText("尚未更新")
            self.updated_at_label.setToolTip(error or "等待额度数据")


    def update_usage(self, snapshot, demo=False):
        available = snapshot.session_total > 0 or snapshot.today_total > 0
        self.subtitle.setText("模拟额度" if demo else "Codex 额度")
        self.token_area.setVisible(available)
        self.token_unavailable.hide()
        self.values["session"].setText(f"{snapshot.session_total:,}")
        self.values["today"].setText(f"{snapshot.today_total:,}")
        self.values["split"].setText(f"{snapshot.input_tokens:,} / {snapshot.output_tokens:,}")
        self.values["cost"].setText(cost_text(snapshot.estimated_cost))
        self.values["rate"].setText(f"约 {snapshot.recent_rate:,.0f} tokens / hour")


    @staticmethod
    def add_label(layout, text, style=""):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(style)
        layout.addWidget(label)
        return label


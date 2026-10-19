"""Yahoo Finance 指数行情适配；只展示数值，不生成投资建议。"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import time
from urllib.parse import quote
from PySide6.QtCore import QObject, QTimer, Signal
from http_client import JsonClient, number

INDICES = (('^GSPC','S&P 500','美国'),('^IXIC','Nasdaq Composite','美国'),('^DJI','Dow Jones','美国'),
           ('000001.SS','上证指数','中国'),('399001.SZ','深证成指','中国'),('000300.SS','沪深300','中国'))


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    name: str
    price: float
    change: float
    percent: float
    market_time: float
    offset: int
    timezone_name: str
    state: str
    fetched_at: float


@dataclass(frozen=True)
class MarketUpdate:
    quotes: tuple
    failed: tuple = ()


def parse_chart(data, symbol, name, now=None):
    now = time.time() if now is None else now
    result = data['chart']['result'][0]
    meta = result['meta']
    if meta['symbol'] != symbol:
        raise ValueError('返回的指数代码不匹配')
    price, stamp = number(meta['regularMarketPrice']), number(meta['regularMarketTime'])
    offset = int(number(meta['gmtoffset']))
    zone = timezone(timedelta(seconds=offset))
    day = datetime.fromtimestamp(stamp,zone).date()
    history = []
    for timestamp, value in zip(result['timestamp'], result['indicators']['quote'][0]['close']):
        if value is not None:
            history.append((number(timestamp),number(value)))
    previous = [v for t,v in sorted(history) if datetime.fromtimestamp(t,zone).date()<day]
    # range=5d 的 chartPreviousClose 通常是五天前，不能拿它当昨日收盘。
    if previous:
        baseline = previous[-1]
    elif len({datetime.fromtimestamp(t,zone).date() for t,v in history}) == 1:
        baseline = number(meta.get('previousClose',meta.get('chartPreviousClose')))
    else:
        raise ValueError('缺少前一交易日收盘值')
    if baseline <= 0 or price <= 0:
        raise ValueError('无效指数值')
    period = meta.get('currentTradingPeriod',{}).get('regular',{})
    start, end = period.get('start'), period.get('end')
    if type(start) in (int,float) and type(end) in (int,float):
        state = '交易中 · 可能延迟' if start <= now <= end else '最近收盘'
    else:
        state = '最近行情'
    local = datetime.fromtimestamp(now,zone)
    if symbol.endswith(('.SS','.SZ')) and state.startswith('交易中') and (11,30) <= (local.hour,local.minute) < (13,0):
        state = '午间休市'
    change = price-baseline
    return MarketQuote(symbol,name,price,change,change/baseline*100,stamp,offset,
                       str(meta.get('timezone',meta.get('exchangeTimezoneName',''))),state,now)


class MarketProvider(QObject):
    updated = Signal(object)

    def __init__(self, minutes=2, parent=None):
        super().__init__(parent)
        self.client = JsonClient(self)
        self.quotes, self.failed, self.pending = {}, set(), set()
        self.timer = QTimer(self)
        self.timer.setInterval(max(1,min(5,minutes))*60000)
        self.timer.timeout.connect(self.refresh)

    def start(self):
        self.refresh()
        self.timer.start()

    def refresh(self):
        if self.pending or self.client.closed:
            return
        self.pending = {s for s,_,_ in INDICES}
        for symbol,name,_ in INDICES:
            url = 'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?interval=1d&range=5d'
            self.client.get(url,lambda data,error,symbol=symbol,name=name:self.received(symbol,name,data,error))

    def received(self,symbol,name,data,error):
        try:
            if error: raise ValueError(error)
            self.quotes[symbol] = parse_chart(data,symbol,name)
            self.failed.discard(symbol)
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,OSError):
            self.failed.add(symbol)
        self.pending.discard(symbol)
        self.updated.emit(MarketUpdate(tuple(self.quotes[s] for s,_,_ in INDICES if s in self.quotes),tuple(self.failed)))

    def stop(self):
        self.timer.stop()
        self.client.close()

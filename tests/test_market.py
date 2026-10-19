import unittest
from copy import deepcopy
from PySide6.QtWidgets import QApplication
from market_provider import MarketProvider, parse_chart, INDICES


def fixture(symbol='^GSPC'):
    start=1700000000
    return {'chart':{'result':[{'meta':{'symbol':symbol,'regularMarketPrice':120,
        'regularMarketTime':start+86400,'gmtoffset':0,'timezone':'UTC','chartPreviousClose':80,
        'currentTradingPeriod':{'regular':{'start':start+86300,'end':start+120000}}},
        'timestamp':[start,start+86400], 'indicators':{'quote':[{'close':[100,120]}]}}]}}


class MarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_change_uses_previous_session_not_range_baseline(self):
        q=parse_chart(fixture(),'^GSPC','S&P 500',1700086400)
        self.assertEqual(q.change,20)
        self.assertEqual(q.percent,20)
        self.assertIn('交易中',q.state)
        closed=parse_chart(fixture(),'^GSPC','S&P 500',1701000000)
        self.assertEqual(closed.state,'最近收盘')

    def test_missing_wrong_symbol_and_nan_are_rejected(self):
        for mutate in (lambda d:d['chart'].update(result=None),
                       lambda d:d['chart']['result'][0]['meta'].update(symbol='OTHER'),
                       lambda d:d['chart']['result'][0]['meta'].update(regularMarketPrice=float('nan'))):
            data=deepcopy(fixture())
            mutate(data)
            with self.assertRaises((ValueError,KeyError,TypeError)):
                parse_chart(data,'^GSPC','Index')

    def test_failure_preserves_success_and_partial_results(self):
        p=MarketProvider()
        events=[]
        p.updated.connect(events.append)
        p.received('^GSPC','S&P 500',fixture(),None)
        original=p.quotes['^GSPC']
        p.received('^GSPC','S&P 500',None,'offline')
        self.assertIs(p.quotes['^GSPC'],original)
        self.assertIn('^GSPC',events[-1].failed)
        p.received('^IXIC','Nasdaq Composite',fixture('^IXIC'),None)
        self.assertEqual(len(events[-1].quotes),2)
        p.stop()

    def test_two_minute_refresh_and_no_overlapping_requests(self):
        p=MarketProvider()
        calls=[]
        p.client.get=lambda url,callback:calls.append((url,callback))
        p.start()
        self.assertEqual(p.timer.interval(),120000)
        self.assertEqual(len(calls),6)
        p.refresh()
        self.assertEqual(len(calls),6)
        for _,callback in calls: callback(None,'offline')
        self.assertFalse(p.pending)
        self.assertEqual(len(p.failed),len(INDICES))
        p.stop()

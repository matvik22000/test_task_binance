import unittest
from unittest.mock import AsyncMock

from binance import *


class BinanceTest(unittest.TestCase):
    class AlertServiceMock:
        def __init__(self):
            self.alert = AsyncMock()

    def test_alert_called(self):
        a = self.AlertServiceMock()
        monitor = SymbolMonitor("test", 0.01, lambda old, new: (old - new) / new,
                                alert_service=a
                                )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(monitor.reg_price(10))
        loop.run_until_complete(monitor.reg_price(100))
        loop.run_until_complete(monitor.reg_price(99))
        a.alert.assert_called()

    def test_alert_not_called(self):
        a = self.AlertServiceMock()
        monitor = SymbolMonitor("test", 0.01, lambda old, new: (old - new) / new,
                                alert_service=a
                                )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(monitor.reg_price(10))
        loop.run_until_complete(monitor.reg_price(100))
        loop.run_until_complete(monitor.reg_price(99.8))
        a.alert.assert_not_called()

    def test_lifetime(self):
        a = self.AlertServiceMock()
        loop = asyncio.new_event_loop()
        monitor = SymbolMonitor("test", 0.01, lambda old, new: (old - new) / new,
                                alert_service=a
                                )
        h = monitor._storage._price_history
        h[100] = PriceAtTime(100, datetime.datetime.now())
        h[500] = PriceAtTime(500, datetime.datetime.now() - datetime.timedelta(hours=1, minutes=1))
        monitor._storage._max_key = 500
        loop.run_until_complete(monitor.reg_price(101))
        assert len(h) == 3

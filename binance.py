import abc
import asyncio
import datetime
import json
import typing as tp
from dataclasses import dataclass

import websockets

symbols_config = [
    {
        "symbol": "xrpusdt",
        "alert_threshold": 0.01
    }
]
# Это легко можно вынести в отдельный файл
BASE_URL = 'wss://stream.binance.com:9443/stream'

DROP_RELATIVE = lambda old, new: (old - new) / new


# Можно использовать любые другие метрики
# Например, вдруг нам захочется реагировать не на пададение, а на увеличение

class AbstractAlertService(abc.ABC):
    """
    Сервис, отвечающий за уведомления о событиях
    Можно легко добавить другие реализации (например сервис уведомлений в телеграм,
    писать в файл или сразу совершать какое-то полезное действие)


    """

    @abc.abstractmethod
    async def alert(self, msg):
        raise NotImplementedError()


class ConsoleAlertService(AbstractAlertService):
    """
    Консольная реализация сервиса уведомлений

    """

    async def alert(self, msg):
        print(f'{datetime.datetime.now()}: {msg}')


class AbstractSymbolStorage(abc.ABC):
    """
    Сервис, отвечающий за сохранение цены
    Простая реализация через хранение максимума имеет недостатки:
    например, при перезапуске приложения история пропадает.
    Можно добавить реализацию через базу данных

    """

    @abc.abstractmethod
    async def store(self, price: float):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_price(self):
        raise NotImplementedError()


@dataclass(order=True)
class PriceAtTime:
    price: float
    datetime: datetime


class LocalSymbolStorage(AbstractSymbolStorage):
    """
    Реализация сервиса для сохранения цены
    """
    lifetime: datetime.timedelta

    def __init__(self, lifetime: datetime.timedelta):
        self.lifetime = lifetime
        self._price_history = {-1.0: PriceAtTime(-1, datetime.datetime.now())}
        self._max_key = -1.0

    async def store(self, price: PriceAtTime) -> None:
        # Этот метод должен работать за O(log(n)), но я не нашел простого способа
        # добиться этого в питоне. Мне кажется, сюда идеально вписалась бы TreeMap
        # Где в корне всегда был бы максимальный элемент, достать его можно было бы
        # за O(1), добавить новый или обновить старый можно было бы за O(log(n))
        # Но я не смог найти подходящую реализацию, а писать свою мне кажется
        # не совсем то, что предполагалось в тестовом задании
        # Поэтому вставка работает за O(n) (в среднем)
        while True:
            top = self._price_history.get(self._max_key)
            if price.datetime - top.datetime > self.lifetime:
                self._price_history.pop(self._max_key)
                self._max_key = max(self._price_history.keys())
            else:
                break
        self._price_history[price.price] = price
        self._max_key = max(price.price, self._max_key)

    def get_price(self) -> float:
        # По-хорошему, проверять то, что значение не просрочено, нужно здесь
        # Но это замедлит получение значения, что для нас критично
        # Так как обновления происходят достаточно часто (порядка раз в несколько секунд)
        # Получаемая в худшем случае ошибка будет такого же порядка, что,
        # при значении lifetime в 1 час, мне кажется, пренебрежимо мало
        return self._max_key


class SymbolMonitor:
    """
    Каждый объект этого класса следит за своим символом
    В нём вся логика, связанная с подсчётом отклонения и отправкой уведомлений

    """
    threshold: float
    calc: tp.Callable
    symbol: str

    def __init__(self, symbol: str, threshold: float, calc: tp.Callable, *, alert_service: AbstractAlertService,
                 storage=None):
        if not storage:
            self._storage = LocalSymbolStorage(datetime.timedelta(hours=1))
        else:
            self._storage = storage
        self._alert_service = alert_service
        self.symbol = symbol
        self.threshold = threshold
        self.calc = calc

    async def reg_price(self, price: float):
        stored = self._storage.get_price()
        diff = self.calc(stored, price)
        # Тут очень хочется логировать происходящее
        # Но в текущем виде оно сольется с принтами из alertService, поэтому ничего не выводим
        # print(f'reg {self.symbol} for {price} at {datetime.datetime.now()}; diff {diff}')
        if diff > self.threshold:
            await self._alert_service.alert(
                f'цена на {self.symbol} изменилась на {diff * 100:.2f}%'
            )
        await self._storage.store(PriceAtTime(price, datetime.datetime.now()))


def init_monitors(config):
    """
    Создаем объект мониторинга для каждого символа
    :return кортеж из списка символов и хендлера для событий изменения цены
    """
    alert_service = ConsoleAlertService()
    monitors = {}
    for symbol_config in config:
        symbol, threshold = symbol_config.get('symbol'), symbol_config.get('alert_threshold')
        stream_name = f'{symbol_config.get("symbol")}@trade'
        monitors[stream_name] = SymbolMonitor(symbol, threshold, DROP_RELATIVE,
                                              alert_service=alert_service)

    async def handler(msg):
        parsed = json.loads(msg)
        stream = parsed.get("stream")
        monitor = monitors[stream]
        if not monitor:
            raise Exception(f"Monitor for stream {stream} not created")
        await monitor.reg_price(float(parsed.get('data').get('p')))

    return monitors.keys(), handler


async def create_websocket(symbols, handler):
    """
    Открываем веб сокет и бесконечно слушаем его

    """
    url = f'{BASE_URL}?streams={"/".join(symbols)}'
    print('connecting to:', url)
    async with websockets.connect(url) as ws:
        while True:
            msg = await ws.recv()
            await handler(msg)


if __name__ == '__main__':
    url, handler = init_monitors(symbols_config)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_websocket(url, handler))
"""
Отвечая на 2 часть задания, я постарался сделать приложение модульным и масштабируемым
Добавить отслеживание любого количества пар очень легко - достаточно изменить symbols_config 
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
from random import choice


@dataclass
class Order:  # Our own placed order
    timestamp: float
    id: int
    side: str
    size: float
    price: float


@dataclass
class AnonTrade:  # Market trade
    timestamp: float
    side: str
    size: float
    price: float


@dataclass
class OwnTrade:  # Execution of own placed order
    timestamp: float
    trade_id: int
    order_id: int
    side: str
    size: float
    price: float


@dataclass
class OrderbookSnapshotUpdate:  # Orderbook tick snapshot
    timestamp: float
    ask: list  # list[price, size]
    bid: list


@dataclass
class MdUpdate:  # Data of a tick
    orderbook: Optional[OrderbookSnapshotUpdate] = None
    trades: Optional[list] = None


class Strategy:
    def __init__(self, max_position: float) -> None:
        self.max_pos = max_position

    def run(self, sim):
        id = 0
        while True:
            try:
                md_update = sim.tick()
                sim.place_order(id, md_update, self.max_pos)
                sim.cancel_order(md_update.orderbook.timestamp)

            except StopIteration:
                break

            id += 1


def load_md_from_file(path_trades: str, path_lobs: str, ticks_number: int):  # ticks_number is a number of
    trades = pd.read_csv(path_trades)  # order book updates
    lobs = pd.read_csv(path_lobs)
    lobs = lobs[['receive_ts', 'btcusdt:Binance:LinearPerpetual_ask_price_0',
                 'btcusdt:Binance:LinearPerpetual_ask_vol_0',
                 'btcusdt:Binance:LinearPerpetual_bid_price_0',
                 'btcusdt:Binance:LinearPerpetual_bid_vol_0']]
    timeline_trades = trades['receive_ts']
    timeline_lobs = lobs['receive_ts']
    md = []
    ind_trades = 0
    for ind_lobs in range(ticks_number):
        orderbook = OrderbookSnapshotUpdate(float(timeline_lobs[ind_lobs]),
                                            [float(lobs[lobs['receive_ts'] == timeline_lobs[ind_lobs]][
                                                       'btcusdt:Binance:LinearPerpetual_ask_price_0']),
                                             float(lobs[lobs['receive_ts'] == timeline_lobs[ind_lobs]][
                                                       'btcusdt:Binance:LinearPerpetual_ask_vol_0'])],
                                            [float(lobs[lobs['receive_ts'] == timeline_lobs[ind_lobs]][
                                                       'btcusdt:Binance:LinearPerpetual_bid_price_0']),
                                             float(lobs[lobs['receive_ts'] == timeline_lobs[ind_lobs]][
                                                       'btcusdt:Binance:LinearPerpetual_bid_vol_0'])])

        trades_list = []
        while timeline_trades[ind_trades] <= timeline_lobs[ind_lobs]:
            trade = trades[trades['receive_ts'] == timeline_trades[ind_trades]]
            side = 'ASK' if 'ASK' in str(trade['aggro_side']) else 'BID'
            trades_list.append(AnonTrade(float(trade['receive_ts']), side,
                                         float(trade['size']), float(trade['price'])))
            ind_trades += 1
        md.append(MdUpdate(orderbook, trades_list))

    return md


class Sim:
    def __init__(self, execution_latency: float, md_latency: float, t_0: float) -> None:
        self.md = iter(load_md_from_file("trades.csv", "lobs.csv", 1000))
        self.execution_latency = execution_latency
        self.t_0 = t_0
        self.orders_market = {}  # orders that are already placed to the market {id: order}
        self.orders_queue = []  # orders, waiting latency
        self.trade_id = 0
        self.trades = []

    def tick(self) -> MdUpdate:
        md = next(self.md)
        time = md.orderbook.timestamp

        self.execute_orders(md.trades)
        self.prepare_orders(time)

        return md

    def prepare_orders(self, time: float):
        while True:
            if len(self.orders_queue) != 0 and self.orders_queue[0].timestamp + self.execution_latency <= time:
                if self.orders_queue[0].side == 'cancel':
                    if self.orders_queue[0].id in self.orders_market:
                        self.orders_market.pop(self.orders_queue[0].id)
                else:
                    self.orders_market[self.orders_queue[0].id] = self.orders_queue[0]
                self.orders_queue.pop(0)
            else:
                break

    def execute_orders(self, trades):
        for trade in trades:
            for key in self.orders_market:
                if ((trade.side == 'ASK' and self.orders_market[key].side == 'BID'
                        and self.orders_market[key].price >= trade.price) or
                    (trade.side == 'BID' and self.orders_market[key].side == 'ASK'
                        and self.orders_market[key].price <= trade.price)):
                    executed_trade = OwnTrade(trade.timestamp, self.trade_id,
                                              self.orders_market[key].id,
                                              self.orders_market[key].side, self.orders_market[key].size,
                                              trade.price)
                    self.trades.append(executed_trade)
                    self.trade_id += 1
                    self.orders_market.pop(key)
                    break

    def place_order(self, id, md_update, max_pos):  # we assuming that vol of each order = 0.1
        time = md_update.orderbook.timestamp
        side = choice(['ASK', 'BID'])

        if side == 'ASK':
            order = Order(time, id, 'ASK', 0.1, md_update.orderbook.ask[0])
        else:
            order = Order(time, id, 'BID', 0.1, md_update.orderbook.bid[0])

        pos = 0
        for key in self.orders_market:
            if self.orders_market[key].side == 'BID':
                pos += self.orders_market[key].size
            else:
                pos -= self.orders_market[key].size

        if pos <= max_pos:
            self.orders_queue.append(order)

    def cancel_order(self, time: float):
        for id in self.orders_market:
            if self.orders_market[id].timestamp + self.t_0 <= time:
                dead_order = self.orders_market[id]
                dead_order.side = 'cancel'
                self.orders_queue.append(dead_order)


if __name__ == "__main__":
    strategy = Strategy(10)
    sim = Sim(10, 10, 10**10)
    strategy.run(sim)

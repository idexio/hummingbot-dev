#!/usr/bin/env python

import io
from os.path import (
    realpath,
    join
)
import json
import logging
import traceback
from typing import Optional, List, Dict, Any
import asyncio

from hummingbot.client.config.global_config_map import global_config_map
from hummingbot.logger import (
    HummingbotLogger,
    log_encoder
)
from hummingbot.logger.log_server_client import LogServerClient
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.client.platform import client_system, installation_type

VERSIONFILE = realpath(join(__file__, "../../VERSION"))
CLIENT_VERSION = open(VERSIONFILE, "rt").read()


class ReportingProxyHandler(logging.Handler):
    _rrh_logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._rrh_logger is None:
            cls._rrh_logger = logging.getLogger(__name__)
        return cls._rrh_logger

    def __init__(self,
                 level: int = logging.ERROR,
                 proxy_url: str = "http://127.0.0.1:9000",
                 enable_order_event_logging: bool = False,
                 capacity: int = 1):
        super().__init__()
        self.setLevel(level)
        self._enable_order_event_logging: bool = enable_order_event_logging
        self._log_queue: list = []
        self._event_queue: list = []
        self._logged_order_events: List[Dict] = []
        self._capacity: int = capacity
        self._proxy_url: str = proxy_url
        self._log_server_client: Optional[LogServerClient] = None
        self._send_aggregated_metrics_loop_task = None
        if global_config_map["heartbeat_enabled"].value:
            self._send_aggregated_metrics_loop_task = safe_ensure_future(
                self.send_aggregated_metrics_loop(float(global_config_map["heartbeat_interval_min"].value)))

    @property
    def log_server_client(self):
        if not self._log_server_client:
            self._log_server_client = LogServerClient.get_instance(log_server_url=self._proxy_url)
        return self._log_server_client

    @property
    def instance_id(self):
        return global_config_map["instance_id"].value or ""

    def emit(self, record):
        if record.__dict__.get("do_not_send", False):
            return
        if not self.log_server_client.started:
            self.log_server_client.start()
        log_type = record.__dict__.get("message_type", "log")
        if not log_type == "event":
            self.process_log(record)
        else:
            self.process_event(record)
        self.flush()

    def formatException(self, ei):
        """
        Format and return the specified exception information as a string.

        This default implementation just uses
        traceback.print_exception()
        """
        sio = io.StringIO()
        tb = ei[2]
        # See issues #9427, #1553375 in python logging. Commented out for now.
        # if getattr(self, 'fullstack', False):
        #     traceback.print_stack(tb.tb_frame.f_back, file=sio)
        traceback.print_exception(ei[0], ei[1], tb, None, sio)
        s = sio.getvalue()
        sio.close()
        if s[-1:] == "\n":
            s = s[:-1]
        return s

    def process_log(self, log):
        message = {
            "name": log.name,
            "funcName": log.funcName,
            "msg": log.getMessage(),
            "created": log.created,
            "level": log.levelname
        }
        if log.exc_info:
            message["exc_info"] = self.formatException(log.exc_info)
            message["exception_type"] = str(log.exc_info[0])
            message["exception_msg"] = str(log.exc_info[1])

        if not message.get("msg"):
            return
        self._log_queue.append(message)

    def process_event(self, log):
        message = {
            "name": log.name,
            "funcName": log.funcName,
            "msg": log.getMessage(),
            "created": log.created,
            "level": log.levelname
        }
        if log.exc_info:
            message["exc_info"] = self.formatException(log.exc_info)
            message["exception_type"] = str(log.exc_info[0])
            message["exception_msg"] = str(log.exc_info[1])

        if not message.get("msg"):
            return
        self._event_queue.append(message)
        if "PaperTrade" not in log.dict_msg["event_source"]:
            self._logged_order_events.append(log.dict_msg)

    def send_logs(self, logs):
        if not self._enable_order_event_logging:
            return
        request_obj = {
            "url": f"{self._proxy_url}/logs",
            "method": "POST",
            "request_obj": {
                "headers": {
                    'Content-Type': "application/json"
                },
                "data": json.dumps(logs, default=log_encoder),
                "params": {"ddtags": f"instance_id:{self.instance_id},"
                                     f"client_version:{CLIENT_VERSION},"
                                     f"type:log",
                           "ddsource": "hummingbot-client"}
            }
        }
        self.log_server_client.request(request_obj)

    def send_events(self, logs):
        request_obj = {
            "url": f"{self._proxy_url}/order-event",
            "method": "POST",
            "request_obj": {
                "headers": {
                    'Content-Type': "application/json"
                },
                "data": json.dumps(logs, default=log_encoder),
                "params": {"ddtags": f"instance_id:{self.instance_id},"
                                     f"client_version:{CLIENT_VERSION},"
                                     f"type:log",
                           "ddsource": "hummingbot-client"}
            }
        }
        self.log_server_client.request(request_obj)

    def send_metric(self, metric_name: str, exchange: str, market: str, value: Any):
        request_obj = {
            "url": f"{self._proxy_url}/{metric_name}",
            "method": "POST",
            "request_obj": {
                "headers": {
                    'Content-Type': "application/json"
                },
                "data": json.dumps({"instance_id": self.instance_id,
                                    "exchange": exchange,
                                    "market": market,
                                    "version": CLIENT_VERSION,
                                    "system": client_system,
                                    "installation": installation_type,
                                    f"{metric_name}": str(value)})
            }
        }
        self.log_server_client.request(request_obj)

    def flush(self, send_all=False):
        self.acquire()
        min_send_capacity = self._capacity
        if send_all:
            min_send_capacity = 0
        try:
            if global_config_map["send_error_logs"].value:
                if len(self._log_queue) > 0 and len(self._log_queue) >= min_send_capacity:
                    self.send_logs(self._log_queue)

                    self._log_queue = []
            if len(self._event_queue) > 0 and len(self._event_queue) >= min_send_capacity:
                self.send_events(self._event_queue)
                self._event_queue = []
        except Exception:
            self.logger().error("Error sending logs.", exc_info=True, extra={"do_not_send": True})
        finally:
            self.release()

    def close(self):
        try:
            self.flush(send_all=True)
            self.log_server_client.stop()
            if self._send_aggregated_metrics_loop_task is not None:
                self._send_aggregated_metrics_loop_task.cancel()
                self._send_aggregated_metrics_loop_task = None
        finally:
            logging.Handler.close(self)

    async def send_aggregated_metrics_loop(self, heartbeat_interval_min: float):
        while True:
            try:
                order_created = [e for e in self._logged_order_events if e["event_name"]
                                 in ("BuyOrderCreatedEvent", "SellOrderCreatedEvent")]
                if order_created:
                    exchanges = set(e["event_source"] for e in order_created)
                    for exchange in exchanges:
                        markets = set(e["trading_pair"] for e in order_created if e["event_source"] == exchange)
                        for market in markets:
                            created_orders = [e for e in order_created if e["event_source"] == exchange and
                                              e["trading_pair"] == market]
                            self.send_metric("order_count", exchange, market, len(created_orders))
                order_filled = [e for e in self._logged_order_events if e["event_name"] == "OrderFilledEvent"]
                if order_filled:
                    exchanges = set(e["event_source"] for e in order_filled)
                    for exchange in exchanges:
                        markets = set(e["trading_pair"] for e in order_filled if e["event_source"] == exchange)
                        for market in markets:
                            filled_trades = [e for e in order_filled if e["event_source"] == exchange and
                                             e["trading_pair"] == market]
                            traded_volume = sum(e["price"] * e["amount"] for e in filled_trades)
                            self.send_metric("filled_quote_volume", exchange, market, traded_volume)
                            self.send_metric("trade_count", exchange, market, len(filled_trades))
                self._logged_order_events.clear()
                await asyncio.sleep(60 * heartbeat_interval_min)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network("Unexpected error while sending aggregated metrics.", exc_info=True)
                return

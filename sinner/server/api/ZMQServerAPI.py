import asyncio
import logging
import platform
from typing import Callable, Optional, Any

import zmq.asyncio
from zmq import ZMQError
from zmq.asyncio import Socket as AsyncSocket

from sinner.server.api.messages.NotificationMessage import NotificationMessage
from sinner.server.api.messages.RequestMessage import RequestMessage
from sinner.server.api.messages.ResponseMessage import ResponseMessage


class ZMQServerAPI:
    _reply_endpoint: str = "tcp://127.0.0.1:5555"
    _context: zmq.asyncio.Context
    _publish_context: zmq.Context[Any]
    _reply_socket: AsyncSocket  # the listening socket
    _publish_endpoint: str = "tcp://127.0.0.1:5556"
    _publish_socket: zmq.Socket[Any]  # the publishing socket

    _logger: logging.Logger
    _server_running: bool = False
    _request_handler: Optional[Callable[[RequestMessage], ResponseMessage]] = None  # external method to handle incoming messages

    def __init__(self, handler: Optional[Callable[[RequestMessage], ResponseMessage]] = None, reply_endpoint: str = "tcp://127.0.0.1:5555", publish_endpoint: str = "tcp://127.0.0.1:5556"):
        if platform.system().lower() == 'windows':
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]  # has to be ignored, method can be unavailable on non-windows environments
            except AttributeError:
                pass  # there's no WindowsSelectorEventLoopPolicy available

        self._request_handler = handler
        self._reply_endpoint = reply_endpoint
        self._context = zmq.asyncio.Context()
        self._reply_socket = self._context.socket(zmq.REP)
        # self._reply_socket.setsockopt(zmq.RCVTIMEO, self._timeout)  # Асинхронный ZMQ сам управляет ожиданием через asyncio.

        self._publish_endpoint = publish_endpoint

        # Синхронный контекст и сокет для PUB (изменено!)
        self._publish_context = zmq.Context.instance()  # Синхронный контекст
        self._publish_socket = self._publish_context.socket(zmq.PUB)
        self._publish_socket.setsockopt(zmq.LINGER, 0)  # Быстрое закрытие

        self._logger = logging.getLogger(self.__class__.__name__)

    async def start(self) -> bool:
        try:
            self._reply_socket.bind(self._reply_endpoint)
            self._publish_socket.bind(self._publish_endpoint)

            self._server_running = True
            self._logger.info(f"Frame processor server started at {self._reply_endpoint}")

            await asyncio.gather(
                self._message_handler()
            )
            return True
        except ZMQError:
            return False

    def stop(self) -> None:
        """Close ZeroMQ context and sockets."""
        if self._reply_socket:
            self._reply_socket.close()
        if self._publish_socket:
            self._publish_socket.close()
        if self._context:
            self._context.term()
        if self._publish_context:
            self._publish_context.term()

        self._server_running = False

    async def _message_handler(self) -> None:
        """Async message handler that responds to requests."""
        while self._server_running:
            try:
                # Всегда получаем multipart сообщения
                message_parts = await self._reply_socket.recv_multipart()  # Асинхронно ждем сообщения - НЕ блокирует поток!
                request = RequestMessage.deserialize_multipart(message_parts)
                response = self._handle_request(request)
                response_parts = response.serialize_multipart()
                await self._reply_socket.send_multipart(response_parts)
            except zmq.ZMQError as e:
                if e.errno == zmq.EAGAIN:  # Тайм-аут
                    self._logger.error(f"Timeout handling message: {e}")
                    await asyncio.sleep(0.01)
                else:
                    self._logger.error(f"ZMQ error in message handler: {e}")
            except Exception as e:
                self._logger.error(f"Error handling message: {e}")
                # Пауза при ошибке, чтобы не загружать процессор
                await asyncio.sleep(0.1)

    def notify(self, notification: NotificationMessage) -> None:
        try:
            self._publish_socket.send(notification.serialize(), zmq.NOBLOCK)
        except Exception as e:
            self._logger.error(f"Failed to send notification: {e}")

    def _handle_request(self, message: RequestMessage) -> ResponseMessage:
        if self._request_handler is None:
            return ResponseMessage.error_response(message="Handler is not defined")
        else:
            return self._request_handler(message)

from typing import List, Tuple, Callable
import heapq
import functools
import time
import threading
import smtplib
from ._mailbox_base import MailboxBase
from ._packet import Packet
from . import _socket_context
from ..credential import Credential
import src.config


class MailboxTasks(MailboxBase):
    __transport: smtplib.SMTP
    __scheduled_tasks: List[Tuple[float, Callable]]
    __cv_timer: threading.Condition
    __thread_timer: threading.Thread
    __closed: bool = False

    @staticmethod
    def __init_smtp(credential: Credential) -> smtplib.SMTP:
        smtp = smtplib.SMTP(credential.host, credential.port)
        smtp.ehlo()
        smtp.starttls()
        smtp.login(credential.username, credential.password)
        return smtp

    def __init__(self, smtp: Credential):
        super().__init__()
        self.__transport = self.__init_smtp(smtp)
        self.__scheduled_tasks = []
        self.__cv_timer = threading.Condition(self._mutex)
        self.__thread_timer = threading.Thread(target=self.__timer)
        self.__thread_timer.start()

    def join(self):
        self.__thread_timer.join()

    def close(self):
        with self.__cv_timer:
            self.__closed = True
            self.__cv_timer.notify_all()
        self.__transport.close()

    def __timer(self):
        with self.__cv_timer:
            while not self.__closed:
                if self.__scheduled_tasks:
                    scheduled_time, task = self.__scheduled_tasks[0]
                    now = time.time()
                    if scheduled_time <= now:
                        heapq.heappop(self.__scheduled_tasks)
                        try:
                            task()
                        except Exception:
                            # TODO: exception handling for scheduled tasks
                            pass
                    else:
                        self.__cv_timer.wait(scheduled_time - now)
                else:
                    self.__cv_timer.wait()

    def _schedule_task(self, delay: float, task: Callable):
        with self.__cv_timer:
            heapq.heappush(self.__scheduled_tasks, (time.time() + delay, task))
            self.__cv_timer.notify_all()

    def _task_transmit(self, sid: int, seq: int):
        context: _socket_context.Connected = self._socket_check_status(sid, _socket_context.Connected)
        with context.cv:
            acks = set(context.to_ack)
            local_endpoint, remote_endpoint = context.local_endpoint, context.remote_endpoint
            if seq == -1:
                if not acks:  # nothing to ack
                    return
                packet = Packet(context.local_endpoint, context.remote_endpoint, seq, 0, acks, b'')
            elif not seq in context.pending_local:
                # already acked
                return
            else:
                attempt = context.attempts[seq]
                context.attempts[seq] += 1
                context.sent_acks[(seq, attempt)] = acks
                packet = Packet(
                    context.local_endpoint,
                    context.remote_endpoint, seq,
                    attempt, acks,
                    context.pending_local[seq])
        msg = packet.to_message()
        with self._mutex:
            self.__transport.sendmail(local_endpoint.address, remote_endpoint.address, msg.as_bytes())
        if seq != -1:  # do not retransmit pure acks
            self._schedule_task(src.config.config['tom']['RTO'] / 1000, functools.partial(self._task_transmit, sid, seq))

    def _task_send_ack(self, sid: int, next_seq: int):
        context: _socket_context.Connected = self._socket_check_status(sid, _socket_context.Connected)
        with context.cv:
            if context.next_seq != next_seq:
                # another packet carrying ack has been sent
                return
        # pure ack does not consume seq number
        self._task_transmit(sid, -1)

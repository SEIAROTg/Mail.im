from typing import List, Tuple, Callable, Optional
import math
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
        while True:
            with self.__cv_timer:
                if self.__closed:
                   break
                while not self.__closed and (not self.__scheduled_tasks or self.__scheduled_tasks[0][0] > time.time()):
                    if self.__scheduled_tasks:
                        self.__cv_timer.wait(self.__scheduled_tasks[0][0] - time.time())
                    else:
                        self.__cv_timer.wait()
                if self.__closed:
                    break
                _, task = heapq.heappop(self.__scheduled_tasks)
            try:
                task()
            except Exception:
                # TODO: exception handling for scheduled tasks
                pass

    def _schedule_task(self, delay: float, task: Callable):
        """
        Schedule a new task.

        :param delay: the scheduled time to execute in seconds, counting from current time.
        :param task: the function to execute.
        """
        with self.__cv_timer:
            heapq.heappush(self.__scheduled_tasks, (time.time() + delay, task))
            self.__cv_timer.notify_all()

    def _task_transmit(self, sid: Optional[int], context: _socket_context.Connected, seq: int):
        """
        Task body for transmitting a packet.

        This will initiate a new transmission attempt of the specified seq number and schedule a timeout retransmission,
        with some exceptions:
        1. If the socket has been closed, no actions will be taken.
        2. If the specified seq number has been ACKed from the remote, no actions will be taken.
        3. If a pure ACK is executed but there is no packet to ACK, no actions will be taken.
        4. If a pure ACK is executed, no retransmission will be scheduled.

        :param context: a connected socket context.
        :param seq: seq number of the packet to transmit.
        """
        with context.cv:
            if context.closed:
                return
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
                # TODO: close the connection on too many failed attempts
                attempt = context.attempts[seq]
                if attempt >= src.config.config['tom']['MaxAttempts']:
                    # avoid acquiring mailbox mutex while holding context.cv
                    self._schedule_task(-math.inf, functools.partial(self._task_close_socket, sid))
                    return
                else:
                    context.attempts[seq] += 1
                    context.sent_acks[(seq, attempt)] = acks
                    packet = Packet(
                        context.local_endpoint,
                        context.remote_endpoint, seq,
                        attempt, acks,
                        context.pending_local[seq],
                        is_syn = seq == context.syn_seq)
        msg = packet.to_message()
        with self._mutex:
            self.__transport.sendmail(local_endpoint.address, remote_endpoint.address, msg.as_bytes())
        if seq != -1:  # do not retransmit pure acks
            self._schedule_task(src.config.config['tom']['RTO'] / 1000, functools.partial(self._task_transmit, sid, context, seq))

    def _task_send_ack(self, context: _socket_context.Connected, next_seq: int):
        """
        Task body for sending acks.

        This will send ACK to the remote if no new packet has been sent between this is scheduled and executed.

        :param context: a connected socket context.
        :param next_seq: the next local seq number of the socket when schedule the task.
        """
        # TODO: take into consideration of attempts to reduce unnecessary pure ACKs
        with context.cv:
            if context.closed or context.next_seq != next_seq:
                # another packet carrying ack has been sent
                return
        # pure ack does not consume seq number
        self._task_transmit(None, context, -1)

    def _task_close_socket(self, sid: int):
        self._socket_close(sid)

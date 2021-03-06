from typing import List, Tuple, Callable, Optional
import math
import heapq
import functools
import time
import threading
import smtplib
from .mailbox_base import MailboxBase
from .packet import PlainPacket, SecurePacket
from . import socket_context
from ..credential import Credential
import src.config


class MailboxTasks(MailboxBase):
    __transport: smtplib.SMTP
    __mutex_transport: threading.RLock
    __scheduled_tasks: List[Tuple[float, Callable]]
    __cv_tasks: threading.Condition
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
        self.__mutex_transport = threading.RLock()
        self.__scheduled_tasks = []
        self.__cv_tasks = threading.Condition()
        self.__thread_timer = threading.Thread(target=self.__timer)
        self.__thread_timer.start()

    def join(self):
        self.__thread_timer.join()

    def close(self):
        with self.__cv_tasks:
            self.__closed = True
            self.__cv_tasks.notify_all()
        self.__transport.close()

    def __timer(self):
        while True:
            with self.__cv_tasks:
                if self.__closed:
                    break
                while not self.__closed and (not self.__scheduled_tasks or self.__scheduled_tasks[0][0] > time.time()):
                    if self.__scheduled_tasks:
                        self.__cv_tasks.wait(self.__scheduled_tasks[0][0] - time.time())
                    else:
                        self.__cv_tasks.wait()
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
        with self.__cv_tasks:
            heapq.heappush(self.__scheduled_tasks, (time.time() + delay, task))
            self.__cv_tasks.notify_all()

    def _schedule_ack(self, sid: int, context: socket_context.Connected):
        with context.cv:
            if context.ack_scheduled:
                return
            context.ack_scheduled = True
            self._schedule_task(
                src.config.config['tom']['ATO'] / 1000,
                functools.partial(self._task_send_ack, sid, context, context.next_seq))

    def _task_transmit(self, sid: Optional[int], context: socket_context.Connected, seq: int):
        """
        Task body for transmitting a packet.

        This will initiate a new transmission attempt of the specified seq number and schedule a timeout retransmission,
        with some exceptions:
        1. If the socket has been closed, no actions will be taken.
        2. If the specified seq number has been ACKed from the remote, no actions will be taken.
        3. If a pure ACK is executed but there is no packet to ACK, no actions will be taken.
        4. If a pure ACK is executed, no retransmission will be scheduled.

        :param sid: socket id
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
                packet: PlainPacket = PlainPacket(context.local_endpoint, context.remote_endpoint, seq, 0, acks, b'')
                if isinstance(context, socket_context.SecureConnected):
                    packet = SecurePacket.encrypt(packet, context.ratchet, context.xeddsa)
            elif not seq in context.pending_local:
                # already acked
                return
            else:
                attempt = context.attempts[seq]
                if attempt >= src.config.config['tom']['MaxAttempts']:
                    # avoid acquiring mailbox mutex while holding context.cv
                    self._schedule_task(-math.inf, functools.partial(self._task_close_socket, sid))
                    return
                elif isinstance(context, socket_context.SecureConnected):
                    context.attempts[seq] += 1
                    context.sent_acks[(seq, attempt)] = acks
                    packet: SecurePacket = context.pending_local[seq]
                else:
                    context.attempts[seq] += 1
                    context.sent_acks[(seq, attempt)] = acks
                    packet: PlainPacket = context.pending_local[seq]
                    packet = PlainPacket(
                        packet.from_,
                        packet.to,
                        seq,
                        attempt,
                        acks,
                        packet.payload,
                        packet.is_syn)
            msg = packet.to_message()
            context.ack_scheduled = False
        with self.__mutex_transport:
            self.__transport.sendmail(local_endpoint.address, remote_endpoint.address, msg.as_bytes())
        if seq != -1:  # do not retransmit pure acks
            self._schedule_task(src.config.config['tom']['RTO'] / 1000, functools.partial(self._task_transmit, sid, context, seq))

    def _task_send_ack(self, sid: int, context: socket_context.Connected, next_seq: int):
        """
        Task body for sending acks.

        This will send ACK to the remote if no new packet has been sent between this is scheduled and executed.

        :param sid: socket id
        :param context: a connected socket context.
        :param next_seq: the next local seq number of the socket when schedule the task.
        """
        # TODO: take into consideration of attempts to reduce unnecessary pure ACKs
        with context.cv:
            if context.closed or context.next_seq != next_seq:
                # another packet carrying ack has been sent
                return
            # pure ack does not consume seq number
            self._task_transmit(sid, context, -1)

    def _task_close_socket(self, sid: int):
        self._socket_shutdown(sid)

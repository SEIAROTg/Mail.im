import os
import random
import threading
import pytest
from faker import Faker
from src.tom import Credential, Mailbox, Endpoint, Socket, Epoll


ENV_PREFIX = 'MAILIM_INTEG_TOM_'


def get_credential(protocol: str) -> Credential:
    prefix = ENV_PREFIX + protocol.upper()
    host = os.getenv(prefix + '_HOST')
    assert host is not None
    port = os.getenv(prefix + '_PORT')
    assert port is not None
    port = int(port)
    username = os.getenv(prefix + '_USERNAME')
    assert username is not None
    password = os.getenv(prefix + '_PASSWORD')
    assert password is not None
    return Credential(host, port, username, password)


@pytest.fixture()
def smtp() -> Credential:
    return get_credential('smtp')


@pytest.fixture()
def imap() -> Credential:
    return get_credential('imap')


@pytest.mark.integ
@pytest.mark.timeout(500)
def test_mutual_connect(faker: Faker, smtp: Credential, imap: Credential):
    payloads = [faker.binary(random.randint(10, 10000)) for i in range(10)]
    port0 = faker.uuid4()
    port1 = faker.uuid4()
    mailbox = Mailbox(smtp, imap)
    socket0 = Socket(mailbox)
    socket1 = Socket(mailbox)
    socket0.connect(Endpoint(imap.username, port0), Endpoint(imap.username, port1))
    socket1.connect(Endpoint(imap.username, port1), Endpoint(imap.username, port0))
    print()
    for i in range(0, 10, 2):
        socket0.send(payloads[i])
        print('packet {}: sent'.format(i))
        assert socket1.recv_exact(len(payloads[i])) == payloads[i]
        print('packet {}: received'.format(i))
        socket1.send(payloads[i + 1])
        print('packet {}: sent'.format(i + 1))
        assert socket0.recv_exact(len(payloads[i + 1])) == payloads[i + 1]
        print('packet {}: received'.format(i + 1))
    mailbox.close()


@pytest.mark.integ
@pytest.mark.timeout(500)
def test_listen(faker: Faker, smtp: Credential, imap: Credential):
    payloads = [faker.binary(random.randint(10, 10000)) for i in range(10)]
    port0 = faker.uuid4()
    port1 = faker.uuid4()
    mailbox = Mailbox(smtp, imap)
    socket0 = Socket(mailbox)
    socket_listen = Socket(mailbox)
    socket_listen.listen(Endpoint(imap.username, port1))
    socket0.connect(Endpoint(imap.username, port0), Endpoint(imap.username, port1))
    socket0.send(payloads[0])
    socket1 = socket_listen.accept()
    print()
    for i in range(0, 10, 2):
        if i != 0:
            socket0.send(payloads[i])
        print('packet {}: sent'.format(i))
        assert socket1.recv_exact(len(payloads[i])) == payloads[i]
        print('packet {}: received'.format(i))
        socket1.send(payloads[i + 1])
        print('packet {}: sent'.format(i + 1))
        assert socket0.recv_exact(len(payloads[i + 1])) == payloads[i + 1]
        print('packet {}: received'.format(i + 1))
    mailbox.close()


@pytest.mark.integ
@pytest.mark.timeout(500)
def test_secure(faker: Faker, smtp: Credential, imap: Credential):
    payloads = [faker.binary(random.randint(10, 10000)) for i in range(10)]
    port0 = faker.uuid4()
    port1 = faker.uuid4()
    mailbox = Mailbox(smtp, imap)
    socket0 = Socket(mailbox)
    socket_listen = Socket(mailbox)
    socket_listen.listen(Endpoint(imap.username, port1))
    thread_connect = threading.Thread(
        target=lambda: socket0.connect(Endpoint(imap.username, port0), Endpoint(imap.username, port1), secure=True))
    thread_connect.start()
    socket1 = socket_listen.accept()
    thread_connect.join()
    print()
    print('hand shaked')
    for i in range(0, 10, 2):
        socket0.send(payloads[i])
        print('packet {}: sent'.format(i))
        assert socket1.recv_exact(len(payloads[i])) == payloads[i]
        print('packet {}: received'.format(i))
        socket1.send(payloads[i + 1])
        print('packet {}: sent'.format(i + 1))
        assert socket0.recv_exact(len(payloads[i + 1])) == payloads[i + 1]
        print('packet {}: received'.format(i + 1))
    mailbox.close()

import os
import random
import threading
import pytest
from faker import Faker
from xeddsa.implementations.xeddsa25519 import XEdDSA25519
from src.tom import Credential, Mailbox, Endpoint, Socket


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
    payloads = [faker.binary(random.randint(10, 10000)) for _ in range(10)]
    alice_port = faker.uuid4()
    bob_port = faker.uuid4()
    mailbox = Mailbox(smtp, imap)
    alice_socket = Socket(mailbox)
    bob_socket = Socket(mailbox)
    alice_socket.connect(Endpoint(imap.username, alice_port), Endpoint(imap.username, bob_port))
    bob_socket.connect(Endpoint(imap.username, bob_port), Endpoint(imap.username, alice_port))
    print()
    for i in range(0, 10, 2):
        alice_socket.send(payloads[i])
        print('packet {}: sent'.format(i))
        assert bob_socket.recv_exact(len(payloads[i])) == payloads[i]
        print('packet {}: received'.format(i))
        bob_socket.send(payloads[i + 1])
        print('packet {}: sent'.format(i + 1))
        assert alice_socket.recv_exact(len(payloads[i + 1])) == payloads[i + 1]
        print('packet {}: received'.format(i + 1))
    mailbox.close()


@pytest.mark.integ
@pytest.mark.timeout(500)
def test_listen(faker: Faker, smtp: Credential, imap: Credential):
    payloads = [faker.binary(random.randint(10, 10000)) for _ in range(10)]
    alice_port = faker.uuid4()
    bob_port = faker.uuid4()
    mailbox = Mailbox(smtp, imap)
    alice_socket = Socket(mailbox)
    socket_listen = Socket(mailbox)
    socket_listen.listen(Endpoint(imap.username, bob_port))
    alice_socket.connect(Endpoint(imap.username, alice_port), Endpoint(imap.username, bob_port))
    alice_socket.send(payloads[0])
    bob_socket = socket_listen.accept()
    print()
    for i in range(0, 10, 2):
        if i != 0:
            alice_socket.send(payloads[i])
        print('packet {}: sent'.format(i))
        assert bob_socket.recv_exact(len(payloads[i])) == payloads[i]
        print('packet {}: received'.format(i))
        bob_socket.send(payloads[i + 1])
        print('packet {}: sent'.format(i + 1))
        assert alice_socket.recv_exact(len(payloads[i + 1])) == payloads[i + 1]
        print('packet {}: received'.format(i + 1))
    mailbox.close()


@pytest.mark.integ
@pytest.mark.timeout(500)
def test_secure(faker: Faker, smtp: Credential, imap: Credential):
    payloads = [faker.binary(random.randint(10, 10000)) for i in range(10)]
    alice_port = faker.uuid4()
    bob_port = faker.uuid4()
    alice_priv = XEdDSA25519.generate_mont_priv()
    alice_pub = XEdDSA25519.mont_pub_from_mont_priv(alice_priv)
    bob_priv = XEdDSA25519.generate_mont_priv()
    bob_pub = XEdDSA25519.mont_pub_from_mont_priv(bob_priv)
    mailbox = Mailbox(smtp, imap)
    alice_socket = Socket(mailbox)
    socket_listen = Socket(mailbox)
    socket_listen.listen(Endpoint(imap.username, bob_port))
    thread_connect = threading.Thread(
        target=lambda: alice_socket.connect(
            Endpoint(imap.username, alice_port),
            Endpoint(imap.username, bob_port),
            sign_key_pair=(alice_priv, bob_pub)))
    thread_connect.start()
    bob_socket = socket_listen.accept(should_accept=lambda *args: (bob_priv, alice_pub))
    thread_connect.join()
    print()
    print('hand shaked')
    for i in range(0, 10, 2):
        alice_socket.send(payloads[i])
        print('packet {}: sent'.format(i))
        assert bob_socket.recv_exact(len(payloads[i])) == payloads[i]
        print('packet {}: received'.format(i))
        bob_socket.send(payloads[i + 1])
        print('packet {}: sent'.format(i + 1))
        assert alice_socket.recv_exact(len(payloads[i + 1])) == payloads[i + 1]
        print('packet {}: received'.format(i + 1))
    mailbox.close()

import pytest
from faker import Faker
import pickle
from src.crypto.doubleratchet import *
import src.config

# from https://github.com/Syndace/python-doubleratchet/blob/master/tests/test_doubleratchet.py, with changes
# MIT License
# Copyright (c) 2018 Tim Henkes (Syndace)


def test_simple(faker: Faker):
    alice_key = KeyPair.generate()

    alice_ratchet = DoubleRatchet(own_key=alice_key)
    bob_ratchet = DoubleRatchet(other_pub=alice_key.pub)

    for _ in range(100):
        message = faker.binary(111)
        c = bob_ratchet.encryptMessage(message)
        assert alice_ratchet.decryptMessage(c['ciphertext'], c['header']) == message
        message = faker.binary(111)
        c = alice_ratchet.encryptMessage(message)
        assert bob_ratchet.decryptMessage(c['ciphertext'], c['header']) == message


def test_not_synced(faker: Faker):
    alice_key = KeyPair.generate()
    alice_ratchet = DoubleRatchet(own_key=alice_key)
    message = faker.binary(111)

    with pytest.raises(doubleratchet.exceptions.NotInitializedException):
        alice_ratchet.encryptMessage(message)


def test_skipped_message(faker: Faker):
    alice_key = KeyPair.generate()

    alice_ratchet = DoubleRatchet(own_key=alice_key)
    bob_ratchet = DoubleRatchet(other_pub=alice_key.pub)

    for _ in range(100):
        message_a = faker.binary(111)
        message_b = faker.binary(111)

        c_a = bob_ratchet.encryptMessage(message_a)
        c_b = bob_ratchet.encryptMessage(message_b)

        assert alice_ratchet.decryptMessage(c_b['ciphertext'], c_b['header']) == message_b
        assert alice_ratchet.decryptMessage(c_a['ciphertext'], c_a['header']) == message_a

        message_a = faker.binary(111)
        message_b = faker.binary(111)

        c_a = alice_ratchet.encryptMessage(message_a)
        c_b = alice_ratchet.encryptMessage(message_b)

        assert bob_ratchet.decryptMessage(c_b['ciphertext'], c_b['header']) == message_b
        assert bob_ratchet.decryptMessage(c_a['ciphertext'], c_a['header']) == message_a


def test_too_many_skipped_messages(faker: Faker):
    alice_key = KeyPair.generate()

    alice_ratchet = DoubleRatchet(own_key=alice_key)
    bob_ratchet = DoubleRatchet(other_pub=alice_key.pub)

    # Skip MaxMsgKeys+1 messages
    for _ in range(src.config.config['crypto']['MaxMsgKeys'] + 1):
        bob_ratchet.encryptMessage(faker.binary(111))

    c = bob_ratchet.encryptMessage(faker.binary(111))

    with pytest.raises(doubleratchet.exceptions.TooManySavedMessageKeysException):
        alice_ratchet.decryptMessage(c['ciphertext'], c['header'])


def test_serialization(faker: Faker):
    alice_key = KeyPair.generate()

    alice_ratchet = DoubleRatchet(own_key=alice_key)
    bob_ratchet = DoubleRatchet(other_pub=alice_key.pub)

    for _ in range(100):
        message = faker.binary(111)

        c = bob_ratchet.encryptMessage(message)

        assert alice_ratchet.decryptMessage(c['ciphertext'], c['header']) == message

        message = faker.binary(111)

        c = alice_ratchet.encryptMessage(message)

        assert bob_ratchet.decryptMessage(c['ciphertext'], c['header']) == message

    alice_ratchet_serialized = pickle.dumps(alice_ratchet.serialize())
    bob_ratchet_serialized = pickle.dumps(bob_ratchet.serialize())

    alice_ratchet = DoubleRatchet.fromSerialized(pickle.loads(alice_ratchet_serialized))
    bob_ratchet = DoubleRatchet.fromSerialized(pickle.loads(bob_ratchet_serialized))

    for _ in range(100):
        message = faker.binary(111)

        c = bob_ratchet.encryptMessage(message)

        assert alice_ratchet.decryptMessage(c['ciphertext'], c['header']) == message

        message = faker.binary(111)

        c = alice_ratchet.encryptMessage(message)

        assert bob_ratchet.decryptMessage(c['ciphertext'], c['header']) == message

from unittest.mock import patch, call
import pytest
from faker import Faker
from src.tom import Credential, Mailbox


@pytest.fixture()
def faker():
    return Faker()


@pytest.mark.timeout(5)
@patch('smtplib.SMTP')
@patch('imapclient.IMAPClient')
def test_mailbox(IMAPClient, SMTP, faker):
    smtp = Credential(host=faker.hostname(), port=faker.pyint(), username=faker.email(), password=faker.password())
    imap = Credential(host=faker.hostname(), port=faker.pyint(), username=faker.email(), password=faker.password())

    mailbox = Mailbox(smtp, imap)

    SMTP.assert_has_calls([
        call(smtp.host, smtp.port),
        call().ehlo(),
        call().starttls(),
        call().login(smtp.username, smtp.password),
    ])

    IMAPClient.assert_has_calls([
        call(imap.host, imap.port, ssl=True, use_uid=True),
        call().login(imap.username, imap.password),
    ])

    mailbox.close()

    SMTP.return_value.close.assert_called_once()
    IMAPClient.return_value.logout.assert_called_once()

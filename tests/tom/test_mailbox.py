from unittest.mock import patch, call, MagicMock
import pytest
from faker import Faker
from src.tom import Credential, Mailbox


@pytest.mark.timeout(5)
@patch('smtplib.SMTP')
@patch('src.tom._mailbox.imapclient.IMAPClient')
def test_mailbox(IMAPClient: MagicMock, SMTP: MagicMock, faker: Faker):
    smtp = Credential(host=faker.hostname(), port=faker.pyint(), username=faker.email(), password=faker.password())
    imap = Credential(host=faker.hostname(), port=faker.pyint(), username=faker.email(), password=faker.password())

    store = MagicMock()
    listener = MagicMock()

    IMAPClient.side_effect = [store, listener]
    listener.idle_check.return_value = None  # skip idle check in tests

    mailbox = Mailbox(smtp, imap)

    SMTP.assert_has_calls([
        call(smtp.host, smtp.port),
        call().ehlo(),
        call().starttls(),
        call().login(smtp.username, smtp.password),
    ])

    IMAPClient.assert_has_calls([
        call(imap.host, imap.port, ssl=True, use_uid=True),
        call(imap.host, imap.port, ssl=True, use_uid=True),
    ])

    store.assert_has_calls([
        call.login(imap.username, imap.password),
        call.select_folder('INBOX'),
    ])

    listener.assert_has_calls([
        call.login(imap.username, imap.password),
        call.select_folder('INBOX'),
    ])

    mailbox.close()

    SMTP.return_value.close.assert_called_once()
    store.logout.assert_called_once()
    listener.logout.assert_called_once()

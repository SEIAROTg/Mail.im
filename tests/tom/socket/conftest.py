import pytest
from ..socket_test_helper import SocketTestHelper


@pytest.fixture()
def helper() -> SocketTestHelper:
    helper = SocketTestHelper()
    yield helper
    helper.close()

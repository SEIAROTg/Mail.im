import pytest
from faker import Faker


@pytest.fixture(scope='session')
def faker() -> Faker:
    return Faker()


def pytest_addoption(parser):
    parser.addoption('--integration', action='store_true', help='run integration tests rather than unit tests')


def pytest_runtest_setup(item):
    if ('integ' in item.keywords) != item.config.getoption('--integration'):
        pytest.skip('asd')

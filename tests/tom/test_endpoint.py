from src.tom import Endpoint


def test_equal():
    a = Endpoint("foo@bar.com", "123")
    b = Endpoint("foo@bar.com", "123")
    c = Endpoint("bar@foo.com", "123")
    d = Endpoint("foo@bar.com", "321")
    e = Endpoint("@bar.com", "")
    assert a == a
    assert a == b
    assert a != c
    assert a != d
    assert a != e


def test_complete():
    a = Endpoint("foo@bar.com", "123")
    b = Endpoint("@bar.com", "123")
    c = Endpoint("foo@bar.com", "")
    d = Endpoint("", "")
    assert a.complete()
    assert not b.complete()
    assert not c.complete()
    assert not d.complete()


def test_match():
    endpoints = [
        Endpoint("foo@bar.com", "123"),
        Endpoint("foo@bar.com", "321"),
        Endpoint("foo@bar.com", ""),
        Endpoint("bar@foo.com", "123"),
        Endpoint("@foo.com", "123"),
        Endpoint("@bar.com", "123"),
        Endpoint("", ""),
    ]
    expected = [
        1, 0, 0, 0, 0, 0, 0,
        0, 1, 0, 0, 0, 0, 0,
        1, 1, 1, 0, 0, 0, 0,
        0, 0, 0, 1, 0, 0, 0,
        0, 0, 0, 1, 1, 0, 0,
        1, 0, 0, 0, 0, 1, 0,
        1, 1, 1, 1, 1, 1, 1,
    ]
    i = 0
    for a in endpoints:
        for b in endpoints:
            assert a.matches(b) == bool(expected[i])
            i += 1


def test_intersect():
    endpoints = [
        Endpoint("foo@bar.com", "123"),
        Endpoint("foo@bar.com", "321"),
        Endpoint("foo@bar.com", ""),
        Endpoint("bar@foo.com", "123"),
        Endpoint("@foo.com", "123"),
        Endpoint("@bar.com", "123"),
        Endpoint("", ""),
    ]
    expected = [
        1, 0, 1, 0, 0, 1, 1,
        0, 1, 1, 0, 0, 0, 1,
        1, 1, 1, 0, 0, 1, 1,
        0, 0, 0, 1, 1, 0, 1,
        0, 0, 0, 1, 1, 0, 1,
        1, 0, 1, 0, 0, 1, 1,
        1, 1, 1, 1, 1, 1, 1,
    ]
    i = 0
    for a in endpoints:
        for b in endpoints:
            assert a.intersects_with(b) == bool(expected[i])
            i += 1

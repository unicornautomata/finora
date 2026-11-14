import pytest
from finora.client.api_client import ApiError
from finora.client.auth_flow import (describe_login_error, is_encrypted_url, is_local_url, looks_like_caps_lock,
                                     normalize_server_url)


@pytest.mark.parametrize("raw,expected", [("192.168.1.5:8000/", "http://192.168.1.5:8000"),
                                          ("https://acct.example.com/", "https://acct.example.com"),
                                          ("  localhost:8000 ", "http://localhost:8000")])
def test_normalize_accepts_and_cleans(raw, expected):
    assert normalize_server_url(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "ftp://x", "http://", "https://", "http://host:99999"])
def test_normalize_rejects_with_a_readable_message(bad):
    with pytest.raises(ValueError) as e:
        normalize_server_url(bad)
    assert len(str(e.value)) > 10


def test_url_classification():
    assert is_local_url("http://127.0.0.1:8000") and is_local_url("http://localhost:1")
    assert not is_local_url("http://192.168.1.5:8000")
    assert is_encrypted_url("https://a.example.com") and not is_encrypted_url("http://a.example.com")


def test_error_wording_distinguishes_causes():
    assert "Incorrect username or password" in describe_login_error(ApiError("x", 401))[0]
    msg, kind = describe_login_error(ApiError("x", 429))
    assert "locked" in msg and kind == "warning"
    msg, kind = describe_login_error(ApiError("boom", 0, network=True), "http://srv:8000")
    assert "Can't reach the server at http://srv:8000" in msg and kind == "danger"
    assert "problem (503)" in describe_login_error(ApiError("x", 503))[0]
    assert describe_login_error(RuntimeError("SQLite too old"))[0] == "SQLite too old"
    # the server's own wording is never shown for credential problems (no account hints)
    assert "x" not in describe_login_error(ApiError("x", 401))[0].split()


def test_caps_lock_heuristic():
    assert looks_like_caps_lock("A", False) is True        # capital without Shift
    assert looks_like_caps_lock("a", True) is True         # lowercase with Shift
    assert looks_like_caps_lock("a", False) is False
    assert looks_like_caps_lock("A", True) is False
    assert looks_like_caps_lock("5", False) is None and looks_like_caps_lock("", False) is None

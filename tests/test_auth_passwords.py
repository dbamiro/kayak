from app.auth.passwords import hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("short-pass-ok-8")
    assert verify_password("short-pass-ok-8", h)
    assert not verify_password("wrong", h)


def test_verify_rejects_empty_hash():
    assert verify_password("x", None) is False
    assert verify_password("x", "") is False

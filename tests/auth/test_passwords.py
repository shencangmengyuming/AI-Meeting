from app.auth_user.application.passwords import hash_password, verify_password


def test_scrypt_password_round_trip() -> None:
    stored = hash_password("secret")

    assert stored.startswith("scrypt$")
    assert verify_password("secret", stored) == (True, False)
    assert verify_password("wrong", stored) == (False, False)


def test_legacy_password_is_verified_and_marked_for_upgrade() -> None:
    assert verify_password("secret", "secret") == (True, True)
    assert verify_password("wrong", "secret") == (False, True)

from app.core import crypto


def test_round_trip():
    ct = crypto.encrypt_at_rest("hello")
    assert ct != "hello"
    assert crypto.decrypt_at_rest(ct) == "hello"


def test_totp_helpers_delegate_and_interop():
    # Data written via totp helpers must decrypt via the shared helper and vice versa.
    from app.services import totp_service
    ct = totp_service._totp_encrypt("x")
    assert crypto.decrypt_at_rest(ct) == "x"
    ct2 = crypto.encrypt_at_rest("y")
    assert totp_service._totp_decrypt(ct2) == "y"

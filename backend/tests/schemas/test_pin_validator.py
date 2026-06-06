import pytest
from pydantic import ValidationError
from app.schemas.auth import PinSetRequest


@pytest.mark.parametrize("pin", ["4827", "13905", "90218746"])
def test_valid_pins(pin):
    req = PinSetRequest(pin=pin, code="123456")
    assert req.pin == pin


@pytest.mark.parametrize("pin", [
    "0000", "1111", "9999",     # all-same
    "1234", "2345", "5678",     # ascending
    "4321", "9876",             # descending
    "123",                       # too short
    "123456789",                 # too long
    "12a4", "ab12",              # non-digit
])
def test_invalid_pins(pin):
    with pytest.raises(ValidationError):
        PinSetRequest(pin=pin, code="123456")

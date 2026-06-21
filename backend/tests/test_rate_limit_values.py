from app.core.rate_limiter import RATE_LIMITS


def test_file_upload_limit_is_realistic():
    """50000/min was effectively unlimited (DoS path). 300/min is plenty for the
    web file manager while bounding abuse."""
    assert RATE_LIMITS["file_upload"] == "300/minute"


def test_file_chunked_stays_high_for_per_chunk_puts():
    """file_chunked gates every chunk PUT, so it must stay high — do not slash it."""
    count = int(RATE_LIMITS["file_chunked"].split("/")[0])
    assert count >= 10000

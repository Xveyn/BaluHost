"""A full disk reaches the client as 507 with its message (scrubber follow-up to #591).

The route raised HTTPException(507, ...); the global 5xx scrubber turned the
"Not enough space ..." text into "Internal server error". Through the real app
(and its exception handlers) the message must survive.
"""
from fastapi.testclient import TestClient

import app.api.routes.chunked_upload as chunked_routes


def test_init_beyond_available_space_is_a_507_with_the_sizes(client: TestClient, admin_headers, monkeypatch):
    async def _three_bytes_free():
        return 3

    monkeypatch.setattr(chunked_routes, "calculate_available_bytes_async", _three_bytes_free)

    r = client.post(
        "/api/files/upload/chunked/init",
        json={"filename": "big.bin", "total_size": 10, "target_path": ""},
        headers=admin_headers,
    )

    assert r.status_code == 507
    assert r.json()["detail"] == "Not enough space. Need 10 bytes, available 3."

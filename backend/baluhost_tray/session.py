"""Token lifecycle for the tray.

Three error classes, not one. A 429 on /ws-token (30/minute) must never cost
the pairing: a backoff that starts at one second would burn the allowance in
half a minute and the tray would sign itself out.
"""

from __future__ import annotations

from baluhost_tray import config as tray_config
from baluhost_tui.client import BackendClient

WS_TOKEN_PATH = "/api/notifications/ws-token"
REFRESH_PATH = "/api/auth/refresh"
WS_PATH = "/api/notifications/ws"


class AuthExpired(Exception):
    """The access token is stale — refresh_access() should fix it."""


class TemporaryFailure(Exception):
    """Rate limit, server error or network. Back off and try again."""


class PairingLost(Exception):
    """The refresh token no longer works — the device must pair again."""


class Session:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        tokens = tray_config.load_tokens()
        # BackendClient takes `server=`, not `base_url=`. Without it
        # resolve_transport() falls back to /run/baluhost/local.sock — the
        # companion channel this design deliberately does not use.
        self._client = BackendClient(server=self._base_url)
        if tokens:
            self._client.set_token(tokens.access)

    def client(self) -> BackendClient:
        return self._client

    def ws_url(self) -> str:
        """Websocket URL derived from the base URL (http→ws, https→wss)."""
        scheme = "wss" if self._base_url.startswith("https") else "ws"
        host = self._base_url.split("://", 1)[-1]
        return f"{scheme}://{host}{WS_PATH}"

    def ws_token(self) -> str:
        """Short lived (60 s) token for the notification websocket.

        Fetched per connection attempt rather than cached — caching a token
        that lives one minute only produces a stale one after every outage.
        """
        response = self._client.post(WS_TOKEN_PATH)
        code = response.status_code
        if code == 200:
            return response.json()["token"]
        if code == 401:
            raise AuthExpired("ws-token rejected the access token")
        if code == 429 or code >= 500:
            raise TemporaryFailure(f"ws-token unavailable: {code}")
        raise PairingLost(f"ws-token refused: {code}")

    def refresh_access(self) -> None:
        """Exchange the refresh token for a fresh access token.

        The server does not rotate the refresh token (see TokenResponse), so
        the stored one is kept. Only a 401 means the pairing is gone; a rate
        limit must not delete credentials.
        """
        tokens = tray_config.load_tokens()
        if not tokens:
            raise PairingLost("no tokens stored")

        response = self._client.post(
            REFRESH_PATH, json={"refresh_token": tokens.refresh}
        )
        code = response.status_code

        if code == 429 or code >= 500:
            raise TemporaryFailure(f"refresh unavailable: {code}")
        if code != 200:
            self.forget()
            raise PairingLost(f"refresh refused: {code}")

        data = response.json()
        new_tokens = tray_config.Tokens(
            access=data["access_token"],
            refresh=tokens.refresh,
        )
        tray_config.save_tokens(new_tokens)
        self._client.set_token(new_tokens.access)

    def forget(self) -> None:
        tray_config.clear_tokens()
        self._client.clear_token()

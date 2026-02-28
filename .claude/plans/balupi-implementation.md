# BaluPi — Implementation Prompt for Claude Code

> **Use this as a prompt/plan when working in the BaluPi repo** ([github.com/Xveyn/BaluPi](https://github.com/Xveyn/BaluPi)).
> All BaluHost-side changes (handshake service, snapshot export, hooks, Pi frontend build) are already done.

---

## Current Repo State

The BaluPi repo has a P0 foundation:

| Done | Missing |
|------|---------|
| FastAPI app + lifespan (`main.py`) | All services (`services/__init__.py` is empty) |
| Async SQLite + WAL (`database.py`) | APScheduler integration |
| Config with 40+ env vars (`config.py`) | Energy/Tapo business logic |
| Health/Ping endpoints | Handshake endpoints |
| Auth forwarding to NAS (`deps.py`) | JWT local validation (offline) |
| System status via psutil | NAS state machine |
| NAS health polling (`/api/nas/status`) | Heartbeat service |
| WoL utility (`utils/wol.py`) | WoL route wiring |
| DB models (energy + tapo, complete) | DNS switching (Pi-hole) |
| Pydantic schemas (energy + tapo) | Inbox flush (rsync) |
| systemd service file | Background scheduler |
| Energy/Tapo route stubs | Actual route implementations |

### Files to Remove (Unused Cache/Sync Leftovers)

These were part of an earlier sync design that was scrapped. Delete them:

```
backend/app/models/cached_file.py
backend/app/models/upload_queue.py
backend/app/models/sync_log.py
backend/app/models/conflict.py
backend/app/models/file_metadata.py
backend/app/api/routes/files.py
backend/app/api/routes/cache.py
backend/app/schemas/cache.py
backend/app/schemas/files.py
backend/app/schemas/sync.py
```

Also remove corresponding imports in `__init__.py` files and any cache/sync config variables from `config.py` (`BALUPI_CACHE_MAX_SIZE_GB`, `BALUPI_SYNC_INTERVAL_SECONDS`, etc.).

After deletion, verify: `python3 -c "from app.main import app"` still works.

---

## Phase 1 — Energy Monitoring

No dependencies on BaluHost. Can be implemented standalone.

### 1.1 Tapo Service — `backend/app/services/tapo_service.py`

Uses `python-kasa` (already in dependencies). Key patterns:

```python
from kasa import Discover, Device, Module

# Discovery — scan LAN for Tapo P110/P115 devices
devices = await Discover.discover(target="192.168.178.0/24", timeout=5)
# Returns dict: {ip: Device}. Each device needs .update() before reading data.

# Connect to known device by IP (faster than discovery)
device = await Device.connect(host="192.168.178.40", credentials=Credentials("user", "pass"))
await device.update()  # MUST call before reading any data

# Read energy data
energy = device.modules[Module.Energy]
power_w = energy.current_consumption    # Watts (float)
voltage_v = energy.voltage              # Volts (float)
current_a = energy.current              # Amps (float)
today_kwh = energy.consumption_today    # kWh today (float)

# Toggle on/off
await device.turn_on()
await device.turn_off()

# Device info
device.alias          # User-friendly name
device.mac            # MAC address
device.model          # e.g. "P110"
device.hw_info        # Hardware version
device.is_on          # Power state
```

**Connection Caching**: Store authenticated `Device` objects in a dict keyed by IP. On error (`KasaException`, `TimeoutError`), remove from cache and reconnect. BaluHost's `power/monitor.py` has a reference pattern for this.

**Error Handling**: Wrap all kasa calls in try/except. Devices go offline frequently (Wi-Fi drops, power cycles). Log warnings, don't crash the service. Mark devices as `is_online=False` in DB when unreachable.

**Credentials**: Tapo P110/P115 require TP-Link cloud credentials for local auth (a python-kasa quirk). Store in config: `BALUPI_TAPO_USERNAME` and `BALUPI_TAPO_PASSWORD`. These are already defined in the config.

**Dev Mode**: When `BALUPI_MODE=dev`, return mock data instead of calling python-kasa. Pattern: check `settings.is_dev_mode` at the top of each service function.

Service functions to implement:

```python
async def discover_devices() -> list[TapoDiscoverResult]
async def get_all_devices(db: AsyncSession) -> list[TapoDevice]
async def get_device_realtime(device_id: str) -> EnergyCurrent | None
async def toggle_device(device_id: str, db: AsyncSession) -> bool
async def update_device(device_id: str, data: TapoDeviceUpdate, db: AsyncSession) -> TapoDevice
```

### 1.2 Energy Service — `backend/app/services/energy_service.py`

```python
async def collect_energy_samples(db: AsyncSession) -> None:
    """Poll all active Tapo devices, write to energy_samples table. Called every 30s by scheduler."""

async def aggregate_hourly(db: AsyncSession) -> None:
    """Roll up raw samples into energy_hourly (avg/min/max power, total energy). Called hourly."""

async def aggregate_daily(db: AsyncSession) -> None:
    """Roll up hourly into energy_daily (+ cost calculation). Called daily at 00:05."""

async def cleanup_old_samples(db: AsyncSession) -> None:
    """Delete raw samples older than 7 days. Called daily."""

async def get_current_power(db: AsyncSession) -> EnergCurrentAll:
    """Live power reading from all devices."""

async def get_energy_history(device_id: str, period: str, db: AsyncSession) -> list[EnergyHistoryPoint]:
    """Historical data for a device. period: today|week|month."""

async def get_energy_summary(db: AsyncSession) -> EnergySummary:
    """Overview: total devices, total power, NAS state guess, monthly cost estimate."""
```

**NAS Detection via Power**: Use configurable threshold (default 30W):
- `>20W` = NAS active
- `2-15W` = Standby/Sleep
- `<2W` = Completely off

**Cost Calculation**: Read `energy_price_config` table, then `ct_per_kwh * consumption`. Default: 30 ct/kWh.

**Retention**: Raw samples after 7 days = ~17 MB max at 3 devices (30s intervals).

### 1.3 APScheduler Integration — `backend/app/main.py`

Use APScheduler 3.x with `AsyncIOScheduler` (already in dependencies):

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# In lifespan startup:
scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=str(settings.database_url))},
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
)

scheduler.add_job(
    collect_energy_samples, "interval", seconds=30,
    id="collect_energy", replace_existing=True,
)
scheduler.add_job(
    aggregate_hourly, "cron", minute=5,
    id="aggregate_hourly", replace_existing=True,
)
scheduler.add_job(
    aggregate_daily, "cron", hour=0, minute=5,
    id="aggregate_daily", replace_existing=True,
)
scheduler.add_job(
    cleanup_old_samples, "cron", hour=0, minute=10,
    id="cleanup_samples", replace_existing=True,
)

scheduler.start()

# In lifespan shutdown:
scheduler.shutdown(wait=False)
```

**Important**: Use `replace_existing=True` on all jobs — prevents duplicate jobs when the process restarts. Use `coalesce=True` so missed jobs don't stack up. Use `max_instances=1` to prevent concurrent executions.

**DB Session in Jobs**: Jobs need their own DB session. Create a helper:

```python
async def _run_with_db(func):
    async with get_async_session() as db:
        await func(db)
```

### 1.4 Wire Up Route Stubs

The routes in `api/routes/energy.py` and `api/routes/tapo.py` already have the correct signatures but return empty/mock data. Replace the bodies with actual service calls.

**Energy routes:**
- `GET /api/energy/current` -> `energy_service.get_current_power(db)`
- `GET /api/energy/history?device_id=...&period=today|week|month` -> `energy_service.get_energy_history(...)`
- `GET /api/energy/costs?period=...` -> cost data from `energy_service`
- `GET /api/energy/summary` -> `energy_service.get_energy_summary(db)`

**Tapo routes:**
- `GET /api/tapo/devices` -> `tapo_service.get_all_devices(db)`
- `POST /api/tapo/devices/discover` -> `tapo_service.discover_devices()`
- `PUT /api/tapo/devices/{id}` -> `tapo_service.update_device(...)`
- `POST /api/tapo/devices/{id}/toggle` -> `tapo_service.toggle_device(...)`

### 1.5 Tests

Create `tests/test_energy_service.py` and `tests/test_tapo_service.py`:

- Mock `Device.connect()` and `Discover.discover()` — never call real hardware in tests
- Test sampling writes to DB correctly
- Test hourly/daily aggregation math
- Test cost calculation
- Test device CRUD operations
- Test error handling (device offline, connection timeout)
- Test dev mode returns mock data

### 1.6 Verification

```bash
# Start the app
BALUPI_MODE=dev python3 -m uvicorn app.main:app --port 8000

# Check energy endpoints
curl http://localhost:8000/api/energy/current
curl http://localhost:8000/api/energy/summary
curl http://localhost:8000/api/tapo/devices

# Check scheduler is running
curl http://localhost:8000/api/health
# Should show scheduler status in response
```

---

## Phase 2 — NAS Handshake, WoL & DNS

Depends on Phase 1 (uses Tapo power data for dual NAS detection). Also requires BaluHost-side changes (already implemented in BaluHost repo).

### 2.1 NAS State Machine — `backend/app/services/nas_state_machine.py`

Simple Python class with JSON persistence. No library needed.

```python
class NasState(str, Enum):
    UNKNOWN = "unknown"
    OFFLINE = "offline"
    BOOTING = "booting"
    ONLINE = "online"
    SHUTTING_DOWN = "shutting_down"

VALID_TRANSITIONS = {
    NasState.UNKNOWN: {NasState.ONLINE, NasState.OFFLINE},
    NasState.OFFLINE: {NasState.BOOTING, NasState.ONLINE},
    NasState.BOOTING: {NasState.ONLINE, NasState.OFFLINE},
    NasState.ONLINE: {NasState.SHUTTING_DOWN, NasState.OFFLINE},
    NasState.SHUTTING_DOWN: {NasState.OFFLINE, NasState.ONLINE},
}

class NasStateMachine:
    STATE_FILE = "/data/handshake/nas_state.json"

    def __init__(self):
        self._load()

    def transition(self, new_state: NasState) -> bool:
        """Transition to new state. Returns True if valid. Persists to disk."""

    @property
    def state(self) -> NasState: ...

    @property
    def since(self) -> datetime: ...

    def _load(self) -> None: ...
    def _save(self) -> None: ...
```

**Side Effects on Transitions** (call after successful transition):

| Transition | Action |
|------------|--------|
| `* -> online` | Switch DNS to NAS-IP, flush inbox (rsync) |
| `* -> offline` | Switch DNS to Pi-IP |
| `online -> shutting_down` | Store received snapshot |
| `offline -> booting` | Send WoL magic packet |

### 2.2 Heartbeat Service — `backend/app/services/heartbeat_service.py`

```python
class HeartbeatService:
    POLL_INTERVAL = 30          # seconds, normal mode
    FAST_POLL_INTERVAL = 5      # seconds, after WoL
    FAILURE_THRESHOLD = 3       # consecutive failures = offline
    POLL_TIMEOUT = 5            # seconds per request

    async def poll_nas_health(self) -> bool:
        """Check NAS /api/health. Returns True if reachable."""

    async def run_heartbeat_loop(self) -> None:
        """Main loop. Runs as background task (not APScheduler — needs dynamic interval)."""
```

**Dual Detection** (combine heartbeat + Tapo power):
- HTTP heartbeat OK = definitely online
- HTTP fail + power >30W = service crashed but hardware on (rare)
- HTTP fail + power <2W = definitely off
- HTTP fail + power 2-15W = standby/sleep

Run as `asyncio.create_task()` in lifespan startup, not via APScheduler (heartbeat needs dynamic polling intervals — faster after WoL, slower in steady state).

### 2.3 Handshake Endpoints — `backend/app/api/routes/handshake.py`

New route file. All endpoints verify HMAC-SHA256 signature (no JWT).

```python
# HMAC verification dependency
async def verify_hmac_signature(request: Request) -> None:
    """
    Verify X-Balupi-Timestamp and X-Balupi-Signature headers.

    Signature = HMAC-SHA256(
        shared_secret,
        f"{method}:{path}:{timestamp}:{sha256(body)}"
    )

    Reject if timestamp is >60s old (replay protection).
    Raise HTTPException(401) on failure.
    """
```

**Endpoints:**

```
POST /api/handshake/nas-going-offline
  Body = snapshot JSON from NAS.
  -> Store snapshot in /data/snapshot/snapshot.json
  -> Transition state machine: * -> shutting_down
  -> Switch DNS (baluhost.local -> Pi-IP)
  -> Response: { "acknowledged": true, "dns_switched": true }

POST /api/handshake/nas-coming-online
  NAS calls this after startup.
  -> Transition state machine: * -> online
  -> Flush inbox (rsync Pi->NAS, --remove-source-files)
  -> Switch DNS (baluhost.local -> NAS-IP)
  -> Response: { "acknowledged": true, "inbox_flushed": true, "files_transferred": N }

GET /api/handshake/status
  Public endpoint (no HMAC needed, but requires JWT auth).
  -> { "nas_state": "online", "since": "...", "last_snapshot": "...", "inbox_size_mb": 12.5 }
```

The HMAC signing format matches what BaluHost sends (see `backend/app/services/balupi_handshake.py` in BaluHost repo):

```python
# Signing format (both sides must agree):
body_bytes = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
body_hash = hashlib.sha256(body_bytes).hexdigest()
message = f"{method}:{path}:{timestamp}:{body_hash}"
signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
```

### 2.4 WoL Route — `backend/app/api/routes/nas.py`

Wire the existing stub to the real WoL utility + state machine:

```python
@router.post("/wol")
async def wake_nas(current_user = Depends(get_current_user)):
    previous_state = state_machine.state

    # Check if WoL makes sense (via Tapo power reading)
    power = await tapo_service.get_nas_plug_power()
    if power and power > 30:
        raise HTTPException(400, "NAS appears to be already running")
    if power is not None and power < 2:
        raise HTTPException(400, "NAS has no power (plug off?). Turn on the smart plug first.")

    # Send WoL
    from app.utils.wol import send_wol
    send_wol(settings.nas_mac_address)

    # Transition state
    state_machine.transition(NasState.BOOTING)

    # Switch heartbeat to fast polling
    heartbeat_service.set_fast_poll()

    return {
        "wol_sent": True,
        "nas_previous_state": previous_state,
        "estimated_boot_time_s": 60,
    }
```

### 2.5 DNS Switching via Pi-hole v6 — `backend/app/services/dns_service.py`

Pi-hole v6 uses a REST API with session-based auth:

```python
import httpx

class PiholeClient:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url  # e.g. "http://localhost/api"
        self.password = password
        self._sid: str | None = None

    async def _auth(self) -> str:
        """Get session ID (SID) from Pi-hole."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/auth",
                json={"password": self.password},
            )
            data = resp.json()
            self._sid = data["session"]["sid"]
            return self._sid

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Authenticated request with auto-retry on 401."""
        if not self._sid:
            await self._auth()
        async with httpx.AsyncClient() as client:
            headers = {"sid": self._sid}
            resp = await client.request(
                method, f"{self.base_url}{path}",
                headers=headers, **kwargs,
            )
            if resp.status_code == 401:
                await self._auth()
                headers = {"sid": self._sid}
                resp = await client.request(
                    method, f"{self.base_url}{path}",
                    headers=headers, **kwargs,
                )
            return resp.json()

    async def set_dns_host(self, ip: str, hostname: str) -> None:
        """Add/update a local DNS A record."""
        # Pi-hole v6: PUT /api/config/dns/hosts/{IP %20 HOSTNAME}
        encoded = f"{ip} {hostname}".replace(" ", "%20")
        await self._request("PUT", f"/config/dns/hosts/{encoded}")

    async def remove_dns_host(self, ip: str, hostname: str) -> None:
        """Remove a local DNS A record."""
        encoded = f"{ip} {hostname}".replace(" ", "%20")
        await self._request("DELETE", f"/config/dns/hosts/{encoded}")

    async def switch_baluhost_dns(self, target_ip: str) -> None:
        """
        Switch baluhost.local to point to target_ip.
        Removes old record first, then adds new one.
        """
        hostname = "baluhost.local"
        # Remove both possible records (NAS and Pi IPs)
        for ip in [settings.nas_ip, settings.pi_ip]:
            try:
                await self.remove_dns_host(ip, hostname)
            except Exception:
                pass  # May not exist
        # Add new record
        await self.set_dns_host(target_ip, hostname)
```

**Config needed**: `BALUPI_PIHOLE_URL` (default `http://localhost`), `BALUPI_PIHOLE_PASSWORD`.

**TTL**: Pi-hole v6 uses 2 seconds TTL for custom DNS by default. This is fine for LAN.

### 2.6 Inbox Flush — in Handshake Service

```python
import asyncio

async def flush_inbox() -> int:
    """
    rsync /smb/inbox/ to NAS, removing successfully transferred files.
    Returns number of files transferred.
    """
    result = await asyncio.create_subprocess_exec(
        "rsync", "-avz", "--remove-source-files",
        "/smb/inbox/",
        f"{settings.nas_ssh_user}@{settings.nas_ip}:{settings.nas_inbox_path}/",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await result.communicate()

    if result.returncode != 0:
        logger.error("Inbox flush failed: %s", stderr.decode())
        return 0

    # Count transferred files from rsync output
    lines = stdout.decode().splitlines()
    transferred = sum(
        1 for line in lines
        if not line.startswith(("sending", "sent", "total", ""))
        and line.strip()
    )

    logger.info("Inbox flush: %d files transferred", transferred)
    return transferred
```

**Security**: Use SSH key auth for rsync (no password in config). Set up SSH key pair during deployment.

### 2.7 Snapshot Endpoint — `backend/app/api/routes/snapshot.py`

```python
@router.get("/snapshot")
async def get_snapshot(current_user = Depends(get_current_user)):
    """Serve the last NAS snapshot as JSON."""
    snapshot_path = Path("/data/snapshot/snapshot.json")
    if not snapshot_path.exists():
        raise HTTPException(404, "No snapshot available")
    return json.loads(snapshot_path.read_text())
```

### 2.8 Tests

Create:
- `tests/test_state_machine.py` — All transitions, invalid transitions, persistence, edge cases
- `tests/test_heartbeat.py` — Polling logic, failure counting, state transitions, dual detection
- `tests/test_handshake.py` — HMAC verification (valid, expired, wrong sig), snapshot storage, DNS switch
- `tests/test_dns_service.py` — Pi-hole API calls (mocked httpx)
- `tests/test_inbox.py` — rsync mock, error handling, file counting

### 2.9 Verification

```bash
# WoL
curl -X POST http://pi:8000/api/nas/wol -H "Authorization: Bearer $TOKEN"
# Expected: {"wol_sent": true, "nas_previous_state": "offline"}

# Handshake status
curl http://pi:8000/api/handshake/status -H "Authorization: Bearer $TOKEN"
# Expected: {"nas_state": "online", "since": "...", "last_snapshot": "2026-02-28T22:00:00Z"}

# Simulate NAS shutdown (from NAS side):
# sudo systemctl stop baluhost-backend
# Pi log: "Received shutdown snapshot, switching DNS to Pi"

# Verify DNS switched
nslookup baluhost.local
# Should resolve to Pi IP when NAS is offline
```

---

## Implementation Order

```
Step 0: Cleanup — Remove unused cache/sync files
Step 1: Tapo Service (connect, discover, read, toggle, caching)
Step 2: Energy Service (sampling, aggregation, cost calc)
Step 3: APScheduler integration in main.py
Step 4: Wire energy + tapo routes to services
Step 5: Tests for Phase 1
Step 6: Verify Phase 1 end-to-end

Step 7: NAS State Machine (states, transitions, persistence)
Step 8: Heartbeat Service (polling, failure detection)
Step 9: DNS Service (Pi-hole v6 API client)
Step 10: Handshake endpoints (HMAC auth, snapshot storage, inbox flush)
Step 11: WoL route wiring
Step 12: Snapshot serving endpoint
Step 13: Tests for Phase 2
Step 14: Verify Phase 2 end-to-end
```

---

## Key Config Variables (Already in `config.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `BALUPI_MODE` | `dev` | `dev` = mock data, `prod` = real hardware |
| `BALUPI_TAPO_USERNAME` | `""` | TP-Link cloud email |
| `BALUPI_TAPO_PASSWORD` | `""` | TP-Link cloud password |
| `BALUPI_NAS_URL` | `""` | NAS API URL for health checks |
| `BALUPI_NAS_MAC` | `""` | NAS MAC for WoL |
| `BALUPI_NAS_IP` | `""` | NAS IP for DNS switching |
| `BALUPI_HANDSHAKE_SECRET` | `""` | Shared HMAC secret (32+ chars) |
| `BALUPI_ENERGY_POLL_INTERVAL` | `30` | Seconds between Tapo polls |
| `BALUPI_ENERGY_PRICE_CT_KWH` | `30.0` | Default electricity price |
| `BALUPI_NAS_POWER_THRESHOLD_W` | `30.0` | Watts above = NAS active |

**Add to config if missing:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `BALUPI_PIHOLE_URL` | `http://localhost` | Pi-hole API base URL |
| `BALUPI_PIHOLE_PASSWORD` | `""` | Pi-hole admin password |
| `BALUPI_PI_IP` | `""` | Pi's own IP for DNS switching |
| `BALUPI_NAS_INBOX_PATH` | `/data/inbox` | NAS-side inbox path for rsync |
| `BALUPI_NAS_SSH_USER` | `baluhost` | SSH user for rsync |

---

## Dev Mode Behavior

When `BALUPI_MODE=dev`:

- **Tapo**: Return mock devices with random power values (50-80W for NAS, 3-5W for others)
- **Energy sampling**: Generate synthetic data points
- **Heartbeat**: Always return "online" or configurable via env var
- **DNS switching**: Log the switch but don't call Pi-hole API
- **WoL**: Log the magic packet but don't send it
- **rsync**: Log the command but don't execute it
- **Snapshot**: Use a static example snapshot JSON

---

## Constraints (Pi 3B+)

- 1 GB RAM total: 1 Uvicorn worker, no PostgreSQL, ~225 MB budget
- No heavy computation — Tapo polling is lightweight (HTTP calls)
- SQLite with WAL mode — good for single-writer workloads
- USB 2.0 HDD — ~35 MB/s, sufficient for SMB + inbox
- APScheduler jobs must be lightweight and non-blocking (use async)
- Connection caching is critical — don't create new Tapo/HTTP connections per poll

---

## Security Notes

- HMAC shared secret must be identical on both NAS and Pi (32+ chars)
- No rate limiting needed (LAN-only, trusted network)
- No HTTPS needed (LAN-only, VPN for external access)
- Tapo credentials in `.env` only (not in DB)
- Snapshot contains no passwords, tokens, or private keys
- Use `asyncio.create_subprocess_exec()` with list args only (no shell=True)
- rsync via SSH key auth (no password storage)

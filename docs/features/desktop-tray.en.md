# Desktop Tray (KDE Plasma)

The BaluHost tray is a small icon in the Plasma panel. It shows whether there
are unread notifications from the NAS and raises critical events as desktop
notifications — without the web UI having to be open.

It is a separate console program from the Python extra
`baluhost-backend[tray]` and runs as a **systemd user unit** inside the desktop
session. No root, no system-service privileges: the tray only reads. On a
normal installation it lives at
`/opt/baluhost/backend/.venv/bin/baluhost-tray`.

---

## The icon

The BaluHost cat with a small dot in the lower right corner. Four states:

| State | Appearance | Meaning |
|---|---|---|
| `ok` | **green dot** | Connected, nothing unread |
| `warning` | yellow dot | At least one unread warning |
| `critical` | red dot | At least one unread critical notification |
| `offline` | desaturated, **no** dot | No connection — or not paired |

The quiet state carries a dot too, a green one. Without a badge, "everything
is fine" could not be told apart from "icon failed to load" or "state
unknown". Only `offline` has no dot: there the desaturation carries the
message, and a dot would be misleading — at that moment we precisely do not
know anything.

### Green is not a health statement

**Green means "nothing unread", not "the NAS is healthy."** Reading a
notification — in the web UI, on the phone, anywhere — turns the icon green
while the array stays degraded. The icon counts unread notifications; it does
not measure the state of the machine. That is what the dashboard is for.

Grey has two causes that call for different reactions. The tooltip says which
one it is:

- *"BaluHost — nicht erreichbar"* (unreachable) → wait, the tray reconnects on
  its own.
- *"BaluHost — nicht gekoppelt: baluhost-tray --pair"* (not paired) → act, see
  below.

---

## Pairing

```bash
/opt/baluhost/backend/.venv/bin/baluhost-tray --pair
```

The program lives inside the installation's venv and is therefore **not on
the PATH** — the bare name `baluhost-tray` does not work on the target machine
by itself. To save the typing, add a symlink:

```bash
sudo ln -s /opt/baluhost/backend/.venv/bin/baluhost-tray /usr/local/bin/baluhost-tray
```

An alias in `~/.bashrc` does the same. Either is an offer, not a
prerequisite; this document spells out the full path throughout. The program's
own messages — for instance the tooltip *"nicht gekoppelt: baluhost-tray
--pair"* — keep using the short name.

The program prints a **six digit code** and the URL to approve it. Confirm the
code in the web UI under **Devices** — done, the credentials land on disk.

This works **while the service is running**: pairing takes its own lock, so
nothing has to be stopped first.

> **Important: restart the service after pairing.**
>
> ```bash
> systemctl --user restart baluhost-tray
> ```
>
> The background worker reads the credentials **only at startup**. Without a
> restart the running service never picks up the fresh tokens — the icon would
> stay grey even though pairing succeeded. This is the most common stumbling
> block during first setup.

On the very first run the restart is needed anyway: without existing
credentials the unit does not start at all (see *Autostart*).

---

## Menu and click

Right-click the icon:

| Entry | Effect |
|---|---|
| **BaluHost oeffnen** | Opens the web UI in the default browser |
| **Eine Stunde stumm** | Holds popups back for one hour (toggle) |
| **Geraete in der Web-UI** | Opens the devices page — where you pair and revoke |
| **Beenden** | Quits the tray for this session |

A plain left-click on the icon also opens the web UI.

The menu entry is deliberately called *"Geraete in der Web-UI"* (devices in the
web UI) and not *"Re-pair"*: it cannot restore the pairing by itself, that
needs `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` on the console.

---

## Behaviour while gaming

While a game is running, popups are **held back, not dropped**. The icon still
changes colour — anyone glancing at the panel mid-game sees red.

After the gaming session everything held is delivered, normally within 30
seconds (that is how often the tray asks). From **four** notifications on, a
single collected line replaces the burst: *"N neue kritische Meldungen"* (N new
critical notifications).

On top of that, Plasma's own **Do Not Disturb** applies. The tray notifies
through the standard `org.freedesktop.Notifications` interface, so every rule
Plasma enforces anyway holds here too — the tray does not have to detect
anything itself.

---

## When a popup arrives late

The backend runs with four worker processes. A live notification only reaches
the connections of the process it was created in — and the tray hangs off
exactly one of them. So it can happen that the icon turns red while the popup
stays away.

The tray compensates: at every resync — on connect and every ten minutes after
that — it catches up popups for critical notifications it has never seen. A
missed popup is therefore **late, not lost**.

Two things follow from this:

- The **first** resync after start raises no popups. Otherwise every restart
  would greet you with the entire unread backlog at once.
- During acceptance, a test notification may arrive without a popup and only
  show up minutes later. That is this behaviour, not a fault in the tray.

The cause sits in the backend, not in the tray, and is tracked as
[issue #685](https://github.com/Xveyn/BaluHost/issues/685). Catching up is a
mitigation, not a fix.

---

## Quiet mode

**Eine Stunde stumm** ("mute for an hour") in the menu holds all popups back.
Afterwards — or as soon as the checkmark is removed again — whatever was held
is delivered, by the same rule as for gaming (collected from four
notifications on).

Held popups are never lost. Seeing a notification late is better than not
seeing it at all.

---

## Where the credentials live

```
~/.baluhost/tray-tokens.json     (file 0600, directory 0700)
```

It holds an access token and a refresh token.

> **This is a full user token.** Anyone who can read the file can use the API
> with the privileges of that account — not just fetch notifications. That is
> why it belongs to nobody but the user, and why it is written with `0600`
> from the first byte rather than chmod'ed afterwards.

On machines with several logins, that is the reason to pair the tray only
within your own account.

---

## Revoking the pairing

Remove the device in the web UI under **Devices**. The tray notices on its next
request, drops into the *not paired* state (grey icon), says so **once** with
*"Kopplung aufgehoben — bitte neu koppeln"* (pairing revoked — please pair
again) and deletes the credentials from disk. After that it stays quiet: there
is no storm of requests in the log.

Only the background worker stops here — the process itself keeps running with
a grey icon, so the tooltip can keep carrying the explanation.

To pair again, run `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` and
restart the service (see above).

---

## Autostart and installation

The installer places a **user unit**:

```
~/.config/systemd/user/baluhost-tray.service
```

It is bound to `graphical-session.target` — the tray belongs to the desktop
session, not to system startup.

The target user is determined separately at install time and is **not** derived
from the BaluHost service account: a user unit in the service account's home
starts in no desktop session. The default is `SUDO_USER`; to set it explicitly:

```bash
sudo TRAY_DESKTOP_USER=sven TRAY_WEB_URL=https://baluhost.local ./install.sh
```

If no desktop user can be determined, the installer reports that and skips the
step instead of writing the unit into the wrong home.

> **The autostart can be missing even though the unit is there.** A user unit
> can only be enabled from a running session of the target user. A first
> install over SSH as root has none — that is the normal case, not the
> exception. The unit then does sit in `~/.config/systemd/user/`, but
> `systemctl --user enable` never ran, there is no symlink in
> `graphical-session.target.wants/`, and `WantedBy=` has no effect. The
> installer says so as a **warning**. Catch it up once, logged in as the
> target user:
>
> ```bash
> systemctl --user enable baluhost-tray.service
> ```
>
> Whether it is needed is answered by `systemctl --user status baluhost-tray`
> — point 15 of the acceptance list below checks exactly that.

### One-time: install the `[tray]` extra

The installation's venv does **not** contain the extra. That is deliberate: Qt
does not belong on a headless server install, and the tray is an opt-in for
the one machine that is also a desktop. Exactly once:

```bash
sudo /opt/baluhost/backend/.venv/bin/pip install -e '/opt/baluhost/backend[tray]'
```

Without this step the unit is created **and enabled**, but the tray exits
immediately at startup with *"PyQt6 fehlt"* (PyQt6 is missing). The installer
prints exactly this command as a hint when it places the unit.

The full path into the venv is a necessity, not convenience: a bare
`pip install` would target the system Python, which on Debian 13 is
"externally managed" (PEP 668) and refuses the installation.

### Three properties of the unit are deliberate

- **`ConditionPathExists=%h/.baluhost/tray-tokens.json`** — without a pairing
  the unit does not even start. This prevents *no* restart storm: the unpaired
  case exits with 0, and `Restart=on-failure` does not restart on 0 anyway.
  The gain is a readable state — `systemctl --user status` shows
  `condition failed`, which reads as "not set up yet". A start that exits
  immediately and cleanly would look like a failed start instead.
- **`Restart=on-failure`**, not `always` — the exit codes carry meaning: `0`
  means *permanently done* (not paired, a second instance is running, the extra
  is missing), where a restart does not help. `3` means *possibly transient*:
  no session bus or no tray host in the session — at login the tray can simply
  be ready before Plasma is — **or** a failure passed through from the
  background worker, whose cause nobody knows. There a restart genuinely does
  help.
- **`StartLimitIntervalSec=300` with `StartLimitBurst=5`** — the unit sets its
  own start limit. The systemd default is a ten-second window at five
  attempts; with `RestartSec=10s` at most one start falls into each window, the
  five are never reached, and a permanent exit 3 would keep restarting
  **forever** every ten seconds. Five minutes hold the five attempts, and then
  it stops.

---

## Service and logs

```bash
systemctl --user status baluhost-tray      # Is it running?
systemctl --user restart baluhost-tray     # Required after --pair
systemctl --user enable  baluhost-tray     # Turn on autostart
journalctl --user -u baluhost-tray -f      # Follow the log
```

For more detail in the journal:

```bash
systemctl --user set-environment BALUHOST_TRAY_LOG_LEVEL=DEBUG
systemctl --user restart baluhost-tray
```

Every failure puts a plain sentence in the journal saying what to do. In the
unexpected case the traceback is **also** there (`logger.exception` in
`tray.py`): the sentence is for the human in front of it, the traceback for
finding the cause.

---

## When something is wrong

| Symptom | Cause | Remedy |
|---|---|---|
| No icon, unit "inactive (dead)", condition failed | Never paired | `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair`, then `systemctl --user restart baluhost-tray` |
| Icon stays grey, tooltip *"nicht gekoppelt"* | Just paired, service not restarted | `systemctl --user restart baluhost-tray` |
| Icon stays grey, tooltip *"nicht erreichbar"* | Backend down or network gone | Wait; the tray reconnects on its own |
| Icon turns red but no popup | The notification was created in a different backend worker process ([#685](https://github.com/Xveyn/BaluHost/issues/685)) | Wait up to ten minutes; the tray catches it up at the next resync |
| Exits with code 3 at login | Tray was ready before Plasma — **or** the background worker failed unexpectedly | At login: nothing, `Restart=on-failure` tries again. Otherwise check the journal (`journalctl --user -u baluhost-tray`): if it says *"Tray-Hintergrund beendet"* or shows a traceback, it is a real crash and not a startup-order problem |
| *"PyQt6 fehlt"* | Extra not installed | `sudo /opt/baluhost/backend/.venv/bin/pip install -e '/opt/baluhost/backend[tray]'` |
| *"BaluHost Tray laeuft bereits in dieser Sitzung."* | Second instance | Nothing; the first one is already doing the right thing |

After a connection drop the tray only speaks up if the outage lasted **longer
than two minutes** — a flapping backend must not cause a rain of popups. A
snoozed notification colours the icon again once the snooze expires, at the
latest on the resync that runs every ten minutes.

---

## Acceptance on the target machine

Not a CI substitute. PyQt6 is not installed on the development machine and the
tray cannot be started there — this list is written for a human at the real
machine.

### Prerequisites

- [ ] **0a.** Install the extra once:
      `sudo /opt/baluhost/backend/.venv/bin/pip install -e '/opt/baluhost/backend[tray]'`
- [ ] **0b.** `test -f ~/.config/systemd/user/baluhost-tray.service` → the file
      must be there. If it is missing, module 10 took the *"Kein
      Desktop-Benutzer bekannt"* branch (no desktop user known) or *"Kein Home
      fuer …"* (no home). Remedy: re-run the installation with
      `TRAY_DESKTOP_USER=<name>`.
- [ ] **0c.** `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` → a six
      digit code appears; approve it in the web UI under **Devices**; output
      `Gekoppelt.`
- [ ] **0d.** **`systemctl --user restart baluhost-tray`** — mandatory. The
      worker reads the credentials **only at startup**; without a restart a
      running service never picks up the fresh tokens and the icon stays grey
      even though pairing succeeded. Before the first pairing the unit does not
      start at all because of `ConditionPathExists`
      (`systemctl --user status` shows `condition failed`) — that is by design,
      not a fault.

### The twelve points

- [ ] **1.** `systemctl --user start baluhost-tray` → the icon appears in the panel.
- [ ] **2.** Stop the backend → the icon turns grey, **one** message, then quiet.
- [ ] **3.** Start the backend → the icon turns green; a message only for an
      outage longer than two minutes.
- [ ] **4.** Raise a critical test notification → red icon plus popup.
      If the popup stays away while the icon turns red, that is **not a
      failure**: the notification was created in a different worker process.
      Wait up to ten minutes, the tray catches it up at the next resync (see
      *When a popup arrives late*). Only if it is still missing then does this
      point fail.
      `POST /api/notifications` is **admin-only** (`get_current_admin`) and
      takes a `NotificationCreate` body. For the tray to react at all,
      `notification_type` must be **`critical`** — `warning` only colours the
      icon and raises no popup — **and** `user_id` must hit the paired account
      (`null` is a broadcast and reaches admin accounts only). `category` must
      come from the fixed list: `raid`, `smart`, `backup`, `scheduler`,
      `system`, `security`, `sync`, `vpn`, `lifecycle`.

      ```bash
      # Fetch an admin token (with 2FA enabled the login returns a
      # pending_token instead — then take the token from the logged-in web UI)
      TOKEN=$(curl -s -X POST https://baluhost.local/api/auth/login \
        -H 'Content-Type: application/json' \
        -d '{"username":"admin","password":"<password>"}' \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

      # user_id is the id of the paired account, not the admin's
      curl -X POST https://baluhost.local/api/notifications \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d '{
              "user_id": 1,
              "notification_type": "critical",
              "category": "system",
              "title": "Abnahme Schritt 4",
              "message": "Testmeldung fuer das Desktop-Tray",
              "priority": 3
            }'
      ```

      There is no spontaneously degrading array to simulate:
      `emit_raid_degraded_sync` is only called from `degrade()`, i.e. when
      BaluHost itself fails a device. Alternative without HTTP:
      `simulate_failure` in the dev backend.
- [ ] **5.** Swipe the same notification away **on the phone** → the icon turns
      green without further action.
- [ ] **6.** Snooze a notification with a short expiry → icon green, and red
      again after ten minutes at the latest (resync).
- [ ] **7.** Start a game full screen — **directly from Steam, not through
      BaluHost** — and raise a test notification → no popup, red icon.
- [ ] **8.** Quit the game → the held notification is delivered within 30
      seconds.
- [ ] **9.** Choose "Eine Stunde stumm" and raise a notification → no popup;
      choose the menu entry again or wait → delivery.
- [ ] **10.** Start a second
      `/opt/baluhost/backend/.venv/bin/baluhost-tray` → it exits with a notice
      ("BaluHost Tray laeuft bereits in dieser Sitzung.", exit code 0).
- [ ] **11.** `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair` while the
      service is running → it shows a code instead of exiting.
- [ ] **12.** Revoke the pairing in the web UI → grey icon, one message, no
      storm of requests in the log.

### After point 12

- [ ] **13.** Pair again after the revocation:
      `/opt/baluhost/backend/.venv/bin/baluhost-tray --pair`, approve,
      **then `systemctl --user restart baluhost-tray`** → the icon turns green
      again. Without the restart it stays grey — the same trap as in 0d, for
      the same reason. It is set a second time exactly here because point 11
      shows that pairing works while the service runs: it does, but the service
      only *adopts* the new tokens after a restart.

### Check the autostart

- [ ] **14.** Log out and back in → the icon is there without any action
      (`WantedBy=graphical-session.target`).
- [ ] **15.** `systemctl --user status baluhost-tray` shows `enabled`;
      `journalctl --user -u baluhost-tray` contains no tracebacks.

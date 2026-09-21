# Desktop Tray (KDE Plasma)

The BaluHost tray is a small icon in the Plasma panel. It shows whether there
are unread notifications from the NAS and raises critical events as desktop
notifications — without the web UI having to be open.

It is a separate console program (`baluhost-tray`) from the Python extra
`baluhost-backend[tray]` and runs as a **systemd user unit** inside the desktop
session. No root, no system-service privileges: the tray only reads.

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
baluhost-tray --pair
```

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
> The background worker reads the credentials **only at startup** and exits
> when the pairing goes away. Without a restart the running service never
> picks up the fresh tokens — the icon would stay grey even though pairing
> succeeded. This is the most common stumbling block during first setup.

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
needs `baluhost-tray --pair` on the console.

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

To pair again, run `baluhost-tray --pair` and restart the service (see above).

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

Two properties of the unit are deliberate:

- **`ConditionPathExists=%h/.baluhost/tray-tokens.json`** — without a pairing
  the unit does not even start. Otherwise it would start, exit immediately and
  be revived every ten seconds until the start limit kicks in.
- **`Restart=on-failure`**, not `always` — the exit codes carry meaning: `0`
  means *permanently done* (not paired, a second instance is running, the extra
  is missing), where a restart does not help. `3` means *possibly transient*
  (no session bus, no tray host in the session), where it genuinely does — at
  login the tray can simply be ready before Plasma is.

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

Failures appear as a plain sentence, not as a traceback — nobody reads a
traceback in the journal.

---

## When something is wrong

| Symptom | Cause | Remedy |
|---|---|---|
| No icon, unit "inactive (dead)", condition failed | Never paired | `baluhost-tray --pair`, then `systemctl --user restart baluhost-tray` |
| Icon stays grey, tooltip *"nicht gekoppelt"* | Just paired, service not restarted | `systemctl --user restart baluhost-tray` |
| Icon stays grey, tooltip *"nicht erreichbar"* | Backend down or network gone | Wait; the tray reconnects on its own |
| Exits with code 3 at login | Tray was ready before Plasma | Nothing — `Restart=on-failure` tries again |
| *"PyQt6 fehlt"* | Extra not installed | `pip install 'baluhost-backend[tray]'` |
| *"BaluHost Tray laeuft bereits in dieser Sitzung."* | Second instance | Nothing; the first one is already doing the right thing |

After a connection drop the tray only speaks up if the outage lasted **longer
than two minutes** — a flapping backend must not cause a rain of popups. A
snoozed notification colours the icon again once the snooze expires, at the
latest on the resync that runs every ten minutes.

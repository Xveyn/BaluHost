# Feature Dependencies

Single source of truth for which system packages each BaluHost feature needs,
how to enable it, and which setup script configures it.

## Supported OS

BaluHost's production installer supports **Debian 12 (bookworm) and Debian 13
(trixie) only**. The preflight check (`deploy/install/modules/01-preflight.sh`)
aborts on any other OS. This is deliberate: package names, systemd unit
assumptions, and the deploy scripts are tested only on Debian. Ubuntu, Fedora,
Arch, and RHEL are not supported. (The mDNS script `install-avahi.sh` happens to
handle several distros, but the rest of the install chain does not — there is no
half-supported path.)

## What a default install gives you

Running `sudo ./install.sh` without enabling any optional feature installs the
**core NAS**: PostgreSQL, Nginx, the FastAPI backend, the built frontend, and
the base toolchain (Python, Node, git, build-essential, curl). Files, users,
monitoring, and the web UI work immediately.

Everything in the table below is **off by default** and stays dark until enabled.

## Dependency matrix

| Feature | Packages | Setup script | Default install |
|---|---|---|---|
| RAID array management | `mdadm` | `deploy/scripts/install-hardware-sudoers.sh` | off |
| Disk health (SMART) | `smartmontools` | `deploy/scripts/install-hardware-sudoers.sh` | off |
| WireGuard VPN | `wireguard-tools` | `deploy/scripts/setup-wireguard.sh` | off |
| Cloud import | `rclone` | (none — runs as the service user) | off |
| Samba / SMB sharing | `samba`, `samba-common-bin` | `deploy/samba/setup-samba.sh` | off |
| NFS sharing | `nfs-kernel-server` | `deploy/nfs/setup-nfs.sh` | off |
| Windows discovery (WS-Discovery) | `wsdd2` / `wsdd` | `deploy/wsdd/setup-wsdd.sh` | off |
| mDNS / Bonjour (`baluhost.local`) | `avahi-daemon`, `avahi-utils` | `deploy/scripts/install-avahi.sh` | off |

RAID and SMART share one sudoers file (`/etc/sudoers.d/baluhost-hardware`); the
installer renders it once when either is enabled.

## How to enable features

### During installation (interactive)

The installer asks, per feature, whether to enable it. Answer `y` to pull in the
packages and run that feature's setup.

### Non-interactive / after installation

Set the flag(s) in `/etc/baluhost/install.conf` and re-run the optional-features
module:

```bash
# /etc/baluhost/install.conf
ENABLE_RAID=true
ENABLE_VPN=true
```

```bash
sudo /opt/baluhost/deploy/install/install.sh --module 14-optional-features
```

Available flags: `ENABLE_RAID`, `ENABLE_SMART`, `ENABLE_VPN`, `ENABLE_CLOUD`,
`ENABLE_SAMBA`, `ENABLE_NFS`, `ENABLE_WSDD`, `ENABLE_MDNS`. Unset = `false`.

### Manual alternative

Each setup script can be run directly (as root), e.g.:

```bash
sudo SERVICE_USER=<baluhost-user> STORAGE_GROUP=<baluhost-group> \
    bash /opt/baluhost/deploy/samba/setup-samba.sh
```

## Per-feature notes

- **RAID / SMART** — backend uses `mdadm` and `smartctl`; without them RAID and
  disk-health pages show no data. The shared hardware sudoers grants the service
  user the specific commands it needs.
- **VPN** — `wireguard-tools` provides `wg`/`wg-quick`; `setup-wireguard.sh`
  installs the per-command sudoers and enables IP forwarding. A reboot may be
  required for the WireGuard kernel module.
- **Cloud import** — `rclone` only; no sudoers, runs as the service user.
- **Samba / NFS** — each setup script installs its package, writes a hardened
  config, creates the share/export config owned by the service user, and installs
  scoped sudoers.
- **WS-Discovery / mDNS** — make BaluHost discoverable from Windows Explorer and
  from Bonjour/zeroconf clients respectively.

## Verifying an enabled feature

After enabling, confirm the package and (where applicable) the service:

```bash
dpkg -s mdadm | grep Status        # package installed
systemctl status smbd              # Samba running (SAMBA)
sudo -n -u <baluhost-user> wg show  # VPN sudoers in place (VPN)
```

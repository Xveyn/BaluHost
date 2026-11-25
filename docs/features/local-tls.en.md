# Fixed Home-Network Address (plugin `local_tls`)

The plugin keeps a DuckDNS name (e.g. `mynas.duckdns.org`) pointed at the box's
LAN IP and obtains a real Let's Encrypt certificate for it via DNS-01 (`lego`).
Browsers trust it without a warning, and the box never has to be reachable from
the internet. The plugin is **off** by default.

## Prerequisites

- A DuckDNS domain and its token.
- `lego` 4.35 or newer (Debian 13: `trixie-backports`):
  `sudo apt install -t trixie-backports lego`. The installer can do this
  optionally with `ENABLE_LEGO=true` (module `14-optional-features`, Debian 13
  only). Afterwards run `lego --version` and check that the card says
  "installed (4.35…)" — "version could not be read" means `lego --version` gave
  no usable output.
- nginx already running with HTTPS (`deploy/nginx/baluhost-https.conf`).
- An email address for Let's Encrypt is optional (lego 4.30 or newer).

## Setup

1. Enable the plugin (Settings → Plugins), then
   `sudo systemctl restart baluhost-backend` — plugin routes are mounted only at
   startup; without the restart the card says "Could not load status".
2. Set domain and provider in the plugin settings (optional: network interface,
   email, `staging` for testing).
3. Settings → Integrations → "Fixed local address" card: save the DuckDNS
   token. It is stored encrypted and never shown again.
4. Click "Renew now". The certificate is issued and installed under
   `/var/lib/baluhost/plugins/local_tls/live/`.
5. The card shows "Served by nginx: no", the reason "installed, nginx is not
   serving it yet" and the matching nginx snippet. Switch nginx over (below).

`staging` exercises the flow against the Let's Encrypt test environment (own
lego state, certificate not trusted). Switching back to production issues anew.

## Switching nginx

In **both** TLS blocks (`:443` and `:8443`) append the domain to the existing
`server_name` line (do not replace it) and replace the certificate paths:

```nginx
server_name mynas.duckdns.org <existing names>;
ssl_certificate     /var/lib/baluhost/plugins/local_tls/live/fullchain.pem;
ssl_certificate_key /var/lib/baluhost/plugins/local_tls/live/privkey.pem;
```

Then `sudo nginx -t && sudo systemctl reload nginx`. The card should now show
"Served by nginx: yes". Note: on BaluNode `sites-enabled/baluhost` is a separate file
next to `sites-available/baluhost` — update both.

## What happens in the background

- Every 300 s the plugin checks the LAN IP and updates DuckDNS when the IP or
  the domain changed, plus once a day as reconfirmation. The result of every
  attempt (including a failure and its reason) appears on the card under "Last
  DNS update".
- Daily (and at startup, waiting up to 60 s for the run lock) it checks the
  certificate: `lego run` for the first issue, otherwise `renew --days 30`.
- A new certificate goes to `releases/<UTC timestamp>/`, `live` is switched
  atomically; the last 3 releases are kept. nginx is then reloaded through the
  existing `sudo -n /usr/bin/systemctl reload nginx`. No new sudoers rule.
  Because nginx reloads gracefully (old workers keep serving the old certificate
  briefly), the plugin polls the served certificate for up to 15 s before
  deciding.
- First use, or nginx not switched yet: the certificate is only installed, no
  rollback. `live` is switched back to the previous release (with another
  reload) in two cases: (a) nginx was serving the plugin's previous certificate
  before and still does not serve the new one 15 s after the reload; (b) the nginx reload
  fails and a previous release exists. Without a previous release, a reload
  failure leaves `live` in place and the failure is reported.
- If lego's certificate fingerprint differs from the installed one, it is
  redeployed, so failed deploys are retried daily.
- In dev mode (`NAS_MODE=dev`) the data directory is
  `dev-storage/.system/local_tls`, nginx is never reloaded and "Served by nginx"
  stays "unknown".
- Admin notifications: `cert_expiring` (from 21 days before expiry, also when
  the token or domain has since been removed),
  `renew_failed`, `dns_update_failed`, `address_changed`; with cooldowns that
  reset on restart.

## Migrating BaluNode

The existing certbot certificate for `baluhost.duckdns.org` is valid until
2027-02-23.

Precondition: the service user may run `sudo -n /usr/bin/systemctl reload nginx`
(entry from `baluhost-deploy-sudoers`). Check as the service user:
`sudo -n -l | awk '/reload nginx/'` — if the line is missing, run
`deploy/scripts/install-deploy-sudoers.sh` once as root. Without it every reload
fails.

1. Install lego (`sudo apt install -t trixie-backports lego`).
2. Enable the plugin, `sudo systemctl restart baluhost-backend`, set domain and
   provider in the plugin settings.
3. Save the token under Settings → Integrations.
4. "Renew now".
5. Check the reload permission (above), then switch nginx (both TLS blocks `:443`/`:8443` including `server_name`; mind
   `sites-enabled` vs `sites-available`), `nginx -t`, reload.
6. Verify the card shows "Served by nginx: yes".
7. Retire the old renewal but **keep** the old certificate files: move
   `/etc/letsencrypt/renewal/baluhost.duckdns.org.conf` away (not
   `certbot delete` — that also deletes the files the fallback points at).
8. Only after one certificate change went through the plugin, remove the old
   files and the pipx certbot. A change is either a real renewal (at the
   earliest 30 days before expiry) or a staging test with a second, distinct
   certificate: enable `staging`, "Renew now" (card: served yes; the browser
   warns, the staging certificate is not trusted), disable `staging`, "Renew now"
   (card: served yes, no browser warning). Then
   `sudo certbot delete --cert-name baluhost.duckdns.org` and
   `sudo pipx uninstall certbot` or delete `/usr/local/bin/certbot`. Debian's
   `certbot.timer` may stay for other certificates.

Fallback: the old certificate paths stay valid until 2027-02-23 as long as
step 8 has not been done. If step 6 or the change in step 8 fails, point the nginx site back at them and reload.

## DNS rebind protection

Fritz!Box routers drop DNS answers pointing to private IPs. Without Pi-hole,
add the domain as an exception in the Fritz!Box (Home Network → Network →
Network Settings → DNS rebind protection).

## Troubleshooting

| Card shows | Cause / fix |
|---|---|
| lego missing / too old | `sudo apt install -t trixie-backports lego` |
| lego "version could not be read" | Run `lego --version` by hand; the output must contain a version |
| "Could not load status" right after enabling | `sudo systemctl restart baluhost-backend` |
| Last DNS update "failed" | The reason is shown next to it; usually a wrong token or no private LAN IP |
| Token "not set" | Save the token in the card |
| "No encryption key configured" | `VPN_ENCRYPTION_KEY` is missing; the token is refused rather than stored in plaintext |
| "A run is already in progress" | Wait briefly, retry |
| "Served by nginx: no" | Apply the nginx snippet and reload |
| Browser cannot resolve the domain | DNS rebind protection (see above) |

## Security

Only admins reach the routes. The token is Fernet-encrypted and never returned,
logged or audited. The service user can already rewrite the nginx site itself
(#862); the plugin does not change that. Real secret fields in the generic plugin
config are #863.

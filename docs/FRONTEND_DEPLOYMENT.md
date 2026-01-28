# Frontend Deployment Checkliste

Nach Änderungen am Frontend (`client/`) folgende Schritte ausführen:

## Quick Deploy

```bash
# 1. Build erstellen
cd /home/sven/projects/BaluHost/client
npm run build

bzw.: cd client && npm run build && sudo systemctl reload nginx 

# 2. nginx neuladen (falls config geändert)
sudo nginx -t && sudo systemctl reload nginx
```

Fertig. Änderungen sind sofort unter http://localhost bzw. http://baluhost.local sichtbar.

---

## Ersteinrichtung (einmalig)

```bash
# 1. Frontend bauen
cd /home/sven/projects/BaluHost/client
npm install
npm run build

# 2. nginx Config verlinken
sudo ln -sf /home/sven/projects/BaluHost/deploy/nginx/baluhost-http.conf /etc/nginx/sites-available/baluhost
sudo ln -sf /etc/nginx/sites-available/baluhost /etc/nginx/sites-enabled/baluhost
sudo rm -f /etc/nginx/sites-enabled/default  # optional

# 3. Config testen & starten
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx  # Autostart
```

---

## Troubleshooting

| Problem | Lösung |
|---------|--------|
| 502 Bad Gateway | Backend läuft nicht → `python start_prod.py` |
| 404 auf Unterseiten | `try_files` fehlt in nginx config |
| Alte Version sichtbar | Browser-Cache leeren (Ctrl+Shift+R) |
| Build schlägt fehl | `npm install` nochmal ausführen |

## Dateien

- **Build Output:** `client/dist/`
- **nginx Config:** `deploy/nginx/baluhost-http.conf`
- **Logs:** `/var/log/nginx/baluhost-*.log`

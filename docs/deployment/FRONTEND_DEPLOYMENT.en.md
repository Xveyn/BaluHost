# Frontend Deployment Checklist

After making changes to the frontend (`client/`), follow these steps:

## Quick Deploy

```bash
# 1. Create build
cd /home/sven/projects/BaluHost/client
npm run build

# or: cd client && npm run build && sudo systemctl reload nginx 

# 2. Reload nginx (if config changed)
sudo nginx -t && sudo systemctl reload nginx
```

Done. Changes are immediately visible at http://localhost or http://baluhost.local.

---

## Initial Setup (one-time)

```bash
# 1. Build frontend
cd /home/sven/projects/BaluHost/client
npm install
npm run build

# 2. Link nginx config
sudo ln -sf /home/sven/projects/BaluHost/deploy/nginx/baluhost-http.conf /etc/nginx/sites-available/baluhost
sudo ln -sf /etc/nginx/sites-available/baluhost /etc/nginx/sites-enabled/baluhost
sudo rm -f /etc/nginx/sites-enabled/default  # optional

# 3. Test config and start
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx  # Autostart
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| 502 Bad Gateway | Backend is not running -> `python start_prod.py` |
| 404 on subpages | `try_files` missing in nginx config |
| Old version visible | Clear browser cache (Ctrl+Shift+R) |
| Build fails | Run `npm install` again |

## Files

- **Build Output:** `client/dist/`
- **nginx Config:** `deploy/nginx/baluhost-http.conf`
- **Logs:** `/var/log/nginx/baluhost-*.log`

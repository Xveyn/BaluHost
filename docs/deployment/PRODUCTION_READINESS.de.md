# Produktionsreife-Checkliste

## Status

**Produktiv seit:** 25. Januar 2026  
**Server:** Debian 13, Ryzen 5 5600GT, 16 GB RAM, 250 GB NVMe SSD  
**Version:** 1.23.0

## Infrastruktur

| Komponente | Status | Details |
|-----------|--------|---------|
| Backend | Aktiv | FastAPI/Uvicorn, 4 Worker, Port 8000 |
| Frontend | Aktiv | Vite-Build, statische Dateien via Nginx |
| Datenbank | Aktiv | PostgreSQL 17.7, localhost:5432 |
| Reverse Proxy | Aktiv | Nginx, Port 80 (HTTP) |
| Auto-Start | Aktiv | Systemd-Services aktiviert |
| Logging | Aktiv | Strukturiertes JSON-Logging |

## Sicherheit

| Maßnahme | Status |
|----------|--------|
| CORS-Konfiguration | Konfiguriert |
| Rate Limiting | Aktiv (API: 100/s, Auth: 10/s) |
| SQL-Injection-Schutz | SQLAlchemy ORM |
| Security Headers | CSP, X-Frame-Options, HSTS, X-Content-Type-Options |
| Passwortrichtlinie | 8+ Zeichen, Groß/Klein/Zahl, Blacklist |
| Token-Verwaltung | Access (15 min) + Refresh (7 Tage) mit JTI |
| Audit-Logging | DB-basiert, alle sicherheitsrelevanten Aktionen |
| VPN-Schlüssel | Fernet-verschlüsselt |
| Sensible Daten | Redaction in Admin-DB-Inspektion |

## Tests

- **82 Testdateien**, 1465 Testfunktionen
- CI/CD-Pipeline via GitHub Actions
- Automatische Tests bei Push/PR

## Services

| Service | Funktion |
|---------|----------|
| Monitoring Orchestrator | CPU, RAM, Netzwerk, Disk I/O sammeln |
| Scheduler | Geplante Tasks (Backups, Cleanup) |
| WebDAV | Netzwerkdateizugriff |
| Power Management | CPU-Frequenz-Skalierung |
| Fan Control | PWM-Lüftersteuerung mit Temperaturkurven |
| Service Status | Health-Monitoring aller Dienste |

## Optionale Erweiterungen

| Erweiterung | Status |
|-------------|--------|
| SSL/HTTPS | Nicht konfiguriert (Zugang über VPN) |
| E-Mail-Benachrichtigungen | Nicht implementiert |
| Datenbank-Replikation | Nicht konfiguriert (Single-Instance) |

## Wartung

### Regelmäßige Aufgaben

- **Täglich:** RAID-Status prüfen (automatisch via Monitoring)
- **Wöchentlich:** SMART-Daten prüfen, Speicherplatz kontrollieren
- **Monatlich:** System-Updates, PostgreSQL VACUUM
- **Bei Bedarf:** Alembic-Migrationen nach Updates

### Backup

PostgreSQL-Backup:
```bash
pg_dump -U baluhost baluhost > backup_$(date +%Y%m%d).sql
```

Dateien:
```bash
rsync -av /opt/baluhost/storage/ /backup/storage/
```

---

**Letzte Aktualisierung:** April 2026

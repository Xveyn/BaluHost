# BaluHost Docker Quick Start Guide

Get BaluHost running in 5 minutes with Docker Compose!

## Prerequisites

- Docker Engine 20.10+ installed
- Docker Compose 2.0+ installed
- At least 2GB free RAM
- 10GB+ free disk space

## Quick Start

### 1. Clone and Navigate

```bash
cd /path/to/baluhost
```

### 2. Create Environment File

```bash
cp .env.production.example .env
```

### 3. Generate Secure Secrets

**CRITICAL**: Replace the default secret keys with secure random values:

```bash
# Generate SECRET_KEY
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"

# Generate TOKEN_SECRET
python -c "import secrets; print('TOKEN_SECRET=' + secrets.token_urlsafe(32))"

# Generate POSTGRES_PASSWORD
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

Copy these values into your `.env` file.

### 4. Update Environment Variables

Edit `.env` and set:

```bash
# Required - use the generated values from step 3
SECRET_KEY=<your-generated-secret-key>
TOKEN_SECRET=<your-generated-token-secret>
POSTGRES_PASSWORD=<your-generated-postgres-password>

# Required - set your domain (or use localhost for testing)
CORS_ORIGINS=http://localhost,http://localhost:80

# Recommended - change admin password
ADMIN_PASSWORD=your-secure-admin-password
```

### 5. Build and Start

```bash
docker-compose up -d
```

This will:
- Build backend and frontend Docker images (~5-10 minutes on first run)
- Start PostgreSQL database
- Start FastAPI backend
- Start Nginx frontend
- Create all necessary volumes

### 6. Check Status

```bash
docker-compose ps
```

You should see:
```
NAME                   STATUS              PORTS
baluhost-backend       Up (healthy)        -
baluhost-frontend      Up (healthy)        0.0.0.0:80->80/tcp
baluhost-postgres      Up (healthy)        -
```

### 7. Access BaluHost

Open your browser and navigate to:
- **Web UI**: http://localhost
- **API Docs**: http://localhost/api/docs

Default login:
- **Username**: `admin` (or value from ADMIN_USERNAME)
- **Password**: `changeme` (or value from ADMIN_PASSWORD)

**IMPORTANT**: Change the admin password immediately after first login!

## Common Commands

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart backend
```

### Stop Services

```bash
docker-compose stop
```

### Start Services

```bash
docker-compose start
```

### Full Shutdown and Cleanup

```bash
# Stop and remove containers (keeps volumes)
docker-compose down

# Stop, remove containers AND delete volumes (WARNING: destroys all data!)
docker-compose down -v
```

### Rebuild After Code Changes

```bash
# Rebuild all images
docker-compose build

# Rebuild and restart
docker-compose up -d --build
```

## Optional: Database Management (pgAdmin)

Start pgAdmin for database management:

```bash
docker-compose --profile tools up -d
```

Access pgAdmin:
- **URL**: http://localhost:5050
- **Email**: admin@baluhost.local (or value from PGADMIN_EMAIL)
- **Password**: admin (or value from PGADMIN_PASSWORD)

To connect to PostgreSQL in pgAdmin:
- **Host**: postgres
- **Port**: 5432
- **Database**: baluhost
- **Username**: baluhost
- **Password**: (your POSTGRES_PASSWORD from .env)

## Backup and Restore

### Backup Database

```bash
# Create backup directory
mkdir -p ./backups

# Backup PostgreSQL database
docker-compose exec postgres pg_dump -U baluhost baluhost > ./backups/baluhost_$(date +%Y%m%d_%H%M%S).sql
```

### Backup User Data

```bash
# Backup storage volume
docker run --rm -v baluhost_storage_data:/data -v $(pwd)/backups:/backup alpine tar czf /backup/storage_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
```

### Restore Database

```bash
# Restore from backup
cat ./backups/baluhost_20260113_120000.sql | docker-compose exec -T postgres psql -U baluhost baluhost
```

## Troubleshooting

### Service Not Starting

Check logs for errors:
```bash
docker-compose logs backend
```

### Port Already in Use

If port 80 is already in use, change FRONTEND_PORT in `.env`:
```bash
FRONTEND_PORT=8080
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

### Database Connection Issues

Ensure PostgreSQL is healthy:
```bash
docker-compose ps postgres
```

If unhealthy, check PostgreSQL logs:
```bash
docker-compose logs postgres
```

### Permission Issues

If you see permission errors with volumes:
```bash
# Fix volume permissions
docker-compose down
docker volume rm baluhost_storage_data baluhost_backup_data
docker-compose up -d
```

### Reset Everything

**WARNING**: This will delete all data!

```bash
docker-compose down -v
rm -rf ./backups/*.sql ./backups/*.tar.gz
docker-compose up -d
```

## Production Deployment

For production deployments:

1. **Use HTTPS**: Set up a reverse proxy (Nginx/Traefik) with Let's Encrypt SSL
2. **Change Ports**: Don't expose services directly on port 80/443
3. **Secure Secrets**: Use Docker secrets or environment variable injection
4. **Resource Limits**: Add resource limits to docker-compose.yml
5. **Monitoring**: Set up Prometheus + Grafana (see PRODUCTION_READINESS.md)
6. **Backups**: Automate daily backups with cron
7. **Updates**: Establish update procedures with zero downtime

See `docs/DEPLOYMENT.md` (coming soon) for comprehensive production deployment guide.

## Architecture

```
┌─────────────────────────────────┐
│  Browser (localhost:80)         │
└────────────┬────────────────────┘
             │
     ┌───────▼────────────┐
     │   Frontend (Nginx)  │
     │   - Serves React UI  │
     │   - Proxies /api/*   │
     └────────┬────────────┘
              │
      ┌───────▼───────────┐
      │  Backend (FastAPI) │
      │  - REST API        │
      │  - Business Logic  │
      └────────┬───────────┘
               │
       ┌───────▼─────────┐
       │  PostgreSQL DB   │
       │  - User data     │
       │  - Metadata      │
       └──────────────────┘
```

## Next Steps

- Read `PRODUCTION_READINESS.md` for production deployment checklist
- Configure VPN for remote access (see backend config)
- Set up mobile apps (Android/iOS)
- Enable Firebase push notifications
- Configure backup automation
- Set up monitoring and alerting

## Support

- Issues: https://github.com/yourrepo/baluhost/issues
- Documentation: See `docs/` directory
- Security: See `SECURITY.md`

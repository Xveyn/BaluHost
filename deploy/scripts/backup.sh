#!/bin/bash
# Manual backup script for BaluHost production deployments
# Triggers a backup via the BaluHost BackupService (Python).
#
# Default: native execution (systemd deployment).
# Use --docker for legacy Docker-based execution.

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default values
BACKUP_TYPE="full"
INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
CONTAINER_NAME="baluhost-backend"
USE_DOCKER=false

# Display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -t, --type TYPE      Backup type: full|incremental|database_only|files_only (default: full)"
    echo "  -d, --docker         Execute via Docker container (legacy)"
    echo "  -c, --container NAME Docker container name (default: baluhost-backend)"
    echo "  -h, --help           Display this help message"
    echo ""
    echo "Examples:"
    echo "  $0                            # Full backup (native)"
    echo "  $0 --type database_only       # Database-only backup"
    echo "  $0 --docker                   # Legacy Docker execution"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        -d|--docker)
            USE_DOCKER=true
            shift
            ;;
        -c|--container)
            CONTAINER_NAME="$2"
            USE_DOCKER=true
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Validate backup type
case $BACKUP_TYPE in
    full|incremental|database_only|files_only)
        ;;
    *)
        echo -e "${RED}Error: Invalid backup type '$BACKUP_TYPE'${NC}"
        echo "Valid types: full, incremental, database_only, files_only"
        exit 1
        ;;
esac

echo -e "${GREEN}BaluHost Manual Backup Script${NC}"
echo "Backup type: $BACKUP_TYPE"
echo "Mode: $([ "$USE_DOCKER" = true ] && echo 'Docker' || echo 'Native')"
echo ""

# Python script to execute backup
PYTHON_SCRIPT="
import sys
from app.core.database import SessionLocal
from app.services.backup import BackupService
from app.schemas.backup import BackupCreate

print('[Backup] Initializing backup service...')

db = SessionLocal()
try:
    service = BackupService(db)

    backup_type = '${BACKUP_TYPE}'
    includes_database = backup_type in ['full', 'database_only', 'incremental']
    includes_files = backup_type in ['full', 'files_only', 'incremental']

    backup_data = BackupCreate(
        backup_type=backup_type,
        includes_database=includes_database,
        includes_files=includes_files,
        includes_config=True
    )

    print(f'[Backup] Creating {backup_type} backup...')
    print(f'[Backup] - Database: {includes_database}')
    print(f'[Backup] - Files: {includes_files}')
    print(f'[Backup] - Config: True')
    print('')

    backup = service.create_backup(
        backup_data=backup_data,
        creator_id=1,
        creator_username='backup-script'
    )

    print('')
    print('[Backup] Backup created successfully!')
    print(f'[Backup] ID: {backup.id}')
    print(f'[Backup] Filename: {backup.filename}')
    print(f'[Backup] Size: {backup.size_bytes / (1024*1024):.2f} MB')
    print(f'[Backup] Path: {backup.filepath}')
    print('')
    sys.exit(0)

except Exception as e:
    print(f'[Backup] Error: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()
"

# Execute backup
if [ "$USE_DOCKER" = true ]; then
    # Legacy Docker execution
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${RED}Error: Container '${CONTAINER_NAME}' is not running${NC}"
        echo "Available containers:"
        docker ps --format 'table {{.Names}}\t{{.Status}}'
        exit 1
    fi

    echo -e "${YELLOW}Executing backup in Docker container...${NC}"
    echo ""
    docker exec -i "$CONTAINER_NAME" python -c "$PYTHON_SCRIPT"
else
    # Native execution (systemd deployment)
    BACKEND_DIR="$INSTALL_DIR/backend"
    VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"

    if [[ ! -f "$VENV_PYTHON" ]]; then
        echo -e "${RED}Error: Python venv not found at $VENV_PYTHON${NC}"
        echo "Is INSTALL_DIR correct? (current: $INSTALL_DIR)"
        exit 1
    fi

    if [[ ! -d "$BACKEND_DIR/app" ]]; then
        echo -e "${RED}Error: Backend app not found at $BACKEND_DIR/app${NC}"
        exit 1
    fi

    # Load environment
    if [[ -f "$INSTALL_DIR/.env.production" ]]; then
        set -a
        source "$INSTALL_DIR/.env.production"
        set +a
    fi

    echo -e "${YELLOW}Executing backup (native)...${NC}"
    echo ""
    cd "$BACKEND_DIR"
    "$VENV_PYTHON" -c "$PYTHON_SCRIPT"
fi

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Backup completed successfully!${NC}"
else
    echo -e "${RED}Backup failed!${NC}"
fi
exit $EXIT_CODE

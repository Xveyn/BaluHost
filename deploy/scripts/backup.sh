#!/bin/bash
# Manual backup script for BaluHost production deployments
# This script triggers a backup via the Docker container or direct Python execution

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
BACKUP_TYPE="full"
CONTAINER_NAME="baluhost-backend"
USE_DOCKER=true

# Display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -t, --type TYPE      Backup type: full|incremental|database_only|files_only (default: full)"
    echo "  -c, --container NAME Docker container name (default: baluhost-backend)"
    echo "  --no-docker          Execute directly (not via Docker)"
    echo "  -h, --help           Display this help message"
    echo ""
    echo "Examples:"
    echo "  $0                            # Full backup via Docker"
    echo "  $0 --type database_only       # Database-only backup"
    echo "  $0 --no-docker                # Direct execution (no Docker)"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        -c|--container)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --no-docker)
            USE_DOCKER=false
            shift
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
echo "Container: $CONTAINER_NAME"
echo "Use Docker: $USE_DOCKER"
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

    # Determine backup parameters
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
    print('[Backup] ✅ Backup created successfully!')
    print(f'[Backup] ID: {backup.id}')
    print(f'[Backup] Filename: {backup.filename}')
    print(f'[Backup] Size: {backup.size_bytes / (1024*1024):.2f} MB')
    print(f'[Backup] Path: {backup.filepath}')
    print('')
    sys.exit(0)

except Exception as e:
    print(f'[Backup] ❌ Error: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()
"

# Execute backup
if [ "$USE_DOCKER" = true ]; then
    # Check if container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${RED}Error: Container '${CONTAINER_NAME}' is not running${NC}"
        echo "Available containers:"
        docker ps --format 'table {{.Names}}\t{{.Status}}'
        exit 1
    fi

    echo -e "${YELLOW}Executing backup in Docker container...${NC}"
    echo ""

    # Execute Python script in container
    docker exec -i "$CONTAINER_NAME" python -c "$PYTHON_SCRIPT"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Backup completed successfully!${NC}"
        exit 0
    else
        echo -e "${RED}Backup failed!${NC}"
        exit 1
    fi

else
    # Direct execution (assumes current directory is backend/)
    echo -e "${YELLOW}Executing backup directly (no Docker)...${NC}"
    echo ""

    if [ ! -d "app" ]; then
        echo -e "${RED}Error: Not in backend directory${NC}"
        echo "Please run this script from the backend/ directory or use --container option"
        exit 1
    fi

    python -c "$PYTHON_SCRIPT"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Backup completed successfully!${NC}"
        exit 0
    else
        echo -e "${RED}Backup failed!${NC}"
        exit 1
    fi
fi

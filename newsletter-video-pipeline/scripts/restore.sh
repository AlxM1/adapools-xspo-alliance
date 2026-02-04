#!/bin/bash
# ============================================================
# Newsletter Video Pipeline - Restore Script
# ============================================================
# Restore from backup archive
# ============================================================

set -e

# Check arguments
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_archive.tar.gz>"
    echo ""
    echo "Example:"
    echo "  $0 /opt/nvp/backups/nvp_backup_20240101_120000.tar.gz"
    exit 1
fi

BACKUP_ARCHIVE="$1"

if [ ! -f "${BACKUP_ARCHIVE}" ]; then
    echo "Error: Backup file not found: ${BACKUP_ARCHIVE}"
    exit 1
fi

# Configuration
DB_HOST="${DATABASE_HOST:-localhost}"
DB_PORT="${DATABASE_PORT:-5432}"
DB_NAME="${DATABASE_NAME:-newsletter_video_pipeline}"
DB_USER="${DATABASE_USER:-nvp}"
DB_PASSWORD="${DATABASE_PASSWORD:-nvp_password}"

DATA_DIR="${DATA_DIR:-/opt/nvp/data}"
CONFIG_DIR="${CONFIG_DIR:-/opt/nvp/config}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}Newsletter Video Pipeline - Restore${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo "Backup Archive: ${BACKUP_ARCHIVE}"
echo ""

# Warning
echo -e "${RED}WARNING: This will overwrite existing data!${NC}"
read -p "Are you sure you want to continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 1
fi

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

# ============================================================
# Extract Archive
# ============================================================
echo -e "${GREEN}[1/4] Extracting backup archive...${NC}"

tar -xzf "${BACKUP_ARCHIVE}" -C "${TEMP_DIR}"
BACKUP_DIR="${TEMP_DIR}/$(ls ${TEMP_DIR})"

echo "Extracted to: ${BACKUP_DIR}"

# ============================================================
# Restore Database
# ============================================================
echo -e "${GREEN}[2/4] Restoring database...${NC}"

if [ -f "${BACKUP_DIR}/database.dump" ]; then
    export PGPASSWORD="${DB_PASSWORD}"

    # Drop existing connections
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" 2>/dev/null || true

    # Drop and recreate database
    dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" --if-exists "${DB_NAME}" 2>/dev/null || true
    createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}"

    # Restore
    pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --no-owner --no-privileges "${BACKUP_DIR}/database.dump"

    echo "Database restored successfully"
else
    echo -e "${YELLOW}Database dump not found, skipping...${NC}"
fi

# ============================================================
# Restore Configuration
# ============================================================
echo -e "${GREEN}[3/4] Restoring configuration...${NC}"

if [ -f "${BACKUP_DIR}/config.tar.gz" ]; then
    mkdir -p "$(dirname ${CONFIG_DIR})"
    tar -xzf "${BACKUP_DIR}/config.tar.gz" -C "$(dirname ${CONFIG_DIR})"
    echo "Configuration restored successfully"
else
    echo -e "${YELLOW}Configuration backup not found, skipping...${NC}"
fi

# ============================================================
# Restore Media Files
# ============================================================
echo -e "${GREEN}[4/4] Restoring media files...${NC}"

MEDIA_DIRS=("voices" "avatars" "videos" "thumbnails")

for dir_name in "${MEDIA_DIRS[@]}"; do
    if [ -f "${BACKUP_DIR}/${dir_name}.tar.gz" ]; then
        mkdir -p "${DATA_DIR}"
        tar -xzf "${BACKUP_DIR}/${dir_name}.tar.gz" -C "${DATA_DIR}"
        echo "Restored: ${dir_name}"
    fi
done

# ============================================================
# Summary
# ============================================================
echo ""
echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}Restore Complete!${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo "Please restart the services to apply changes:"
echo "  docker-compose restart"

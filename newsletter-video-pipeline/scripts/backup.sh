#!/bin/bash
# ============================================================
# Newsletter Video Pipeline - Backup Script
# ============================================================
# Automated backup for database, configurations, and media files
# ============================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/nvp/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="nvp_backup_${TIMESTAMP}"

# Database configuration
DB_HOST="${DATABASE_HOST:-localhost}"
DB_PORT="${DATABASE_PORT:-5432}"
DB_NAME="${DATABASE_NAME:-newsletter_video_pipeline}"
DB_USER="${DATABASE_USER:-nvp}"
DB_PASSWORD="${DATABASE_PASSWORD:-nvp_password}"

# Directories to backup
DATA_DIR="${DATA_DIR:-/opt/nvp/data}"
CONFIG_DIR="${CONFIG_DIR:-/opt/nvp/config}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}Newsletter Video Pipeline - Backup${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo "Backup Name: ${BACKUP_NAME}"
echo "Backup Directory: ${BACKUP_DIR}"
echo ""

# Create backup directory
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"
CURRENT_BACKUP="${BACKUP_DIR}/${BACKUP_NAME}"

# ============================================================
# 1. Database Backup
# ============================================================
echo -e "${GREEN}[1/4] Backing up database...${NC}"

export PGPASSWORD="${DB_PASSWORD}"
pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --format=custom --compress=9 \
    -f "${CURRENT_BACKUP}/database.dump"

echo "Database backup complete: database.dump"

# ============================================================
# 2. Configuration Backup
# ============================================================
echo -e "${GREEN}[2/4] Backing up configuration files...${NC}"

if [ -d "${CONFIG_DIR}" ]; then
    tar -czf "${CURRENT_BACKUP}/config.tar.gz" -C "$(dirname ${CONFIG_DIR})" "$(basename ${CONFIG_DIR})"
    echo "Configuration backup complete: config.tar.gz"
else
    echo -e "${YELLOW}Configuration directory not found, skipping...${NC}"
fi

# ============================================================
# 3. Media Files Backup
# ============================================================
echo -e "${GREEN}[3/4] Backing up media files...${NC}"

MEDIA_DIRS=(
    "${DATA_DIR}/voices"
    "${DATA_DIR}/avatars"
    "${DATA_DIR}/videos"
    "${DATA_DIR}/thumbnails"
)

for dir in "${MEDIA_DIRS[@]}"; do
    if [ -d "${dir}" ]; then
        dir_name=$(basename "${dir}")
        tar -czf "${CURRENT_BACKUP}/${dir_name}.tar.gz" -C "$(dirname ${dir})" "${dir_name}"
        echo "Backed up: ${dir_name}.tar.gz"
    fi
done

# ============================================================
# 4. Create Final Archive
# ============================================================
echo -e "${GREEN}[4/4] Creating final archive...${NC}"

cd "${BACKUP_DIR}"
tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}"
rm -rf "${CURRENT_BACKUP}"

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
echo "Final backup: ${BACKUP_NAME}.tar.gz (${BACKUP_SIZE})"

# ============================================================
# Cleanup Old Backups
# ============================================================
echo ""
echo -e "${GREEN}Cleaning up old backups (older than ${RETENTION_DAYS} days)...${NC}"

find "${BACKUP_DIR}" -name "nvp_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
REMAINING=$(ls -1 "${BACKUP_DIR}"/nvp_backup_*.tar.gz 2>/dev/null | wc -l)
echo "Remaining backups: ${REMAINING}"

# ============================================================
# Summary
# ============================================================
echo ""
echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}Backup Complete!${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo "Backup file: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
echo "Size: ${BACKUP_SIZE}"
echo ""
echo "To restore this backup, run:"
echo "  ./scripts/restore.sh ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

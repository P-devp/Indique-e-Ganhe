#!/usr/bin/env bash
# Database backup script for Retro Afiliados
# Usage: ./scripts/backup_db.sh [backup_dir]
# Default: backups/ in project root

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${1:-$PROJECT_DIR/backups}"
DB_PATH="$PROJECT_DIR/backend/retro.db"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "Database not found: $DB_PATH"
    exit 1
fi

# Use .backup command via sqlite3 for safe online backup
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/retro_$TIMESTAMP.db'"

# Keep only last 30 backups
find "$BACKUP_DIR" -name 'retro_*.db' -mtime +30 -delete

echo "Backup saved: $BACKUP_DIR/retro_$TIMESTAMP.db"
echo "Total backups: $(find "$BACKUP_DIR" -name 'retro_*.db' | wc -l)"

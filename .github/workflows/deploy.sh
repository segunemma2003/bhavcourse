#!/bin/bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/var/backups/bhavani"

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

# Backup .env file with restricted permissions
cp /var/www/bhavani/.env $BACKUP_DIR/env_$TIMESTAMP.backup
chmod 600 $BACKUP_DIR/env_$TIMESTAMP.backup

# Database backup
mysqldump -u$DB_USER -p$DB_PASSWORD $DB_NAME | gzip > $BACKUP_DIR/db_$TIMESTAMP.sql.gz

# Media files backup
tar -zcf $BACKUP_DIR/media_$TIMESTAMP.tar.gz -C /var/www/bhavani media

# Delete backups older than 7 days
find $BACKUP_DIR -type f -name "*.backup" -mtime +7 -delete
find $BACKUP_DIR -type f -name "*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -type f -name "*.tar.gz" -mtime +7 -delete
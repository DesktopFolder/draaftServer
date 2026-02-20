#!/bin/bash
mkdir -p .backup

echo "Backing up draaft to: .backup"

echo "Backing up: draaft.db"
sqlite3 db/draaft.db ".backup 'backup.db'"
mv backup.db .backup

tar -czf backup.tar.gz .backup
echo "Finished. To export, run: scp $(whoami)@$(hostname):$(pwd)/backup.tar.gz ."

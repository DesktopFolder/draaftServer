#!/bin/bash
mkdir -p .backup

echo "Backing up draaft to: .backup"

echo "Backing up: draaft.db"
sqlite3 db/draaft.db ".backup 'backup.db'"
mv backup.db .backup

echo "Backing up: dotfiles"
cp .visitors.json .backup
cp .bracket-log.json .backup

echo "Backing up: seeds"
cp $HOME/data/draaft/generated_overworld_seeds.txt .backup
cp $HOME/data/draaft/overworld_seeds_strongholds.txt .backup
cp $HOME/data/draaft/overworld_seeds.txt .backup

tar -czf backup.tar.gz .backup
echo "Finished. To export, run: scp $(whoami)@$(hostname):$(pwd)/backup.tar.gz ."

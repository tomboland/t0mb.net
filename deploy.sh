#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.ghcup/bin:/usr/local/bin:/usr/bin:/bin"

REPO_DIR="$HOME/t0mb.net"
PUBLIC_DIR="/var/www/t0mb.net/public"

cd "$REPO_DIR"

OLD_COMMIT=$(git rev-parse HEAD)
git pull origin main --rebase
NEW_COMMIT=$(git rev-parse HEAD)

if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
    echo "Site is already up to date ($NEW_COMMIT). Nothing to do."
    exit 0
fi

echo "New changes detected ($OLD_COMMIT -> $NEW_COMMIT). Starting build..."

cabal build exe:site
cabal exec site -- build

rsync -a --delete "$REPO_DIR/_site/" "$PUBLIC_DIR/"

echo "Deploy complete."

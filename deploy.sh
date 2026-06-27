#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.ghcup/bin:/usr/local/bin:/usr/bin:/bin"

FORCE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--force]"
            echo
            echo "  --force    Build and deploy even if git is already up to date"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--force]" >&2
            exit 2
            ;;
    esac
done

REPO_DIR="$HOME/t0mb.net"
PUBLIC_DIR="/var/www/t0mb.net/public"

cd "$REPO_DIR"

OLD_COMMIT=$(git rev-parse HEAD)
git pull origin main --rebase
NEW_COMMIT=$(git rev-parse HEAD)

if [ "$OLD_COMMIT" = "$NEW_COMMIT" ] && [ "$FORCE" = false ]; then
    echo "Site is already up to date ($NEW_COMMIT). Nothing to do."
    exit 0
fi

if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
    echo "No new git changes, but --force was supplied. Starting build..."
else
    echo "New changes detected ($OLD_COMMIT -> $NEW_COMMIT). Starting build..."
fi

cabal build exe:site
cabal exec site -- build

rsync -a --delete "$REPO_DIR/_site/" "$PUBLIC_DIR/"

echo "Deploy complete."

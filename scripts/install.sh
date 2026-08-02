#!/usr/bin/env bash
# One-shot installer for a fresh Ubuntu VDS: installs Docker if needed,
# clones the repo, seeds .env/config.yaml, and prints the remaining
# (unavoidably interactive) steps: login and go-live.
#
# Usage on the server:
#   curl -fsSL https://raw.githubusercontent.com/Oxyg1/Odbcjehbxi/claude/new-session-m867oe/scripts/install.sh | bash
# or, after cloning manually:
#   bash scripts/install.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Oxyg1/Odbcjehbxi.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/tgmarket}"
NEED_RELOGIN=0

echo "== tgmarket installer =="

if ! command -v docker >/dev/null 2>&1; then
  echo "-> Docker not found, installing (docker.io + compose plugin)..."
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-plugin git
  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
  NEED_RELOGIN=1
else
  echo "-> Docker already present."
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "-> Cloning into $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  echo "-> $INSTALL_DIR already exists, skipping clone."
fi
cd "$INSTALL_DIR"

[ -f .env ] || cp .env.example .env
[ -f config.yaml ] || cp config.example.yaml config.yaml

if ! grep -qE '^TG_API_ID=[0-9]+' .env; then
  echo
  echo "Enter your credentials from https://my.telegram.org (API development tools):"
  read -rp "TG_API_ID: " API_ID
  read -rp "TG_API_HASH: " API_HASH
  sed -i "s/^TG_API_ID=.*/TG_API_ID=${API_ID}/" .env
  sed -i "s/^TG_API_HASH=.*/TG_API_HASH=${API_HASH}/" .env
  echo "-> Saved to $INSTALL_DIR/.env"
else
  echo "-> TG_API_ID already set in .env, leaving it as-is."
fi

echo
echo "===================================================================="
echo " Setup done. Review filters before going further:"
echo "   nano $INSTALL_DIR/config.yaml"
echo
if [ "$NEED_RELOGIN" = "1" ]; then
  echo " Docker just added you to the 'docker' group - log out of this SSH"
  echo " session and reconnect once before continuing, otherwise 'docker'"
  echo " commands below will need sudo."
  echo
fi
echo " Remaining steps (run from $INSTALL_DIR):"
echo "   cd $INSTALL_DIR"
echo "   docker compose --profile tools run --rm login    # one-time; needs the Telegram code from your phone"
echo "   docker compose run --rm tgmarket catalog --all    # sanity-check your filters"
echo "   docker compose run --rm tgmarket watch --once     # one dry monitoring cycle"
echo "   docker compose up -d                              # start the loop (dry-run by default)"
echo "   docker compose logs -f"
echo "===================================================================="

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

if ! command -v git >/dev/null 2>&1; then
  echo "-> git not found, installing..."
  sudo apt-get update -y
  sudo apt-get install -y git
fi

# Ubuntu's own archives only carry the old `docker.io` engine and no
# docker-compose-plugin at all, so `apt-get install docker.io
# docker-compose-plugin` fails atomically (apt refuses to install anything
# from the command if any one package name can't be resolved). Docker's own
# convenience script sets up their apt repo and installs a matched
# engine + compose + buildx in one go, which is what actually works here.
if ! command -v docker >/dev/null 2>&1; then
  echo "-> Docker not found, installing via get.docker.com..."
  curl -fsSL https://get.docker.com | sudo sh
  sudo systemctl enable --now docker
  if [ -n "${SUDO_USER:-}" ]; then
    sudo usermod -aG docker "$SUDO_USER"
    NEED_RELOGIN=1
  elif [ "$(id -u)" != "0" ]; then
    sudo usermod -aG docker "$USER"
    NEED_RELOGIN=1
  fi
  # root itself doesn't need the docker group and needs no re-login.
else
  echo "-> Docker already present."
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "-> docker compose plugin missing, installing..."
  sudo apt-get update -y
  if ! sudo apt-get install -y docker-compose-plugin; then
    echo "-> not available via apt, fetching the plugin binary directly"
    plugin_dir="/usr/local/lib/docker/cli-plugins"
    sudo mkdir -p "$plugin_dir"
    arch="$(uname -m)"
    sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${arch}" \
      -o "$plugin_dir/docker-compose"
    sudo chmod +x "$plugin_dir/docker-compose"
  fi
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

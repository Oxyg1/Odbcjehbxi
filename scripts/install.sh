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
# The project currently lives on this feature branch, not on the repo's
# default branch (which is still just the original empty template). Update
# this once the branch is merged.
REPO_BRANCH="${REPO_BRANCH:-claude/new-session-m867oe}"
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

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "-> $INSTALL_DIR already exists, syncing to $REPO_BRANCH"
  git -C "$INSTALL_DIR" fetch origin "$REPO_BRANCH"
  git -C "$INSTALL_DIR" checkout "$REPO_BRANCH"
  git -C "$INSTALL_DIR" reset --hard "origin/$REPO_BRANCH"
else
  echo "-> Cloning $REPO_BRANCH into $INSTALL_DIR"
  git clone --branch "$REPO_BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

if [ ! -f .env.example ]; then
  echo "ERROR: .env.example missing after clone - wrong branch or a broken checkout." >&2
  echo "Try: rm -rf '$INSTALL_DIR' and re-run this script." >&2
  exit 1
fi

[ -f .env ] || cp .env.example .env

if [ -f config.yaml ] && ! grep -q '^telegram:' config.yaml; then
  echo "-> existing config.yaml doesn't look like ours (no 'telegram:' section)."
  echo "   Backing it up to config.yaml.bak and writing a fresh one from config.example.yaml."
  mv config.yaml config.yaml.bak
fi
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

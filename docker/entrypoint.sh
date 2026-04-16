#!/bin/bash
# Docker entrypoint: bootstrap config files into the mounted volume, then run bullwhip.
set -e

BULLWHIP_HOME="/opt/data"
INSTALL_DIR="/opt/bullwhip"

# --- Privilege dropping via gosu ---
# When started as root (the default), optionally remap the bullwhip user/group
# to match host-side ownership, fix volume permissions, then re-exec as bullwhip.
if [ "$(id -u)" = "0" ]; then
    if [ -n "$BULLWHIP_UID" ] && [ "$BULLWHIP_UID" != "$(id -u bullwhip)" ]; then
        echo "Changing bullwhip UID to $BULLWHIP_UID"
        usermod -u "$BULLWHIP_UID" bullwhip
    fi

    if [ -n "$BULLWHIP_GID" ] && [ "$BULLWHIP_GID" != "$(id -g bullwhip)" ]; then
        echo "Changing bullwhip GID to $BULLWHIP_GID"
        groupmod -g "$BULLWHIP_GID" bullwhip
    fi

    actual_hermes_uid=$(id -u bullwhip)
    if [ "$(stat -c %u "$BULLWHIP_HOME" 2>/dev/null)" != "$actual_hermes_uid" ]; then
        echo "$BULLWHIP_HOME is not owned by $actual_hermes_uid, fixing"
        chown -R bullwhip:bullwhip "$BULLWHIP_HOME"
    fi

    echo "Dropping root privileges"
    exec gosu bullwhip "$0" "$@"
fi

# --- Running as bullwhip from here ---
source "${INSTALL_DIR}/.venv/bin/activate"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
# The "home/" subdirectory is a per-profile HOME for subprocesses (git,
# ssh, gh, npm …).  Without it those tools write to /root which is
# ephemeral and shared across profiles.  See issue #4426.
mkdir -p "$BULLWHIP_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# .env
if [ ! -f "$BULLWHIP_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$BULLWHIP_HOME/.env"
fi

# config.yaml
if [ ! -f "$BULLWHIP_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$BULLWHIP_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$BULLWHIP_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$BULLWHIP_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

exec bullwhip "$@"

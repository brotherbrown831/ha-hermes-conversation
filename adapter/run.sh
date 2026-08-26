#!/usr/bin/env bash
# VV HA Adapter launcher for the vexavoice Hermes profile.
# Loads the HA long-lived token from a 0600 credentials file (outside Git/config),
# then runs the FastMCP stdio server with the Hermes venv python.
set -euo pipefail

TOKEN_FILE="/home/nolan/.hermes/profiles/vexavoice/credentials/ha-token"
if [[ -r "$TOKEN_FILE" ]]; then
  export HA_TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
fi
export HA_BASE_URL="${HA_BASE_URL:-http://10.0.10.117:8123}"

exec /home/nolan/.hermes/hermes-agent/venv/bin/python \
  /home/nolan/.hermes/scripts/vv-ha-adapter/server.py
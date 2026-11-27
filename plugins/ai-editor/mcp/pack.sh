#!/bin/sh
# Packs this folder into cooked.mcpb, the one-click Claude desktop extension.
set -e
cd "$(dirname "$0")"
python3 server.py demo
npx -y @anthropic-ai/mcpb pack . cooked.mcpb

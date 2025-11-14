#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-dev python3-venv git       alsa-utils sox libasound2-dev ffmpeg

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment and install dependencies
source venv/bin/activate
pip install -r requirements.txt

echo
echo "Nu behöver du:"
echo "  1) Aktivera/installera WM8960-overlay för ditt 2-Mic HAT (enligt aktuell guide)"
echo "  2) Reboota Pi när overlay är aktiverad"
echo "  3) Testa ljud med arecord/aplay och sätt rätt audio.device i config.yaml"
echo "  4) Sätt önskat ljudformat i config.yaml under audio.reply_format (wav, mp3, flac, etc.)"

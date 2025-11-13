# pi-voice-agent-webhook

Enkel röstagent för Raspberry Pi Zero 2 WH + 2-Mic HAT.

- Tryck på knappen på HAT:en (GPIO17)
- Pi spelar in en WAV-fil (max några sekunder)
- Skickar WAV till en n8n-webhook
- Tar emot ljudfil i valfritt format (WAV, MP3, FLAC, etc.) som svar och spelar upp den

## Snabbstart

```bash
git clone <ditt-repo> pi-voice-agent-webhook
cd pi-voice-agent-webhook

cp config.example.yaml config.yaml

chmod +x scripts/install_deps.sh
./scripts/install_deps.sh
```

Justera `config.yaml` (webhook-URL, audio.device).

### Ljudformat

Systemet kan ta emot och spela upp ljudfiler i olika format från n8n:
- `wav` (standard)
- `mp3`
- `flac`
- `ogg`
- `m4a`

Ange önskat format i `config.yaml` under `audio.reply_format`. 

**Ingen konvertering behövs!** Systemet använder automatiskt `ffplay` (del av ffmpeg) eller `play` (del av sox) som kan spela upp alla format direkt. Som fallback används `aplay` som endast stödjer WAV, och då konverteras filer automatiskt vid behov.

#### Hur det fungerar

Systemet försöker spela upp ljud med följande prioritet:

1. **ffplay** (ffmpeg) - Stöder alla format (WAV, MP3, FLAC, OGG, M4A, etc.) ✅ Rekommenderas
2. **play** (sox) - Stöder de flesta format
3. **aplay** (alsa) - Endast WAV, konverterar automatiskt vid behov

För bästa kompatibilitet och prestanda, installera `ffmpeg` (rekommenderas):

```bash
sudo apt-get install -y ffmpeg
```

Alternativt kan `sox` användas:

```bash
sudo apt-get install -y sox libsox-fmt-all
```

Kör:

```bash
chmod +x scripts/run.sh
./scripts/run.sh
```

## systemd

```bash
sudo cp systemd/simple-voice-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable simple-voice-agent
sudo systemctl start simple-voice-agent
```

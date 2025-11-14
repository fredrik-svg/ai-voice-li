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

Installationsskriptet skapar en Python virtual environment (venv) för att undvika problem med externally-managed-environment på moderna system.

Justera `config.yaml` (webhook-URL, audio.device).

### Ljudformat

Systemet kan ta emot ljudfiler i olika format från n8n:
- `wav` (standard, ingen konvertering krävs)
- `mp3`
- `flac`
- `ogg`
- `m4a`

Ange önskat format i `config.yaml` under `audio.reply_format`. Om ett annat format än WAV används, kommer filen automatiskt att konverteras till WAV före uppspelning. Detta kräver att `ffmpeg` eller `sox` är installerat:

```bash
sudo apt-get install -y ffmpeg
# eller
sudo apt-get install -y sox libsox-fmt-all
```

Kör:

```bash
chmod +x scripts/run.sh
./scripts/run.sh
```

### Statusljud

Systemet använder ljudsignaler för att ge feedback om vad som händer:

- **Kort hög ton (800 Hz)** - Inspelning startar
- **Kort högre ton (1000 Hz)** - Skickar fil till webhook
- **Medellång lägre ton (600 Hz)** - Väntar på svar från webhook
- **Dubbel hög ton (1200 Hz)** - Framgång! Svar mottaget
- **Lång låg ton (400 Hz)** - Fel uppstod (inspelning, nätverksfel, etc.)

Statusljud kan avaktiveras i `config.yaml`:

```yaml
status_sounds:
  enabled: false
```

## systemd

```bash
sudo cp systemd/simple-voice-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable simple-voice-agent
sudo systemctl start simple-voice-agent
```

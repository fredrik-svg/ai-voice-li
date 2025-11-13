# pi-voice-agent-webhook

Enkel röstagent för Raspberry Pi Zero 2 WH + 2-Mic HAT.

- Tryck på knappen på HAT:en (GPIO17)
- Pi spelar in en WAV-fil (max några sekunder)
- Skickar WAV till en n8n-webhook
- Tar emot en WAV som svar och spelar upp den

## Snabbstart

```bash
git clone <ditt-repo> pi-voice-agent-webhook
cd pi-voice-agent-webhook

cp config.example.yaml config.yaml

chmod +x scripts/install_deps.sh
./scripts/install_deps.sh
```

Justera `config.yaml` (webhook-URL, audio.device).

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

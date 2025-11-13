#!/usr/bin/env python3
import os
import sys
import time
import yaml
import signal
import threading
import subprocess
import requests

from src.gpio_button import Button


def load_config(path: str):
    with open(path, "r") as f:
        return yaml.safe_load(f)


class SimpleVoiceAgent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.running = True
        self._lock = threading.Lock()

    def record_once(self):
        audio = self.cfg["audio"]
        dev = audio["device"]
        rate = int(audio["rate"])
        ch = int(audio["channels"])
        fmt = audio["format"]
        dur = int(audio["duration_max"])
        out_path = audio["tmp_record_path"]

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        cmd = [
            "arecord",
            "-D", dev,
            "-c", str(ch),
            "-f", fmt,
            "-r", str(rate),
            "-d", str(dur),
            "-t", "wav",
            out_path,
        ]

        print(f"[audio] Spelar in (max {dur}s) på {dev} ...")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print("[audio] arecord misslyckades:", e)
            return None

        if not os.path.exists(out_path):
            print("[audio] Ingen fil skapad.")
            return None

        print(f"[audio] Inspelning klar: {out_path}")
        return out_path

    def send_to_webhook(self, wav_path: str):
        url = self.cfg["webhook"]["url"]
        timeout = int(self.cfg["webhook"].get("timeout", 90))
        dev_info = self.cfg["device"]

        print(f"[http] Skickar {wav_path} till webhook {url}")
        with open(wav_path, "rb") as f:
            files = {"audio": ("audio.wav", f, "audio/wav")}
            data = {
                "deviceId": dev_info["id"],
                "tenant": dev_info["tenant"],
                "user": dev_info["user"],
            }
            try:
                resp = requests.post(url, data=data, files=files, timeout=timeout)
            except Exception as e:
                print("[http] Fel vid POST:", e)
                return None

        print("[http] Svar status:", resp.status_code)
        if resp.status_code != 200:
            print("[http] Oväntad statuskod, ingen uppspelning.")
            return None

        ctype = resp.headers.get("Content-Type", "")
        if not ctype.startswith("audio/"):
            print("[http] Content-Type är inte audio/* – fick troligen något annat:", ctype)
            return None

        out_path = self.cfg["audio"]["tmp_reply_path"]
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"[http] Sparade svarsljud till {out_path}")
        return out_path

    def play_wav(self, wav_path: str):
        audio = self.cfg["audio"]
        dev = audio["device"]
        cmd = ["aplay", "-q", "-D", dev, wav_path]
        print("[audio] Spelar upp svar...")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print("[audio] aplay misslyckades:", e)

    def handle_button(self):
        if not self._lock.acquire(blocking=False):
            print("[agent] Upptagen – hoppar över knapptryck.")
            return

        def _run():
            try:
                wav_in = self.record_once()
                if not wav_in:
                    return
                wav_out = self.send_to_webhook(wav_in)
                if wav_out:
                    self.play_wav(wav_out)
            finally:
                self._lock.release()

        threading.Thread(target=_run, daemon=True).start()

    def start(self):
        gpio_cfg = self.cfg["gpio"]
        btn = Button(pin=gpio_cfg["button_pin"], pull_up=gpio_cfg.get("pull_up", True))
        btn.on_pressed(self.handle_button)
        btn.start()
        print("[agent] Klar. Tryck på knappen för att spela in. Ctrl+C för att avsluta.")
        while self.running:
            time.sleep(0.5)

    def stop(self):
        self.running = False


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(cfg_path)
    agent = SimpleVoiceAgent(cfg)

    def handle_sig(sig, frame):
        print("[agent] Stänger ned...")
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    agent.start()


if __name__ == "__main__":
    main()

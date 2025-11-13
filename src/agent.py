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

        # Hämta förväntat format från config (standard: wav)
        reply_format = self.cfg["audio"].get("reply_format", "wav").lower()
        
        # Spara mottagen fil med rätt filformat
        base_path = self.cfg["audio"]["tmp_reply_path"]
        # Ta bort befintlig filändelse om den finns
        if base_path.endswith('.wav'):
            base_path = base_path[:-4]
        
        received_path = f"{base_path}.{reply_format}"
        with open(received_path, "wb") as f:
            f.write(resp.content)
        print(f"[http] Sparade svarsljud ({reply_format}) till {received_path}")
        
        # Returnera ljudfilen direkt - ingen konvertering behövs om vi använder ffplay eller play
        return received_path

    def play_audio(self, audio_path: str):
        """
        Spelar upp en ljudfil i valfritt format (wav, mp3, flac, ogg, etc.)
        Försöker med ffplay först (stöder alla format), sedan play (sox), slutligen aplay (endast wav).
        """
        audio = self.cfg["audio"]
        dev = audio["device"]
        
        print(f"[audio] Spelar upp svar från {audio_path}...")
        
        # Försök 1: ffplay (del av ffmpeg, stödjer alla format)
        # Använd -nodisp för att inte visa video-fönster, -autoexit för att stänga när klar
        # -loglevel quiet för att undvika onödig output
        cmd_ffplay = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", audio_path]
        try:
            subprocess.run(cmd_ffplay, check=True, capture_output=True)
            return
        except FileNotFoundError:
            print("[audio] ffplay saknas, försöker play (sox)...")
        except subprocess.CalledProcessError as e:
            print(f"[audio] ffplay misslyckades: {e}")
        
        # Försök 2: play (del av sox, stödjer många format)
        cmd_play = ["play", "-q", audio_path]
        try:
            subprocess.run(cmd_play, check=True, capture_output=True)
            return
        except FileNotFoundError:
            print("[audio] play saknas, försöker aplay...")
        except subprocess.CalledProcessError as e:
            print(f"[audio] play misslyckades: {e}")
        
        # Försök 3: aplay (endast för WAV-filer)
        # Om filen inte är wav, försök konvertera först
        if not audio_path.endswith('.wav'):
            print(f"[audio] aplay kräver WAV-format, konverterar {audio_path}...")
            wav_path = audio_path.rsplit('.', 1)[0] + '_converted.wav'
            if self.convert_to_wav(audio_path, wav_path):
                audio_path = wav_path
            else:
                print("[audio] Konvertering misslyckades, kan inte spela upp med aplay")
                return
        
        cmd_aplay = ["aplay", "-q", "-D", dev, audio_path]
        try:
            subprocess.run(cmd_aplay, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[audio] aplay misslyckades: {e}")
        except FileNotFoundError:
            print("[audio] Ingen ljudspelare hittades (ffplay, play eller aplay)")

    def convert_to_wav(self, input_path: str, output_path: str):
        """
        Konverterar ljudfil till WAV-format med ffmpeg eller sox.
        Returnerar True om konvertering lyckades, annars False.
        Används endast som fallback när aplay måste användas.
        """
        # Försök med ffmpeg först
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", input_path,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path
        ]
        
        print(f"[audio] Konverterar {input_path} till {output_path} med ffmpeg...")
        try:
            subprocess.run(cmd_ffmpeg, check=True, capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[audio] ffmpeg misslyckades eller saknas: {e}")
        
        # Om ffmpeg misslyckades, försök med sox
        cmd_sox = ["sox", input_path, output_path]
        print(f"[audio] Försöker konvertera med sox...")
        try:
            subprocess.run(cmd_sox, check=True, capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[audio] sox misslyckades eller saknas: {e}")
        
        return False

    def handle_button(self):
        if not self._lock.acquire(blocking=False):
            print("[agent] Upptagen – hoppar över knapptryck.")
            return

        def _run():
            try:
                wav_in = self.record_once()
                if not wav_in:
                    return
                audio_out = self.send_to_webhook(wav_in)
                if audio_out:
                    self.play_audio(audio_out)
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

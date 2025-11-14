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
        self.button = None
        self.status_sounds_enabled = cfg.get("status_sounds", {}).get("enabled", True)

    def play_status_beep(self, beep_type: str):
        """
        Spelar statusljud för att indikera vad som händer.
        beep_type kan vara: 'start', 'sending', 'processing', 'success', 'error'
        """
        if not self.status_sounds_enabled:
            return
        
        audio = self.cfg["audio"]
        dev = audio["device"]
        
        # Olika frekvenser och durationer för olika statustyper
        beep_configs = {
            'start': {'freq': 800, 'duration': 0.15},      # Kort hög ton för start
            'sending': {'freq': 1000, 'duration': 0.1},    # Kort ännu högre ton för sändning
            'processing': {'freq': 600, 'duration': 0.2},  # Medellång lägre ton för bearbetning
            'success': {'freq': 1200, 'duration': 0.1},    # Dubbel hög ton för framgång
            'error': {'freq': 400, 'duration': 0.3}        # Lång låg ton för fel
        }
        
        if beep_type not in beep_configs:
            return
            
        config = beep_configs[beep_type]
        
        # Använd speaker-test för att generera ett enkelt pip
        # -t sine = sinusvåg, -f = frekvens, -l 1 = spela en gång, -r = samplingsfrekvens
        cmd = [
            "speaker-test",
            "-t", "sine",
            "-f", str(config['freq']),
            "-l", "1",
            "-r", "48000",
            "-D", dev
        ]
        
        try:
            # Kör speaker-test och avbryt efter specificerad duration
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(config['duration'])
            proc.terminate()
            proc.wait(timeout=1)
        except Exception as e:
            # Om speaker-test misslyckas, försök med beep-kommandot
            try:
                subprocess.run(["beep", "-f", str(config['freq']), "-l", str(int(config['duration'] * 1000))], 
                             timeout=1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                # Ignorera fel - statusljud är inte kritiskt
                pass
        
        # För 'success' lägg till ett andra pip
        if beep_type == 'success':
            time.sleep(0.05)
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.1)
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                pass

    def record_once(self):
        audio = self.cfg["audio"]
        dev = audio["device"]
        rate = int(audio["rate"])
        ch = int(audio["channels"])
        fmt = audio["format"]
        dur = int(audio["duration_max"])
        out_path = audio["tmp_record_path"]

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # Spela statusljud för att indikera att inspelning startar
        self.play_status_beep('start')

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
            # Add timeout to prevent hanging if arecord doesn't respond
            # Set timeout slightly longer than recording duration to allow for completion
            timeout = dur + 5
            subprocess.run(cmd, check=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[audio] arecord timeout efter {timeout}s - avbryter inspelning")
            return None
        except subprocess.CalledProcessError as e:
            # arecord returns a non-zero exit code when the process is interrupted
            # (e.g. when the agent is shutting down due to Ctrl+C). In that case we
            # simply abort silently instead of reporting a failure to the user.
            if not self.running:
                return None
            print("[audio] arecord misslyckades:", e)
            return None
        except FileNotFoundError:
            print("[audio] arecord hittades inte - kontrollera att ALSA-verktyg är installerade")
            return None
        except Exception as e:
            print(f"[audio] Oväntat fel vid inspelning: {e}")
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

        # Spela statusljud för att indikera att filen skickas
        self.play_status_beep('sending')

        print(f"[http] Skickar {wav_path} till webhook {url}")
        with open(wav_path, "rb") as f:
            files = {"audio": ("audio.wav", f, "audio/wav")}
            data = {
                "deviceId": dev_info["id"],
                "tenant": dev_info["tenant"],
                "user": dev_info["user"],
            }
            
            # Spela statusljud för att indikera att vi väntar på svar
            self.play_status_beep('processing')
            
            try:
                resp = requests.post(url, data=data, files=files, timeout=timeout)
            except Exception as e:
                print("[http] Fel vid POST:", e)
                self.play_status_beep('error')
                return None

        print("[http] Svar status:", resp.status_code)
        if resp.status_code != 200:
            print("[http] Oväntad statuskod, ingen uppspelning.")
            self.play_status_beep('error')
            return None

        ctype = resp.headers.get("Content-Type", "")
        if not ctype.startswith("audio/"):
            print("[http] Content-Type är inte audio/* – fick troligen något annat:", ctype)
            self.play_status_beep('error')
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
        
        # Spela framgångsljud när vi fått svaret
        self.play_status_beep('success')
        
        # Om formatet inte är wav, konvertera till wav för uppspelning
        if reply_format != "wav":
            wav_path = f"{base_path}.wav"
            if not self.convert_to_wav(received_path, wav_path):
                print("[audio] Konvertering misslyckades, försöker spela upp originalfilen")
                return received_path
            print(f"[audio] Konverterade till wav: {wav_path}")
            return wav_path
        
        return received_path

    def convert_to_wav(self, input_path: str, output_path: str):
        """
        Konverterar ljudfil till WAV-format med ffmpeg eller sox.
        Returnerar True om konvertering lyckades, annars False.
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
            # Add timeout to prevent hanging during conversion
            result = subprocess.run(cmd_ffmpeg, check=True, capture_output=True, text=True, timeout=30)
            return True
        except subprocess.TimeoutExpired:
            print("[audio] ffmpeg timeout efter 30s - avbryter konvertering")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[audio] ffmpeg misslyckades eller saknas: {e}")
        
        # Om ffmpeg misslyckades, försök med sox
        cmd_sox = ["sox", input_path, output_path]
        print(f"[audio] Försöker konvertera med sox...")
        try:
            # Add timeout to prevent hanging during conversion
            result = subprocess.run(cmd_sox, check=True, capture_output=True, text=True, timeout=30)
            return True
        except subprocess.TimeoutExpired:
            print("[audio] sox timeout efter 30s - avbryter konvertering")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[audio] sox misslyckades eller saknas: {e}")
        
        return False

    def play_wav(self, wav_path: str):
        audio = self.cfg["audio"]
        dev = audio["device"]
        cmd = ["aplay", "-q", "-D", dev, wav_path]
        print("[audio] Spelar upp svar...")
        try:
            # Add reasonable timeout for playback (60 seconds should be enough for most responses)
            subprocess.run(cmd, check=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("[audio] aplay timeout efter 60s - avbryter uppspelning")
        except subprocess.CalledProcessError as e:
            print("[audio] aplay misslyckades:", e)
        except FileNotFoundError:
            print("[audio] aplay hittades inte - kontrollera att ALSA-verktyg är installerade")
        except Exception as e:
            print(f"[audio] Oväntat fel vid uppspelning: {e}")

    def handle_button(self):
        if not self._lock.acquire(blocking=False):
            print("[agent] Upptagen – hoppar över knapptryck.")
            return

        def _run():
            try:
                wav_in = self.record_once()
                if not wav_in:
                    # Spela felljud om inspelning misslyckades
                    self.play_status_beep('error')
                    return
                wav_out = self.send_to_webhook(wav_in)
                if wav_out:
                    self.play_wav(wav_out)
                # Om send_to_webhook returnerar None spelas felljud redan där
            finally:
                self._lock.release()

        threading.Thread(target=_run, daemon=True).start()

    def start(self):
        gpio_cfg = self.cfg["gpio"]
        self.button = Button(pin=gpio_cfg["button_pin"], pull_up=gpio_cfg.get("pull_up", True))
        self.button.on_pressed(self.handle_button)
        self.button.start()
        print("[agent] Klar. Tryck på knappen för att spela in. Ctrl+C för att avsluta.")
        while self.running:
            time.sleep(0.5)

    def stop(self):
        self.running = False
        if self.button:
            self.button.cleanup()


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

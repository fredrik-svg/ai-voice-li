import threading

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None


class Button:
    def __init__(self, pin: int, pull_up: bool = True):
        self.pin = pin
        self.pull_up = pull_up
        self._pressed_cb = None

    def on_pressed(self, cb):
        self._pressed_cb = cb

    def start(self):
        if GPIO is None:
            print("[gpio] RPi.GPIO saknas – simulerar knapp (tryck Enter i terminalen)")
            threading.Thread(target=self._simulate, daemon=True).start()
            return

        GPIO.setmode(GPIO.BCM)
        # Don't configure pull-up/down in software - the hardware already has it
        # The KS0314 ReSpeaker 2-Mic HAT has a hardware pull-up on GPIO17
        # so we detect FALLING edge when button is pressed (active low)
        GPIO.setup(self.pin, GPIO.IN)
        edge = GPIO.FALLING if self.pull_up else GPIO.RISING
        GPIO.add_event_detect(self.pin, edge, callback=self._edge, bouncetime=150)
        print(f"[gpio] Knapp på GPIO{self.pin} – tryck för att spela in.")

    def _edge(self, channel):
        if self._pressed_cb:
            self._pressed_cb()

    def cleanup(self):
        """Cleanup GPIO resources when shutting down."""
        if GPIO is not None:
            try:
                GPIO.cleanup(self.pin)
                print(f"[gpio] Städade GPIO{self.pin}")
            except Exception as e:
                print(f"[gpio] Kunde inte städa GPIO{self.pin}: {e}")

    def _simulate(self):
        while True:
            input("[gpio] Tryck Enter för att spela in...\n")
            if self._pressed_cb:
                self._pressed_cb()

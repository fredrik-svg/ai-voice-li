import threading
import time
from typing import Optional

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None


class Button:
    def __init__(self, pin: int, pull_up: bool = True):
        self.pin = pin
        self.pull_up = pull_up
        self._pressed_cb = None
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

    def on_pressed(self, cb):
        self._pressed_cb = cb

    def start(self):
        self._stop_event.clear()
        if GPIO is None:
            self._start_simulation(
                "[gpio] RPi.GPIO saknas – simulerar knapp (tryck Enter i terminalen)"
            )
            return

        try:
            GPIO.setmode(GPIO.BCM)
            # Don't configure pull-up/down in software - the hardware already has it
            # The KS0314 ReSpeaker 2-Mic HAT has a hardware pull-up on GPIO17
            # so we detect FALLING edge when button is pressed (active low)
            GPIO.setup(self.pin, GPIO.IN)
            # Remove any existing event detection to avoid "Failed to add edge detection" error
            try:
                GPIO.remove_event_detect(self.pin)
            except Exception:
                pass  # Ignore if no event detection was previously set
            edge = GPIO.FALLING if self.pull_up else GPIO.RISING
            try:
                GPIO.add_event_detect(
                    self.pin, edge, callback=self._edge, bouncetime=150
                )
                print(f"[gpio] Knapp på GPIO{self.pin} – tryck för att spela in.")
            except Exception as edge_error:
                print(
                    "[gpio] Kunde inte aktivera edge detection: "
                    f"{edge_error}. Växlar till polling-läge."
                )
                self._start_polling()
        except Exception as e:
            print(
                f"[gpio] Kunde inte initiera GPIO{self.pin}: {e}. "
                "Växlar till simulerat läge."
            )
            self.cleanup()
            self._start_simulation(
                "[gpio] Simulerar knapp (tryck Enter i terminalen)"
            )

    def _edge(self, channel):
        if self._pressed_cb:
            self._pressed_cb()

    def read_state(self):
        """
        Read the current state of the button.
        Returns True if button is not pressed (HIGH), False if pressed (LOW).
        For simulated mode, always returns True (not pressed).
        """
        if GPIO is None:
            return True
        return GPIO.input(self.pin)

    def cleanup(self):
        """Cleanup GPIO resources when shutting down."""
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=0.2)
        self._poll_thread = None
        if GPIO is not None:
            try:
                GPIO.remove_event_detect(self.pin)
            except Exception:
                pass
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

    def _start_simulation(self, message: Optional[str] = None):
        if message:
            print(message)
        threading.Thread(target=self._simulate, daemon=True).start()

    def _start_polling(self):
        if GPIO is None:
            return
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        print(
            f"[gpio] Knapp på GPIO{self.pin} – använder polling. Tryck för att spela in."
        )

    def _poll_loop(self):
        if GPIO is None:
            return
        last_state = GPIO.input(self.pin)
        while not self._stop_event.is_set():
            state = GPIO.input(self.pin)
            if self._is_pressed(state) and not self._is_pressed(last_state):
                if self._pressed_cb:
                    self._pressed_cb()
            last_state = state
            time.sleep(0.05)

    def _is_pressed(self, state: int) -> bool:
        if GPIO is None:
            return False
        if self.pull_up:
            return state == GPIO.LOW
        return state == GPIO.HIGH

import pigpio
import os
from utils.logger import logger
from utils.exceptions import ValveError


class Valve:
    """Gestion de la vanne électromagnétique via pigpio.
    Supporte les circuits actif-haut (VALVE_ACTIVE_HIGH=True)
    et actif-bas (VALVE_ACTIVE_HIGH=False).
    """

    def __init__(self):
        self.gpio_pin = int(os.getenv("GPIO_VANNE", "18"))
        self.active_high = os.getenv("VALVE_ACTIVE_HIGH", "True").lower() == "true"
        self.is_open = False

        self.pi = pigpio.pi()
        if not self.pi.connected:
            logger.error("Pigpio non connecté (Vanne) !")
            raise ValveError("Pigpio non connecté : impossible d'initialiser la vanne")

        self.pi.set_mode(self.gpio_pin, pigpio.OUTPUT)
        self.close()  # Sécurité au démarrage
        logger.info(
            f"Vanne initialisée sur GPIO {self.gpio_pin} "
            f"(active_high={self.active_high})"
        )

    def _signal_open(self):
        """Niveau GPIO pour ouvrir (actif-haut → 1, actif-bas → 0)."""
        return 1 if self.active_high else 0

    def _signal_close(self):
        """Niveau GPIO pour fermer (actif-haut → 0, actif-bas → 1)."""
        return 0 if self.active_high else 1

    def open(self):
        self.pi.write(self.gpio_pin, self._signal_open())
        self.is_open = True
        logger.info(f"Vanne ouverte (GPIO{self.gpio_pin}={self._signal_open()}).")

    def close(self):
        self.pi.write(self.gpio_pin, self._signal_close())
        self.is_open = False
        logger.info(f"Vanne fermée (GPIO{self.gpio_pin}={self._signal_close()}).")

    def cleanup(self):
        self.close()

"""Constants for the Backrest integration."""

from __future__ import annotations

from datetime import timedelta
from logging import Logger, getLogger

DOMAIN = "backrest"
LOGGER: Logger = getLogger(__package__)

MANUFACTURER = "Backrest"
DEFAULT_PORT = 9898
SCAN_INTERVAL = timedelta(minutes=1)

# Longest text Home Assistant accepts as an entity state.
MAX_STATE_LENGTH = 255

"""Constants for the Tesy Convector Local integration."""
from homeassistant.const import Platform

DOMAIN = "tesy_convector_local"

# Configuration options
CONF_IP_ADDRESS = "ip_address"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_UPDATE_INTERVAL = "update_interval"

# Default values
DEFAULT_NAME = "Tesy Convector"
DEFAULT_UPDATE_INTERVAL = 10  # seconds
MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 60

# Temperature limits
MIN_TEMP = 10.0
MAX_TEMP = 30.0
TEMP_STEP = 1.0

# Supported Platforms
PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.SENSOR,
]
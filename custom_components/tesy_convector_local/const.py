"""Constants for the Tesy Convector Integration."""
from homeassistant.const import Platform

DOMAIN = "tesy_convector_local"

# Connection types
CONF_AUTH_TYPE = "auth_type"
AUTH_TYPE_CLOUD = "cloud"
AUTH_TYPE_LOCAL = "local"

# Configuration options
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_USER_ID = "user_id"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_IP_ADDRESS = "ip_address"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_UPDATE_INTERVAL = "update_interval"

# Default values
DEFAULT_NAME = "Tesy Convector"
DEFAULT_UPDATE_INTERVAL = 20  # seconds
MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 120

# Temperature limits
MIN_TEMP = 10.0
MAX_TEMP = 30.0
TEMP_STEP = 1.0

# Supported Platforms
PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.NUMBER,
]
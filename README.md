# Tesy Convector Local Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modern, full-featured custom component for Home Assistant to control **Tesy Convectors** (such as CN06, CN05, and similar series) locally over your Wi-Fi network without relying on cloud services.

---

## ✨ Features

- ⚡ **100% Local Control**: Direct communication with your convector via HTTP REST API. No cloud dependency, super-fast response times.
- 🌡️ **Full Climate Entity Support**:
  - HVAC Modes: `Heat` and `Off`
  - Target Temperature control (`10°C` to `30°C`)
  - Integration with **External Temperature Sensors** (e.g. Zigbee/Z-Wave/BLE room sensors).
  - Modern Home Assistant `turn_on` and `turn_off` action support.
- 🎛️ **Hardware Controls (Switches)**:
  - **Child Lock** (`setLockDevice`): Lock/unlock physical buttons on the heater.
  - **Anti-Frost Protection** (`setAntiFrost`): Prevents room temperature from dropping below freezing.
  - **Adaptive Start** (`setAdaptiveStart`): Pre-heats room to reach set target at programmed schedule.
  - **Open Window Detection** (`setOpenedWindow`): Automatically pauses heating if an open window is detected.
  - **Air Care / UV Lamp** (`setUV`): Toggle air purification lamp (on supported models).
- 📊 **Diagnostic Sensors**:
  - Operating mode readout (`manual`, `eco`, `comfort`, `program`).
  - Internal temperature sensor readout (if reported by firmware).
- ⚙️ **Dynamic Options Flow**: Change the external temperature sensor or polling interval from the Home Assistant UI anytime without re-adding the integration.
- 🌐 **Multilingual**: Full English and Romanian interface translations.
- 🛠️ **Service Actions**: Includes `tesy_convector_local.set_temperature_correction` for sensor calibration.

---

## 📦 Installation

### Option 1: Via HACS (Recommended)

1. Open **Home Assistant** and navigate to **HACS** > **Integrations**.
2. Click the **3 dots** in the top right corner and select **Custom repositories**.
3. Add the URL of your repository:
   - **Repository**: `https://github.com/<your-username>/TesyConvectorLocal`
   - **Type**: `Integration`
4. Click **Add**, find **Tesy Convector Local**, and click **Download**.
5. **Restart Home Assistant**.

### Option 2: Manual Installation

1. Download the latest release ZIP from the repository.
2. Copy the `custom_components/tesy_convector_local` directory into your Home Assistant `<config_dir>/custom_components/` directory.
   ```text
   config/
   └── custom_components/
       └── tesy_convector_local/
           ├── __init__.py
           ├── climate.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           ├── sensor.py
           ├── switch.py
           ├── services.yaml
           ├── strings.json
           └── translations/
               ├── en.json
               └── ro.json
   ```
3. **Restart Home Assistant**.

---

## ⚙️ Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Tesy Convector Local** and select it.
3. Fill in the configuration:
   - **IP Address**: The local IP address of your convector (e.g. `192.168.1.150`). *It is recommended to assign a static/reserved DHCP IP address in your router.*
   - **External Temperature Sensor** *(Optional)*: Select any sensor entity in Home Assistant (e.g. `sensor.living_room_temperature`) to supply ambient temperature readings.
4. Click **Submit**.

---

## 🔄 Options

You can adjust settings at any time:
1. Go to **Settings** > **Devices & Services** > **Tesy Convector Local**.
2. Click **Configure** on the integration card.
3. Modify the external temperature sensor or the update polling interval (5 - 60 seconds).

---

## 🧪 Tested Models

- Tesy CN06AS
- Tesy CN05 Series
- Tesy CN04 Series with Wi-Fi module

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
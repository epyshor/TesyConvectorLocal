# Tesy Convector Integration for Home Assistant (Cloud & Local)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-1.2.0-green.svg)](https://github.com/epyshor/TesyConvectorLocal/releases/tag/v1.2.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modern custom component for Home Assistant supporting **Tesy Convectors** and heaters via both **MyTESY Cloud (mytesy.com)** and **Direct Local Network (IP Address)**.

---

## ✨ Features

- ☁️ **MyTESY Cloud (`mytesy.com`) Integration**:
  - Simple login with your MyTESY **Email** and **Password**.
  - Automatic discovery of all devices on your account with a selection menu.
- ⚡ **Direct Local Network Control (IP)**:
  - Local control for devices reachable directly on the local LAN.
- 🌡️ **Full Climate Entity Support**:
  - HVAC Modes: `Heat` and `Off`
  - Target Temperature control (`10°C` to `30°C`)
  - Integration with **External Temperature Sensors** (e.g. Zigbee/Z-Wave/BLE room sensors).
  - Modern Home Assistant `turn_on` and `turn_off` action support.
- 🎛️ **Hardware Controls (Switches)**:
  - **Boost Mode** (`boost_sw`): Quick heating mode.
  - **Child Lock** (`setLockDevice`): Lock/unlock physical buttons on the heater.
  - **Anti-Frost Protection** (`setAntiFrost`): Prevents room temperature from dropping below freezing.
  - **Adaptive Start** (`setAdaptiveStart`): Pre-heats room to reach set target at programmed schedule.
  - **Open Window Detection** (`setOpenedWindow`): Automatically pauses heating if an open window is detected.
  - **Air Care / UV Lamp** (`setUV`): Toggle air purification lamp (on supported models).
- 📊 **Diagnostic Sensors**:
  - Operating mode readout (`manual`, `eco`, `comfort`, `program`).
  - Heating state (`HEATING` / `READY`).
  - Internal temperature sensor readout.
- ⚙️ **Dynamic Options Flow**: Change the external temperature sensor or polling interval from the Home Assistant UI anytime without re-adding the integration.
- 🌐 **Multilingual**: Full English and Romanian interface translations.

---

## 📦 Installation

### Option 1: Via HACS (Recommended)

1. Open **Home Assistant** and navigate to **HACS** > **Integrations**.
2. Click the **3 dots** in the top right corner and select **Custom repositories**.
3. Add the URL of your repository:
   - **Repository**: `https://github.com/epyshor/TesyConvectorLocal`
   - **Type**: `Integration`
4. Click **Add**, find **Tesy Convector (Cloud & Local)**, and click **Download**.
5. **Restart Home Assistant**.

### Option 2: Manual Installation

1. Download the latest release from the repository.
2. Copy the `custom_components/tesy_convector_local` directory into your Home Assistant `<config_dir>/custom_components/` directory.
3. **Restart Home Assistant**.

---

## ⚙️ Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Tesy Convector** and select it.
3. Choose your connection method:
   - **MyTESY Cloud (mytesy.com)**:
     - Enter your MyTESY **Email** and **Password**.
     - If you have multiple convectors, select the one you wish to add from the dropdown list.
   - **Local Network (IP Address)**:
     - Enter the local IP address of the convector.
4. *(Optional)* Select an external temperature sensor to provide ambient room temperature readings.
5. Click **Submit**.

---

## 🔄 Options

You can adjust settings at any time:
1. Go to **Settings** > **Devices & Services** > **Tesy Convector**.
2. Click **Configure** on the integration card.
3. Modify the external temperature sensor or the update polling interval (5 - 120 seconds).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
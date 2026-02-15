#!/bin/bash
# Air Sensor Installation Script
# Run with: bash install.sh

set -e

echo "Installing Airsensor Python Application..."

if [ "$(id -u)" -eq 0 ]; then
    fatal "Script should not be run as root. Try './install.sh'\n"
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "Warning: This device doesn't appear to be a Raspberry Pi."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-smbus \
    i2c-tools \
    git \
    fonts-dejavu \
    fonts-dejavu-core

# Enable I2C and SPI
echo "Enabling I2C and SPI..."
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0


# Create necessary directories
echo "Creating Application Directory at /opt/airsensor..."
echo "Your password may be required to install system files..."

if [ ! -d "/opt/airsensor" ]; then
  sudo mkdir /opt/airsensor
fi
sudo chown -R $USER /opt/airsensor
sudo rm -fr /opt/airsensor/
git clone https://github.com/jerbzz/airsensor /opt/airsensor

# Make a venv
echo "Creating Python Virtual Environment..."
python -m venv /opt/airsensor/.venv/airsensor

# Install Python packages
echo "Installing Python dependencies..."
/opt/airsensor/.venv/airsensor/bin/pip3 install -r /opt/airsensor/requirements.txt

# Check I2C devices
echo "Checking I2C devices..."
i2cdetect -y 1

echo ""
echo "You should see:"
echo "  - 0x23 (LTR559 light sensor)"
echo "  - 0x49 (MICS6814 gas sensors)"
echo "  - 0x62 (SCD41 CO2 sensor, if connected)"
echo "  - 0x76 (BME280 temp/humidity/pressure)"
echo ""

# Copy example config if needed
echo "Copying default configuration..."
if [ ! -f /opt/airsensor/config/config.yaml ]; then
    cp /opt/airsensor/config/config.yaml.default /opt/airsensor/config/config.yaml
    echo "Config file created at config/config.yaml"
    echo "Please edit this file with your settings before running."
fi

# Install systemd service
read -p "Would you like to install and start a systemd service to run this application automatically at startup? (y/n) "
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Your password may be required to install system files..."
    sudo cp airsensor.service /etc/systemd/system/
    sudo systemctl enable airsensor
    sudo systemctl start airsensor
    echo ""
fi


echo "Installation Complete!"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/airsensor/config/config.yaml with your settings incuding updating MQTT broker address for Home Assistant"
echo "  Then either, to run the application now:"
echo "  2a. Activate the Python virtual environment by running source /opt/airsensor/.venv/bin/activate"
echo "  3a. Run: python3 /opt/airsensor/src/main.py"
echo "  Or, if you have chosen to install the systemd startup service:"
echo "  2b. Nothing!"
echo ""

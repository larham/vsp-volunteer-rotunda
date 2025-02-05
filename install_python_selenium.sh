#!/usr/bin/env bash

# install chrome and selenium on ubuntu

# https://developers.supportbee.com/blog/setting-up-cucumber-to-run-with-Chrome-on-Linux/
# https://gist.github.com/curtismcmullan/7be1a8c1c841a9d8db2c
# https://stackoverflow.com/questions/10792403/how-do-i-get-chrome-working-with-selenium-using-php-webdriver
# https://stackoverflow.com/questions/26133486/how-to-specify-binary-path-for-remote-chromedriver-in-codeception
# https://stackoverflow.com/questions/40262682/how-to-run-selenium-3-x-with-chrome-driver-through-terminal
# https://askubuntu.com/questions/760085/how-do-you-install-google-chrome-on-ubuntu-16-04
# https://gist.github.com/larham/ee5b77dce991f52c790e846d87042b6d

set -euo pipefail

# Chrome Version
CHROME_DRIVER_VERSION=`curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE`

# Selenium version: stuck on 3.9 because selenium 4 stopped including standalone
SELENIUM_STANDALONE_VERSION=3.9.1
SELENIUM_SUBDIR=$(echo "$SELENIUM_STANDALONE_VERSION" | cut -d"." -f-2)
INSTALL_DIR=/usr/local/bin
# Remove existing downloads and binaries so we can start from scratch.
rm -f ~/selenium-server-standalone-*.jar
rm -f ~/chromedriver_linux64.zip ~/chromedriver ~/LICENSE.chromedriver
sudo rm -f $INSTALL_DIR/chromedriver
sudo rm -f $INSTALL_DIR/selenium-server-standalone.jar

# Install dependencies.
sudo apt-get update
sudo apt-get install -y unzip openjdk-8-jre-headless xvfb libxi6 libgconf-2-4

# Install Chrome.
curl -sS -o - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add
if ! grep -q "https://dl.google.com/linux/chrome/deb/"  /etc/apt/sources.list.d/google-chrome.list ; then
    echo "deb https://dl.google.com/linux/chrome/deb/ stable main" | sudo tee -a /etc/apt/sources.list.d/google-chrome.list
fi
sudo apt-get -y update
sudo apt-get -y install google-chrome-stable
sudo apt-get -y install python3-pip
sudo apt-get -y install python3-selenium
sudo apt-get -y install python3-venv
sudo apt-get -y install chromium-chromedriver

# Install ChromeDriver.
wget -N https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip -P ~/
unzip ~/chromedriver_linux64.zip -d ~/
rm -f ~/chromedriver_linux64.zip ~/LICENSE.chromedriver
sudo mv -f ~/chromedriver $INSTALL_DIR/chromedriver
sudo chown root:root $INSTALL_DIR/chromedriver
sudo chmod 0755 $INSTALL_DIR/chromedriver

# Install Selenium.
wget -N https://selenium-release.storage.googleapis.com/$SELENIUM_SUBDIR/selenium-server-standalone-$SELENIUM_STANDALONE_VERSION.jar -P ~/
sudo mv -f ~/selenium-server-standalone-$SELENIUM_STANDALONE_VERSION.jar $INSTALL_DIR/selenium-server-standalone.jar
sudo chown root:root $INSTALL_DIR/selenium-server-standalone.jar
sudo chmod 0755 $INSTALL_DIR/selenium-server-standalone.jar
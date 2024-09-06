# Automation and Analysis Tools

This repository contains a collection of Python scripts designed for automation and analysis tasks related to Android applications and proxy management. Below are the details of each script included in this repository.

## 1. UI Automator Server (`uiAutomatorServer.py`)

This script utilizes the `uiautomator2` library to interact with Android devices for testing purposes. It demonstrates how to automate basic operations in apps like a calculator and Google Translate.

### Features
- Connects to an Android device using its device ID.
- Automates button clicks in the calculator app to perform a simple addition.
- Checks and switches the language in Google Translate if it's not set to English.

### Usage
Ensure the device is connected and the server is running. Execute the script directly to perform the automated tasks.


## 2. Appium Automator (`appiumAutomator.py`)

This script uses the `appium` library to automate interactions with an Android application. It sets up a driver with specific capabilities, logs into an application, navigates through it, and submits data.

### Features
- Configures and connects to an Android device using Appium.
- Performs login and data submission within an app.

### Usage
Run the script to initiate the automated testing sequence on the specified app.


## 3. Proxy Rotator (`proxyRotator.py`)

This script manages a list of proxies, checks their validity against a test URL, and rotates them to access a target site. It ensures that no proxy is overused by limiting the number of requests per proxy.

### Features
- Validates proxies by making HTTP requests.
- Rotates proxies to manage request distribution effectively.

### Usage
Update the `proxies_list.txt` with your proxies and run the script to manage access through them.



## 4. APK Analyzer (`apkAnalyzer.py`)

This script uses `androguard` to analyze Android APK files. It extracts metadata such as package name, version code, version name, and permissions from an APK.

### Features
- Analyzes APK files to extract essential metadata.
- Useful for quick inspections of APK files without installing them.

### Usage
Specify the path to the APK file and run the script to get the metadata.


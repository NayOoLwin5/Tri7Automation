# Import necessary libraries
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
from appium.options.common import AppiumOptions

import time

def setup_driver():
    # Define desired capabilities
    desired_cap = {
        "platformName": "Android",
        "appPackage": "com.ayaplus.subscriber.development",
        "platformVersion": "13.0",
        "deviceName": "One Plus", 
        "appAcitivity": "com.ayaplus.subscriber.MainActivity",
        "automationName": "UiAutomator2",
        "udid" : "e8fbb12d",
        "appWaitForLaunch" : False,
        "appium:appWaitActivity": "*"
    }

    driver = webdriver.Remote("http://localhost:4724", options=UiAutomator2Options().load_capabilities(desired_cap))
    return driver

def login(driver, username, password):
    # Locate and interact with login elements
    driver.find_element(AppiumBy.ID, "com.ayaplus.subscriber.development/login_button").click()

def navigate_and_submit_data(driver):
    # Navigate through the app and submit data
    driver.find_element(AppiumBy.ID, "com.ayaplus.subscriber.development/navigate_button").click()
    driver.find_element(AppiumBy.ID, "com.ayaplus.subscriber.development/data_input").send_keys("Sample Data")
    driver.find_element(AppiumBy.ID, "com.ayaplus.subscriber.development/submit_button").click()

def main():
    driver = setup_driver()
    try:
        # Perform login
        login(driver, "testuser", "password123")
        time.sleep(2)  # Wait for login to complete

        # Navigate and submit data
        navigate_and_submit_data(driver)
        time.sleep(2)  # Wait for submission to complete

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
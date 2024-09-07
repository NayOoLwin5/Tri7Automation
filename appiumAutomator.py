# Import necessary libraries
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
import time

import time

def setup_driver():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.app_package = "com.sololearn"
    options.platform_version = "13.0"
    options.device_name = "One Plus"
    options.app_activity = "com.sololearn.app.ui.launcher.LauncherActivity"  # Corrected typo here
    options.automation_name = "UiAutomator2"
    options.udid = "e8fbb12d"
    options.app_wait_for_launch = False
    options.set_capability("appium:appWaitActivity", "*")

    driver = webdriver.Remote("http://localhost:4724", options=options)
    return driver

def login(driver):
    driver.find_element(AppiumBy.ID, "com.sololearn:id/continueWithGoogle").click()
    time.sleep(2)
    elements = driver.find_elements(AppiumBy.ID, "com.google.android.gms:id/account_name")
    for element in elements:
      if element.text == "nayoolwinpersonal@gmail.com":
          driver.find_element(AppiumBy.ID, "com.google.android.gms:id/account_name").click()
          break

def navigate(driver):
    
    elements = driver.find_elements(AppiumBy.ID, "com.sololearn:id/title")
    for element in elements:
      if element.text == "Overview":
          driver.find_element(AppiumBy.ID, "com.sololearn:id/iconExpandState").click()
          sub_elements = driver.find_elements(AppiumBy.ID, "com.sololearn:id/title")
          for sub_element in sub_elements:
            if sub_element.text == "Your First Lesson":
              driver.find_element(AppiumBy.ID, "com.sololearn:id/title").click()
              time.sleep(4)
              break
      
def main():
    driver = setup_driver()
    time.sleep(8)  
    login(driver)
    time.sleep(8)
    navigate(driver)
    time.sleep(10)

if __name__ == "__main__":
    main()
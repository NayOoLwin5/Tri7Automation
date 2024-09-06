import uiautomator2 as u2
import time

device = u2.connect("e8fbb12d")  

# print(device.info)

# device.start_uiautomator()

# Example usage after scrolling
calculator = "com.oneplus.calculator"
device.app_start(calculator)

device.wait_timeout = 5

device(resourceId="com.oneplus.calculator:id/digit_9").click()
device(resourceId="com.oneplus.calculator:id/op_add").click()
device(resourceId="com.oneplus.calculator:id/digit_3").click()
text_data = device(resourceId="com.oneplus.calculator:id/result").get_text()

print("Extracted Text:", text_data)
device.app_stop(calculator)

google_translate = "com.google.android.apps.translate"
device.app_start(google_translate)

device.wait_timeout = 5

language_a = device(resourceId="com.google.android.apps.translate:id/language_button_a").get_text()
print("Current Language : ", language_a)
if language_a.lower() != "english":
    time.sleep(3)
    device(resourceId="com.google.android.apps.translate:id/language_button_a").click()
    time.sleep(3)
    
    list_items = []
    previous_items_count = -1

    while True:
        device(scrollable=True).scroll(steps=20)



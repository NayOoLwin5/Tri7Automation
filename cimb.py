import uiautomator2 as u2
from uiautomator2 import UiObjectNotFoundError, ConnectError
import time
import re
import datetime
import traceback

cimb_banking = "id.co.cimbniaga.mobile.android"
AUTHENTICATE_ACTIVITY = '.uat.modules.login.view.LoginActivity'
HOME_ACTIVITY = '.uat.modules.home.view.HomeScreenActivity'
MY_ACCOUNT_ACTIVITY = '.uat.modules.myaccount.view.myaccountv2.presentation.ui.MyAccountActivity'
TRANSACTIONS_ACTIVITY = '.uat.modules.myaccount.view.detailv2.casa.presentation.ui.DetailAccountCasaActivity'
UPDATE_AVAILABLE_ACTIVITY = 'com.google.android.finsky.playcoreacquisition.PlayCoreAcquisitionActivity'
IS_AUTHENTICATED = False
IS_PAUSED = False
PIN = "Ningsih221kr"
device_id = "100.79.114.17:5556"

def navigate_to_transactions_history(device_id):
    try:
        d = u2.connect(device_id)
        
    except ConnectError as e:
        print(f"Failed to connect to device: {e}")
        return

    try:
        __watcher_check_popup(d)
        time.sleep(2)
        current_activity = d.app_current().get('activity')
        if current_activity != HOME_ACTIVITY:
            print(f"Current activity is not HOME_ACTIVITY, it is {current_activity}")
            return
        
        idr_text = d.xpath('//android.widget.TextView[@resource-id="id.co.cimbniaga.mobile.android:id/tv_amount"]')
        if not idr_text.exists:
            login_button = d.xpath('//android.widget.TextView[@text="Login or Create Account Now"]')
            if login_button.exists:
                login_button.click()
                _authenticate(d, PIN)
        else:
            print("In initial state, authenticated.")
            idr_text.click()
            navigate_to_transactions_history(device_id)
            IS_AUTHENTICATED = True
        
    except UiObjectNotFoundError as e:
        print(f"Failed to navigate {cimb_banking}. Error: {e}")
        return
                


def __watcher_check_popup(d):
    # Define watchers for different popup scenarios
    d.watcher("knock_knock_watcher").when('//android.widget.TextView[@text="Knock, knock, are you there?"]').when('//android.widget.Button[@text="Yes, I\'m still here"]').click()
    d.watcher("no_internet_watcher").when('//android.widget.TextView[@text="No internet connection"]').when('//android.widget.Button[@text="Retry"]').click()
    d.watcher("session_expired_watcher").when('//android.widget.TextView[@text="Your session has expired"]').when('//android.widget.Button[@text="Login"]').click()
    d.watcher("generic_ok_watcher").when('//android.widget.TextView[@text="No internet connection"]').when('//android.widget.Button[@text="OK"]').click()

    # Start all watchers
    d.watcher.start()

    # Wait for a short period to allow watchers to handle any popups
    time.sleep(1)
    return

def batch_pulling_task(device_id, retry_count=0):
    try:
        d = u2.connect(device_id)
    except ConnectError as e:
        print(f"Failed to connect to device: {e}")
        return

    # Click anywhere on the screen # Click at the center of the screen

    recent_text = "Recent"
    recent_field = d.xpath(f'//android.widget.TextView[@text="{recent_text}"]')
    __watcher_check_popup(d)

    while not recent_field.exists:
        print("Waiting for 'Recent' text field to appear...")
        time.sleep(1)
        recent_field = d.xpath(f'//android.widget.TextView[@text="{recent_text}"]')

    print("'Recent' text field appeared. Starting batch pulling...")

    segment_line_class = "android.widget.LinearLayout"
    recycler_view_id = "id.co.cimbniaga.mobile.android:id/rv_transaction"
    transaction_title_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_title"
    transaction_value_id = "id.co.cimbniaga.mobile.android:id/tv_transaction_value"

    printed_items = set()
    # current_date = datetime.datetime.now().date()
    current_date = datetime.date(datetime.datetime.now().year, datetime.datetime.now().month, 16)

    transaction_count = 0
    max_transactions = 15 if retry_count >= 1 else float('inf')

    while True:
        try:
            recycler_view = d(resourceId=recycler_view_id)
            transaction_items = recycler_view.child(className="android.view.ViewGroup")

            transactions = []
            for i, item in enumerate(transaction_items):
                if i >= 3:
                    break
                visible_texts = [text.get_text() for text in item.child(className="android.widget.TextView")]
                
                transaction = tuple(text for text in visible_texts if text != '00' and 'IDR' not in text)
                
                transaction_value = item.child(resourceId=transaction_value_id).get_text()
                if any('IDR' in text for text in visible_texts):
                    transaction += (transaction_value,)
                if transaction and transaction not in printed_items:
                    transactions.append(transaction)
                    printed_items.add(transaction)
            for transaction in transactions:
                try:
                    transaction_date = datetime.datetime.strptime(transaction[1], '%d %b %Y %H:%M').date()
                    if transaction_date != current_date:
                        print(f"Transaction date {transaction_date} is not current date. Skipping.")
                        continue

                    formatted_date = time.strftime('%Y-%m-%d', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    formatted_datetime = time.strftime('%Y-%m-%dT%H:%M:%S+0700', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    title_text = transaction[0]
                    memo1_text = "?" if len(transaction) <= 3 or transaction[2] == "-" else transaction[2]
                    memo2_text = "?" if len(transaction) <= 4 or transaction[3] == "-" else transaction[3]
                    memo3_text = "?" if len(transaction) <= 5 or transaction[4] == "-" else transaction[4]
                    amount_text = transaction[-1]
                    transaction_type = "DB" if "-" in amount_text else "CR" if "+" in amount_text else "?"
                    amount_numeric = float(amount_text.replace("IDR", "").replace("-", "").replace("+", "").replace(",", "").strip())
                    
                    if title_text == "OVERBOOKING TO KWIK" and memo2_text != "?":
                        match = re.search(r'\S+\s{1,}\S+\s{1,}(\S.*)$', memo2_text)
                        if match:
                            memo2_text = match.group(1)
                    elif title_text == "REMITTANCE CR - BIFAST" and memo2_text != "?":
                        match = re.search(r'BFS\s{1,}\w{2,}.*UN\s{1,}(\S.*)$', memo2_text)
                        if match:
                            memo2_text = match.group(1)
                    elif (title_text in ["OVERBOOKING TO SA", "OVERBOOKING", "OVERBOOKING FROM SA", "OVERBOOKING FROM CA"]) and memo1_text != "?":
                        match = re.search(r'(?<=TRF)\s{1,}\w{2,}\s{1,}(\S.*)$', memo1_text)
                        if match:
                            memo1_text = match.group(1)
                    
                    memos = [memo1_text, memo2_text, memo3_text]
                    non_question_memos = [memo for memo in memos if memo != "?"]
                    question_memos = [memo for memo in memos if memo == "?"]
                    all_memos = " -- ".join(non_question_memos + question_memos)
                    result = f"{formatted_date} | {title_text} -- {all_memos} -- {amount_text} -- {formatted_datetime} | {transaction_type} | {amount_numeric} | {str(float(0))}"
                    print(result)
                    
                    transaction_count += 1
                    if transaction_count >= max_transactions:
                        print(f"Reached maximum of {max_transactions} transactions. Exiting batch pulling.")
                        return
                except IndexError as e:
                    print(f"Error processing transaction: {transaction}. Error: {str(e)}")
                except ValueError as e:
                    print(f"Error parsing transaction data: {transaction}. Error: {str(e)}")

            previous_transactions = [t.info for t in recycler_view.child(resourceId=transaction_title_id)]

            # Get the bounds of the last transaction item
            last_transaction = recycler_view.child(resourceId=transaction_title_id)[-1].info['bounds']
            start_x = (last_transaction['left'] + last_transaction['right']) // 2

            # Get the bounds of the 'Recent' field for the end position
            recent_bounds = recent_field.info['bounds']
            end_x = (recent_bounds['left'] + recent_bounds['right']) // 2
            end_y = recent_bounds['top'] + 70

            # Get the bounds of the last segment line
            segment_lines = d(className=segment_line_class)
            if segment_lines:
                last_segment_line = segment_lines[-1].info['bounds']
                start_y = last_segment_line['bottom']
            else:
                start_y = 1400  # Default value if no segment line is found

            # Perform the swipe
            d.swipe(start_x, start_y, end_x, end_y, duration=0.5)
            try:
                d(resourceId=transaction_title_id).wait(timeout=7)
            except UiObjectNotFoundError:
                break

            current_transactions = [t.info for t in d(resourceId=transaction_title_id)]
            if previous_transactions == current_transactions:
                print("No more transactions found. Exiting batch pulling.")
                break

        except UiObjectNotFoundError as e:
            print(f"No more transactions found or failed to scroll. Error: {str(e)}. Exiting batch pulling.")
            break

    # Retry logic
    if retry_count < 3:  # Limit retries to 3 times
        print(f"Retrying batch pulling task. Attempt {retry_count + 1}")
        # Scroll to the top before retrying
        while True:
            previous_view = d(resourceId=transaction_title_id).info
            d.swipe(start_x, end_y, end_x, start_y, duration=0.5)  # Swipe up
            time.sleep(2)  # Wait for the screen to settle
            current_view = d(resourceId=transaction_title_id).info
            if current_view == previous_view:
                print("Reached the top of the transaction list")
                break
        batch_pulling_task(device_id, retry_count + 1)
    else:
        print("Maximum retry attempts reached. Stopping batch pulling task.")



def write_hierarchy(device_id):
    xml_content = device_id.dump_hierarchy()
    with open("output2.xml", "w") as f:
        f.write(xml_content)    
    print("UI hierarchy saved to hierarchy.xml")


def _authenticate(d, PIN):
    try:
        time.sleep(5)
        if d.app_current()['activity'] == 'some':
            d.press('back')

        __watcher_check_popup(d)
        IS_AUTHENTICATED = False
        if not __wait_for_exists(d, activity='.uat.modules.login.view.LoginActivity'):
            raise TimeoutError("Condition not met within 30 seconds. activity='.uat.modules.login.view.LoginActivity'")

        password_field = __wait_for_exists(d, xpath='//android.widget.EditText[@text="Enter user ID"]', timeout=30)
        password_field.click()

        # self.DEVICE.send_keys(self.PIN)
        d.shell(f'input text {PIN}')
        time.sleep(2)

        login_button = __wait_for_exists(d, xpath='//android.widget.Button[@text="Login"]')
        login_button.click()
        navigate_to_transactions_history(device_id)
    except TimeoutError as e:
        current_app = d.app_current().get('package')
        current_activity = d.app_current().get('activity')
            
        if current_app == cimb_banking and current_activity == UPDATE_AVAILABLE_ACTIVITY:
            while d.app_current().get('activity') != AUTHENTICATE_ACTIVITY:
                d.press('back')
                time.sleep(2)

            return _authenticate(d, PIN)
        else:
            print(e)
            __handle_error(d, e)
    except Exception as e:
        print(e)
        __handle_error(d, e)

def __wait_for_exists(d, xpath: str = None, timeout: int = 5, app_package: str = None, activity: str = None):
    for attempt in range(timeout):
        if xpath and d.xpath(xpath).exists:
            return d.xpath(xpath)
        if app_package and d.app_current().get('package') == app_package:
            return True
        if activity and d.app_current().get('activity') == activity:
            return True
        
        time.sleep(1)

    raise TimeoutError(f"Condition not met within {timeout} seconds. xpath={xpath}, app_package={app_package}, activity={activity}")


def __handle_error(d, error: Exception):
    print(f"An error occurred: {error}")
    print(traceback.format_exc())

    IS_PAUSED = True

    while d.app_current().get('activity') != HOME_ACTIVITY:
        d.press("back")

        time.sleep(1)

    IS_PAUSED = False



try:
    batch_pulling_task(device_id)
    # print("Batch pulling task completed.")
    # d = u2.connect(device_id)
    # some_function(d)
    # write_hierarchy(d)
    # _authenticate(d, PIN)
    # navigate_to_transactions_history(device_id)
except Exception as e:
    print(f"Unexpected error occurred: {e}")
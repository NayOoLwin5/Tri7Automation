import uiautomator2 as u2
from uiautomator2 import UiObjectNotFoundError, ConnectError
import time
import re
import datetime
import traceback

class CIMBBankingAutomation:
    CIMB_BANKING = "id.co.cimbniaga.mobile.android"
    AUTHENTICATE_ACTIVITY = '.uat.modules.login.view.LoginActivity'
    HOME_ACTIVITY = '.uat.modules.home.view.HomeScreenActivity'
    MY_ACCOUNT_ACTIVITY = '.uat.modules.myaccount.view.myaccountv2.presentation.ui.MyAccountActivity'
    TRANSACTIONS_ACTIVITY = '.uat.modules.myaccount.view.detailv2.casa.presentation.ui.DetailAccountCasaActivity'
    UPDATE_AVAILABLE_ACTIVITY = 'com.google.android.finsky.playcoreacquisition.PlayCoreAcquisitionActivity'

    def __init__(self, device_id, pin):
        self.device_id = device_id
        self.pin = pin
        self.is_authenticated = False
        self.is_paused = False
        self.device = None

    def connect(self):
        try:
            self.device = u2.connect(self.device_id)
        except ConnectError as e:
            raise ConnectionError(f"Failed to connect to device: {e}")

    def navigate_to_transactions_history(self):
        try:
            self.__watcher_check_popup()
            time.sleep(2)
            current_activity = self.device.app_current().get('activity')
            if current_activity != self.HOME_ACTIVITY:
                raise ValueError(f"Current activity is not HOME_ACTIVITY, it is {current_activity}")
            
            idr_text = self.device.xpath('//android.widget.TextView[@resource-id="id.co.cimbniaga.mobile.android:id/tv_amount"]')
            if not idr_text.exists:
                login_button = self.device.xpath('//android.widget.TextView[@text="Login or Create Account Now"]')
                if login_button.exists:
                    login_button.click()
                    self._authenticate()
            else:
                print("In initial state, authenticated.")
                idr_text.click()
                self.is_authenticated = True
            
        except UiObjectNotFoundError as e:
            raise RuntimeError(f"Failed to navigate {self.CIMB_BANKING}. Error: {e}")

    def __watcher_check_popup(self):
        self.device.watcher("knock_knock_watcher").when('//android.widget.TextView[@text="Knock, knock, are you there?"]').when('//android.widget.Button[@text="Yes, I’m still here"]').click()
        self.device.watcher("no_internet_watcher").when('//android.widget.TextView[@text="No internet connection"]').when('//android.widget.Button[@text="Retry"]').click()
        self.device.watcher("session_expired_watcher").when('//android.widget.TextView[@text="Your session has expired"]').when('//android.widget.Button[@text="Login"]').click()
        self.device.watcher("generic_ok_watcher").when('//android.widget.TextView[@text="No internet connection"]').when('//android.widget.Button[@text="OK"]').click()
        self.device.watcher.start()
        time.sleep(1)

    def batch_pulling_task(self, retry_count=0):
        recent_text = "Recent"
        recent_field = self.device.xpath(f'//android.widget.TextView[@text="{recent_text}"]')
        self.__watcher_check_popup()

        while not recent_field.exists:
            print("Waiting for 'Recent' text field to appear...")
            time.sleep(1)
            recent_field = self.device.xpath(f'//android.widget.TextView[@text="{recent_text}"]')

        print("'Recent' text field appeared. Starting batch pulling...")

        segment_line_class = "android.widget.LinearLayout"
        recycler_view_id = "id.co.cimbniaga.mobile.android:id/rv_transaction"
        transaction_title_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_title"
        transaction_value_id = "id.co.cimbniaga.mobile.android:id/tv_transaction_value"

        printed_items = set()
        current_date = datetime.date(datetime.datetime.now().year, datetime.datetime.now().month, 16)

        transaction_count = 0
        max_transactions = 15 if retry_count >= 1 else float('inf')

        while True:
            try:
                recycler_view = self.device(resourceId=recycler_view_id)
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
                        
                        memo2_text = self._process_memo(title_text, memo2_text)
                        memo1_text = self._process_memo(title_text, memo1_text)
                        
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

                last_transaction = recycler_view.child(resourceId=transaction_title_id)[-1].info['bounds']
                start_x = (last_transaction['left'] + last_transaction['right']) // 2

                recent_bounds = recent_field.info['bounds']
                end_x = (recent_bounds['left'] + recent_bounds['right']) // 2
                end_y = recent_bounds['top'] + 70

                segment_lines = self.device(className=segment_line_class)
                if segment_lines:
                    last_segment_line = segment_lines[-1].info['bounds']
                    start_y = last_segment_line['bottom']
                else:
                    start_y = 1400

                self.device.swipe(start_x, start_y, end_x, end_y, duration=0.5)
                try:
                    self.device(resourceId=transaction_title_id).wait(timeout=7)
                except UiObjectNotFoundError:
                    break

                current_transactions = [t.info for t in self.device(resourceId=transaction_title_id)]
                if previous_transactions == current_transactions:
                    print("No more transactions found. Exiting batch pulling.")
                    break

            except UiObjectNotFoundError as e:
                print(f"No more transactions found or failed to scroll. Error: {str(e)}. Exiting batch pulling.")
                break

        if retry_count < 3:
            print(f"Retrying batch pulling task. Attempt {retry_count + 1}")
            while True:
                previous_view = self.device(resourceId=transaction_title_id).info
                self.device.swipe(start_x, end_y, end_x, start_y, duration=0.5)
                time.sleep(2)
                current_view = self.device(resourceId=transaction_title_id).info
                if current_view == previous_view:
                    print("Reached the top of the transaction list")
                    break
            self.batch_pulling_task(retry_count + 1)
        else:
            print("Maximum retry attempts reached. Stopping batch pulling task.")

    def _process_memo(self, title_text, memo_text):
        if title_text == "OVERBOOKING TO KWIK" and memo_text != "?":
            match = re.search(r'\S+\s{1,}\S+\s{1,}(\S.*)$', memo_text)
            if match:
                return match.group(1)
        elif title_text == "REMITTANCE CR - BIFAST" and memo_text != "?":
            match = re.search(r'BFS\s{1,}\w{2,}.*UN\s{1,}(\S.*)$', memo_text)
            if match:
                return match.group(1)
        elif (title_text in ["OVERBOOKING TO SA", "OVERBOOKING", "OVERBOOKING FROM SA", "OVERBOOKING FROM CA"]) and memo_text != "?":
            match = re.search(r'(?<=TRF)\s{1,}\w{2,}\s{1,}(\S.*)$', memo_text)
            if match:
                return match.group(1)
        return memo_text

    def write_hierarchy(self):
        xml_content = self.device.dump_hierarchy()
        with open("output2.xml", "w") as f:
            f.write(xml_content)    
        print("UI hierarchy saved to hierarchy.xml")

    def _authenticate(self):
        try:
            time.sleep(5)
            if self.device.app_current()['activity'] == 'some':
                self.device.press('back')

            self.__watcher_check_popup()
            self.is_authenticated = False
            if not self.__wait_for_exists(activity=self.AUTHENTICATE_ACTIVITY):
                raise TimeoutError(f"Condition not met within 30 seconds. activity='{self.AUTHENTICATE_ACTIVITY}'")

            password_field = self.__wait_for_exists(xpath='//android.widget.EditText[@text="Enter user ID"]', timeout=30)
            password_field.click()

            self.device.shell(f'input text {self.pin}')
            time.sleep(2)

            login_button = self.__wait_for_exists(xpath='//android.widget.Button[@text="Login"]')
            login_button.click()
            self.navigate_to_transactions_history()
        except TimeoutError as e:
            current_app = self.device.app_current().get('package')
            current_activity = self.device.app_current().get('activity')
                
            if current_app == self.CIMB_BANKING and current_activity == self.UPDATE_AVAILABLE_ACTIVITY:
                while self.device.app_current().get('activity') != self.AUTHENTICATE_ACTIVITY:
                    self.device.press('back')
                    time.sleep(2)

                return self._authenticate()
            else:
                print(e)
                self.__handle_error(e)
        except Exception as e:
            print(e)
            self.__handle_error(e)

    def __wait_for_exists(self, xpath: str = None, timeout: int = 5, app_package: str = None, activity: str = None):
        for attempt in range(timeout):
            if xpath and self.device.xpath(xpath).exists:
                return self.device.xpath(xpath)
            if app_package and self.device.app_current().get('package') == app_package:
                return True
            if activity and self.device.app_current().get('activity') == activity:
                return True
            
            time.sleep(1)

        raise TimeoutError(f"Condition not met within {timeout} seconds. xpath={xpath}, app_package={app_package}, activity={activity}")

    def __handle_error(self, error: Exception):
        print(f"An error occurred: {error}")
        print(traceback.format_exc())

        self.is_paused = True

        while self.device.app_current().get('activity') != self.HOME_ACTIVITY:
            self.device.press("back")
            time.sleep(1)

        self.is_paused = False

def main():
    device_id = "100.79.114.17:5556"
    pin = "Ningsih221kr"
    
    try:
        cimb_automation = CIMBBankingAutomation(device_id, pin)
        cimb_automation.connect()
        # cimb_automation.navigate_to_transactions_history()
        cimb_automation.batch_pulling_task()
        # cimb_automation.write_hierarchy()
    except Exception as e:
        print(f"Unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
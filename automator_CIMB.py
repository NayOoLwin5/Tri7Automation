import os
import random
import re
import subprocess
import time
import traceback
import dotenv
import requests
import uiautomator2 as u2
from datetime import datetime, timedelta, time as datetime_time
from pathlib import Path
from typing import List, Optional, Tuple

import difflib
import inflection
from pytz import timezone
from celery.app.control import Control, Inspect
from celery.exceptions import Ignore
from icecream import ic
from redis_om import Field, JsonModel, Migrator, NotFoundError, get_redis_connection
from automations.tasks import app
from uiautomator2 import UiObjectNotFoundError, XPathElementNotFoundError, HTTPTimeoutError


dotenv.load_dotenv()

BACKEND_ENDPOINT = os.getenv('BACKEND_ENDPOINT', 'https://staging-api.justmat.pro/api')
MINIMUM_PAUSE_TIME = int(os.getenv('MINIMUM_PAUSE_TIME', 20))
MAXIMUM_PAUSE_TIME = int(os.getenv('MAXIMUM_PAUSE_TIME', 45))
MINIMUM_LIFETIME = int(os.getenv('MINIMUM_LIFETIME', 10 * 60))
MAXIMUM_LIFETIME = int(os.getenv('MAXIMUM_LIFETIME', 12 * 60))
COLLECT_DURATION = int(os.getenv('COLLECT_DURATION', 80))

TZ = timezone('Asia/Jakarta')

PACKAGE_NAME = 'id.co.cimbniaga.mobile.android'
AUTHENTICATE_ACTIVITY = '.uat.modules.login.view.LoginActivity'
HOME_ACTIVITY = '.uat.modules.main.presenter.MainActivity'
MY_ACCOUNT_ACTIVITY = '.uat.modules.myaccount.view.myaccountv2.presentation.ui.MyAccountActivity'
TRANSACTIONS_ACTIVITY = '.uat.modules.myaccount.view.detailv2.casa.presentation.ui.DetailAccountCasaActivity'
UPDATE_AVAILABLE_ACTIVITY = 'com.google.android.finsky.playcoreacquisition.PlayCoreAcquisitionActivity'

redis_connection = get_redis_connection(
    host="broker", port=6379, decode_responses=True
)

def test_redis_connection():
    try:
        redis_connection.ping()
        print("Successfully connected to Redis")
        return True
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        return False

if __name__ == "__main__":
    if not test_redis_connection():
        print("Exiting due to Redis connection failure")
        # sys.exit(1)


def truncate_database() -> None:
    try:
        redis_connection.flushdb()
    except Exception as e:
        print(f"Error truncating database: {e}")
        traceback.print_exc()


# truncate_database()


class TransactionRecord(JsonModel):
    transaction_date: str = Field(index=True)
    transaction_account_id: int = Field(index=True)
    transactions: List[str]

    class Meta:
        database = redis_connection


class TransactionChangeTracker:
    def __init__(self, task_name, account_id) -> None:
        try:
            self.TASK_NAME = task_name
            self.ACCOUNT_ID = account_id
            self.current_transaction_date: str = self.get_current_transaction_date()
        except Exception as e:
            print(f"Error initializing TransactionChangeTracker: {e}")
            traceback.print_exc()

    def get_current_transaction_date(self) -> str:
        try:
            return datetime.now(TZ).strftime("%Y-%m-%d")
            # return datetime(2024, 10, 16, tzinfo=TZ).strftime("%Y-%m-%d")
        except Exception as e:
            print(f"Error getting current transaction date: {e}")
            traceback.print_exc()
            return ""

    def fetch_existing_transactions(self) -> List[str]:
        try:
            transaction_record: Optional[TransactionRecord] = TransactionRecord.find(
                # TransactionRecord.transaction_date == self.current_transaction_date
                (TransactionRecord.transaction_date == self.current_transaction_date) &
                (TransactionRecord.transaction_account_id == self.ACCOUNT_ID)
            ).first()
            
            if transaction_record:
                return transaction_record.transactions
        except NotFoundError:
            return []
        except Exception as e:
            print(f"Error fetching existing transactions: {e}")
            traceback.print_exc()
            return []
        return []

    def store_new_transactions(self, added_transactions: List[str]) -> Optional[str]:
        try:
            try:
                transaction_record: Optional[TransactionRecord] = TransactionRecord.find(
                    # TransactionRecord.transaction_date == self.current_transaction_date
                    (TransactionRecord.transaction_date == self.current_transaction_date) &
                    (TransactionRecord.transaction_account_id == self.ACCOUNT_ID)
                ).first()
            except NotFoundError:
                transaction_record = None

            if transaction_record:
                transaction_record.transactions.extend(added_transactions)
            else:
                transaction_record = TransactionRecord(
                    transaction_date=self.current_transaction_date,
                    transaction_account_id=self.ACCOUNT_ID,
                    transactions=added_transactions,
                )

            transaction_record.save()
            return transaction_record.key()
        except Exception as e:
            print(f"Error storing new transactions: {e}")
            traceback.print_exc()
            return None

    def compare_transaction_lists(
        self, old_transaction_list: List[str], new_transaction_list: List[str]
    ) -> Tuple[List[str], List[str]]:
        try:
            diff = difflib.ndiff(old_transaction_list, new_transaction_list)
            changes = [
                line
                for line in diff
                if line.startswith("+ ") or line.startswith("- ")
            ]

            added_transactions = [
                line[2:] for line in changes if line.startswith("+ ")
            ]
            removed_transactions = [
                line[2:] for line in changes if line.startswith("- ")
            ]

            return added_transactions, removed_transactions
        except Exception as e:
            print(f"Error comparing transaction lists: {e}")
            traceback.print_exc()
            return [], []

    def process_transaction_round(self, transaction_list: List[str]) -> None:
        try:
            
            transaction_list = [transaction for transaction in transaction_list if transaction.split(" | ")[0] == self.current_transaction_date]
            
            existing_transactions: List[str] = self.fetch_existing_transactions()
            current_transactions: List[str] = transaction_list

            added_transactions, _ = self.compare_transaction_lists(
                existing_transactions, current_transactions
            )

            if added_transactions:
                self.store_new_transactions(added_transactions)
        except Exception as e:
            print(f"Error processing transaction round: {e}")
            traceback.print_exc()

    def transform_transactions(self) -> List[dict]:
        try:
            transactions: List[str] = self.fetch_existing_transactions()
            now = datetime.now(TZ)

            transformed_transactions = []
            for transaction in transactions:
                transaction_parts = transaction.split(" | ")

                transaction_date = transaction_parts[0]
                transaction_remark_group = transaction_parts[1].split('--')
                transaction_channel = transaction_remark_group[0].strip().upper()
                clean_transaction_account_name = transaction_remark_group[1].strip().upper()
                transaction_remark = transaction_remark_group[2].strip().upper()
                transaction_code = transaction_remark_group[3].strip().upper()
                transaction_amount = transaction_parts[3]
                transaction_balance = '0.00'
                transaction_type = transaction_parts[2]

                transaction_date_object = datetime.strptime(transaction_date, "%Y-%m-%d").date()
                current_date = now.date()

                if transaction_date_object != current_date:
                    continue

                print({
                    'account_id': inflection.dasherize(self.TASK_NAME.split('.')[0]).upper(),
                    'tnx_account_name': clean_transaction_account_name,
                    'tnx_amount': transaction_amount,
                    'tnx_balance': transaction_balance,
                    'tnx_channel': transaction_channel,
                    'tnx_code': transaction_code,
                    'tnx_date': transaction_date,
                    'tnx_remark': transaction_remark,
                    'tnx_type': transaction_type
                })
                transformed_transactions.append({
                    'account_id': inflection.dasherize(self.TASK_NAME.split('.')[0]).upper(),
                    'tnx_account_name': clean_transaction_account_name,
                    'tnx_amount': transaction_amount,
                    'tnx_balance': transaction_balance,
                    'tnx_channel': transaction_channel,
                    'tnx_code': transaction_code,
                    'tnx_date': transaction_date,
                    'tnx_remark': transaction_remark,
                    'tnx_type': transaction_type
                })

            return transformed_transactions

        except Exception as e:
            print(f"Error transforming transactions: {e}")
            traceback.print_exc()
            return []

try:
    Migrator().run()
except Exception as e:
    print(f"Error running Migrator: {e}")
    traceback.print_exc()

class RetrieveTransactionHistory:
    def __init__(self, task, serial: str, pin: str, account_id: str):
        self.SERIAL = serial
        self.PIN = pin
        self.ACCOUNT_ID = account_id

        self.DEVICE = u2.connect(self.SERIAL)

        self.PREVIOUS_ACTIVITY = None
        self.CURRENT_ACTIVITY = None
        
        self.TASK = task.request
        self.TASK_ID = self.TASK.id
        self.TASK_NAME = task.name
        self.TASK_ARGS = self.TASK.args
        self.TASK_KWARGS = self.TASK.kwargs
        self.TASK_QUEUE = self.TASK.delivery_info.get('routing_key', 'Unknown')
        
        self.IS_TASK_COMPLETE = False

        print(f"TASK => {self.TASK}")
        print(f"TASK_ID => {self.TASK_ID}")
        print(f"TASK_NAME => {self.TASK_NAME}")
        print(f"TASK_ARGS => {self.TASK_ARGS}")
        print(f"TASK_KWARGS => {self.TASK_KWARGS}")
        print(f"TASK_QUEUE => {self.TASK_QUEUE}")
        
        self.IS_PAUSED = False
        self.IS_AUTHENTICATED = False
        self.IS_SINGLE_PAGE_RECYCLER_VIEW = False

        print(f"Initialized RetrieveTransactionHistory for account number {self.ACCOUNT_ID}")
        inspector = Inspect()

        current = self.TASK
        active_tasks = inspector.active()
        reserved_tasks = inspector.reserved()
        scheduled_tasks = inspector.scheduled()

        active = active_tasks.get(self.TASK_QUEUE, []) if active_tasks else []
        pending = reserved_tasks.get(self.TASK_QUEUE, []) if reserved_tasks else []
        scheduled = scheduled_tasks.get(self.TASK_QUEUE, []) if scheduled_tasks else []

        return current, active, pending, scheduled

    # def __purge_tasks_in_queue(self, queue_name):
    #     try:
    #         # Inspect the workers to get the reserved tasks
    #         i = app.control.inspect()

    #         # Purge reserved tasks
    #         reserved_tasks = i.reserved()
    #         if reserved_tasks:
    #             for worker, tasks in reserved_tasks.items():
    #                 for task in tasks:
    #                     if task['delivery_info']['routing_key'] == queue_name:
    #                         app.control.revoke(task['id'], terminate=True)
    #                         print(f"Revoked reserved task {task['id']} from queue {queue_name}.")

    #         # Purge pending tasks from the specified queue
    #         with app.connection_or_acquire() as conn:
    #             queue = app.amqp.queues.get(queue_name)
                
    #             # Ensure the queue is bound to a channel
    #             queue = queue.bind(conn.default_channel)

    #             num_tasks_purged = queue.purge()
    #             print(f"Purged {num_tasks_purged} pending tasks from queue {queue_name}.")

    #     except Exception as e:
    #         self.__handle_error(e)

    def __handle_error(self, error: Exception):
        print(f"An error occurred: {error}")
        print(traceback.format_exc())

        self.IS_PAUSED = True

        while self.DEVICE.app_current().get('activity') != HOME_ACTIVITY:
            self.DEVICE.press("back")

            time.sleep(1)

        self.IS_PAUSED = False

    def __wait_for_exists(self, xpath: str = None, timeout: int = 5, app_package: str = None, activity: str = None):
        for attempt in range(timeout):
            if xpath and self.DEVICE.xpath(xpath).exists:
                return self.DEVICE.xpath(xpath)
            if app_package and self.DEVICE.app_current().get('package') == app_package:
                return True
            if activity and self.DEVICE.app_current().get('activity') == activity:
                return True
            
            time.sleep(1)

        raise TimeoutError(f"Condition not met within {timeout} seconds. xpath={xpath}, app_package={app_package}, activity={activity}")

    def __initialize(self):
        # Package name and the target activity
        target_activity = HOME_ACTIVITY

        # Check if the app is running
        is_running = self.DEVICE.app_wait(PACKAGE_NAME, front=False)

        if not is_running:
            # If the app is not running, start it
            print(f"Starting app {PACKAGE_NAME}")
            self.DEVICE.app_start(PACKAGE_NAME)
        else:
            # If the app is running, check if it's in the foreground
            current_app = self.DEVICE.app_current()
            if current_app['package'] != PACKAGE_NAME:
                # If the app is not in the foreground, restart it
                print(f"Restarting app {PACKAGE_NAME}, Foreground detected.")
                self.DEVICE.app_start(PACKAGE_NAME)
            else:
                # If the app is in the foreground, check the current activity
                current_activity = current_app['activity']
                if current_activity != target_activity:
                    self.IS_PAUSED = True

                    # Press back button until the target activity is reached
                    while current_activity != target_activity:  
                        if current_activity == target_activity:
                            break

                        print(f"Press back button because the app is not in target activity.")
                        self.DEVICE.press("back")
                        time.sleep(1)  # Give it a moment to change activity
                        current_app = self.DEVICE.app_current()
                        current_activity = current_app['activity']
                    
                    self.IS_PAUSED = False

    def __finalize(self):
        print("Stopping the app...")
        self.DEVICE.watcher.stop()
        self.DEVICE.app_stop(PACKAGE_NAME)

    def __check_popup(self):
        # List of text messages to check for popups
        popup_texts = [
            'Knock, knock, are you there?',
            'No internet connection',
            'Your session has expired'
        ]

        for text in popup_texts:
            popup_element = self.DEVICE.xpath(f'//android.widget.TextView[@text="{text}"]')
            
            # Check if the popup text exists on the screen
            if popup_element.exists:

                # Click on the OK button if present
                yes_button = self.DEVICE.xpath('//android.widget.Button[@text="Yes, I’m still here"]')
                login_again_button = self.DEVICE.xpath('//android.widget.Button[@text="Login"]')
                ok_button = self.DEVICE.xpath('//android.widget.Button[@text="OK"]')
                retry_button = self.DEVICE.xpath('//android.widget.Button[@text="Retry"]')

                if yes_button.exists:
                    yes_button.click()
                elif login_again_button.exists:
                    login_again_button.click()
                elif ok_button.exists:
                    ok_button.click()
                elif retry_button.exists:
                    retry_button.click()
                else:
                    self.IS_TASK_COMPLETE = True
                    return

                time.sleep(3)  # Wait for any animations or transitions

        # # List of specific activities to check for unexpected states
        # unexpected_activities = [
        #     'com.google.android.finsky.playcoreacquisition.PlayCoreAcquisitionActivity',
        # ]

        # current_activity = self.DEVICE.app_current().get('activity', '')
        # for activity in unexpected_activities:
        #     if current_activity == activity:
        #         # Handle the PlayCoreAcquisitionActivity specifically
        #         if activity == 'com.google.android.finsky.playcoreacquisition.PlayCoreAcquisitionActivity':
        #             self.DEVICE.xpath('//android.widget.ScrollView/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]'
        #                             '/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.FrameLayout[1]').click()
        #         else:
        #             self.IS_TASK_COMPLETE = True
        #             return

        #         time.sleep(3)  # Wait for any animations or transitions

        return

    def __watcher_check_popup(self):
        self.DEVICE.watcher("knock_knock_watcher").when('//android.widget.TextView[@text="Knock, knock, are you there?"]').when('//android.widget.Button[@text="Yes, I’m still here"]').click()
        self.DEVICE.watcher("no_internet_watcher").when('//android.widget.TextView[@text="No internet connection"]').when('//android.widget.Button[@text="Retry"]').click()
        self.DEVICE.watcher("unable_to_request_watcher").when('//android.widget.TextView[@text="Unable to process this request"]').when('//android.widget.Button[@text="Retry"]').click()
        self.DEVICE.watcher("session_expired_watcher").when('//android.widget.TextView[@text="Your session has expired"]').when('//android.widget.Button[@text="Login"]').click()
        self.DEVICE.watcher("generic_ok_watcher").when('//android.widget.TextView[@text="No internet connection"]').when('//android.widget.Button[@text="OK"]').click()
        self.DEVICE.watcher("login_cancel_watcher").when('//android.widget.TextView[@text="You will be asked to login the next time you open OCTO Mobile."]').when('//android.widget.Button[@text="Cancel"]').click()
        self.DEVICE.watcher.start()
        time.sleep(1)

    def _authenticate(self):
        try:
            time.sleep(5)
            if self.DEVICE.app_current()['activity'] == 'some':
                self.DEVICE.press('back')

            self.IS_AUTHENTICATED = False
            if self.__wait_for_exists(activity=AUTHENTICATE_ACTIVITY):
                password_field = self.__wait_for_exists(xpath='//android.widget.EditText[@text="Enter user ID"]', timeout=30)
                password_field.click()
    
                self.DEVICE.shell(f'input text {self.PIN}')
                time.sleep(2)
    
                login_button = self.__wait_for_exists(xpath='//android.widget.Button[@text="Login"]')
                login_button.click()
                self.IS_AUTHENTICATED = True
            
        except TimeoutError as e:
            current_app = self.DEVICE.app_current().get('package')
            current_activity = self.DEVICE.app_current().get('activity')
            
            if current_app == PACKAGE_NAME and current_activity == UPDATE_AVAILABLE_ACTIVITY:
                while self.DEVICE.app_current().get('activity') != AUTHENTICATE_ACTIVITY:
                    self.DEVICE.press('back')

                    time.sleep(2)

                return self._authenticate()
            else:
                print(e)
                self.__handle_error(e)
        except Exception as e:
            print(e)
            self.__handle_error(e)

    def _navigate(self):
        try:
            time.sleep(2)
            current_activity = self.DEVICE.app_current().get('activity')
            if current_activity != HOME_ACTIVITY:
                self.__initialize()
            
            idr_text = self.DEVICE.xpath('//android.widget.TextView[@resource-id="id.co.cimbniaga.mobile.android:id/tv_amount"]')
            if not idr_text.exists:
                login_button = self.DEVICE.xpath('//android.widget.TextView[@text="Login or Create Account Now"]')
                if login_button.exists:
                    login_button.click()
                    self._authenticate()
            else:
                print("In initial state, authenticated.")
                idr_text.click()
                self.IS_AUTHENTICATED = True

            # TODO: monitoring after go to transction history page should be purge all pending and served task.
            # self.__purge_tasks_in_queue(self.TASK_QUEUE)
        except Exception as e:
            print(e)
            self.__handle_error(e)

    def _collect(self):
        try:
            if not self.__wait_for_exists(activity=TRANSACTIONS_ACTIVITY):
                return

            recent_text = "Recent"
            recent_field = self.DEVICE.xpath(f'//android.widget.TextView[@text="{recent_text}"]')
            
            while not recent_field.exists:
                print("Waiting for 'Recent' text field to appear...")
                time.sleep(1)
                recent_field = self.DEVICE.xpath(f'//android.widget.TextView[@text="{recent_text}"]')

            print("'Recent' text field appeared. Starting batch pulling...")

            segment_line_class = "android.widget.LinearLayout"
            recycler_view_id = "id.co.cimbniaga.mobile.android:id/rv_transaction"
            transaction_title_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_title"
            transaction_value_id = "id.co.cimbniaga.mobile.android:id/tv_transaction_value"

            printed_items = set()

            tracker = TransactionChangeTracker(self.TASK_NAME, self.ACCOUNT_ID)
            existing_transactions = tracker.fetch_existing_transactions()
            is_first_run = len(existing_transactions) == 0
            current_date = tracker.get_current_transaction_date()

            max_transactions = float('inf') if is_first_run else 15
            transaction_count = 0
            final_transactions = []
            start_time = time.time()

            while True:
                recycler_view = self.DEVICE(resourceId=recycler_view_id)
                transaction_items = recycler_view.child(className="android.view.ViewGroup")

                previous_transactions = [t.info for t in recycler_view.child(resourceId=transaction_title_id)]
                
                last_transaction = recycler_view.child(resourceId=transaction_title_id)[-1].info['bounds']
                start_x = (last_transaction['left'] + last_transaction['right']) // 2
                
                recent_bounds = recent_field.info['bounds']
                end_x = (recent_bounds['left'] + recent_bounds['right']) // 2
                end_y = recent_bounds['top'] + 70

                segment_lines = self.DEVICE(className=segment_line_class)
                if segment_lines:
                    last_segment_line = segment_lines[-1].info['bounds']
                    start_y = last_segment_line['bottom']
                else:
                    start_y = 1400
                
                max_iterations = 3
                is_last_swipe = False
                is_not_current_date = False

                if len(printed_items) > 0:
                    self.DEVICE.swipe(start_x, start_y, end_x, end_y, duration=0.5)
                    time.sleep(1)
                
                    current_transactions = [t.info for t in self.DEVICE(resourceId=transaction_title_id)]
                    is_last_swipe = previous_transactions == current_transactions
                    max_iterations = 4 if is_last_swipe else max_iterations

                transactions = []
                for i, item in enumerate(transaction_items):
                    if i >= max_iterations:
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
                        transaction_date = datetime.strptime(transaction[1], '%d %b %Y %H:%M').strftime('%Y-%m-%d')
                        if transaction_date != current_date:
                            print(f"Transaction date {transaction_date} is not current date. Breaking loop.")
                            is_not_current_date = True
                            break
                            

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

                        final_transactions.append(result)
                        transaction_count += 1
                        if transaction_count >= max_transactions:
                            print(f"Reached maximum of {max_transactions} transactions. Exiting batch pulling.")
                            return
                    except (IndexError, ValueError) as e:
                        print(f"Error processing transaction: {transaction}. Error: {str(e)}")

                if is_not_current_date:
                    break

                if is_last_swipe:
                    print("No more transactions found. Exiting batch pulling.")
                    break

                try:
                    self.DEVICE(resourceId=transaction_title_id).wait(timeout=7)
                except Exception:
                    break

            if final_transactions:
                tracker = TransactionChangeTracker(self.TASK_NAME, self.ACCOUNT_ID)
                tracker.process_transaction_round(final_transactions)

                transformed_transactions = tracker.transform_transactions()
                print(f'transformed_transactions => {transformed_transactions}')

                
                endpoint = f'{BACKEND_ENDPOINT}/transactions'
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                data = {
                    'transactions': transformed_transactions
                }
                print(f'Endpoint => {endpoint}')
                print(f'Headers => {headers}')
                print(f'Data => {data}')
                response = requests.post(endpoint, headers=headers, json=data)
                print(f'Response => {response}')
                
                if response.status_code == 200:
                    print("Insert transaction request was successful.")
                    print("Response:", response.json())
                else:
                    print(f"Request failed with status code {response.status_code}.")
                    print("Response:", response.text)

                endpoint = f'{BACKEND_ENDPOINT}/accounts/{self.ACCOUNT_ID}/update-balance'
                headers = {
                    # "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiZWViZGVkYTMxNGRmNDQ3OTZiZmM5ZTg5ZWFiNGMyMWNlM2VlZjAyMWEyNmM3MTVlZWU0YWNhZWY0OWRjNDk4OTJkNzc2OWNkMjRhMGM1N2EiLCJpYXQiOjE3MDc0NDk3NzYuMzk2MzQ5LCJuYmYiOjE3MDc0NDk3NzYuMzk2MzUzLCJleHAiOjIwMjMwNjg5NzYuMzg3MjgzLCJzdWIiOiIyMDMxNjYiLCJzY29wZXMiOltdfQ.ktIFoRYgblN7ZRRgHYdpBbff3JdKjjGixWQgANIDDGuDJf5T7e0vrUcZp7wFUhYdFarAIavdNzBNJtMJDjaHDM5UB3wSlHQjH15sprXbnOeq6PCvTHBCEpS8V4JNsfy1UjUNNo_IFta9CMNcweDM8OxJ3PbJHNX8xZyFBwQ7AHNGtDaChV4-C1tODcuClLOJXZetixsNFqm2lP9tiSG6E5iBHzR0ko2RtnMK4jkUzXu2eaOPAeUDWNuow-gd-yZBJPZ44IQ4BPq1JcZxbgaKq3uLRzJwnNmkwvF1zOHIEVELINIoydthldR-aNcxIG8Q3AKM3LH4tVqmaUxJ5iPV30dab6vsKFwsYHZr9NGD0fuPA8--X9yVfJR4Yc08CULPYh1aTqkVtlo_1DXihCl8Gj9mQ6Poago0NBFdd-j6FY8qxVFDBmxmLzPcIhnKgR_IxXYabFGRm89dYcHIJD7cLuhNVgIZar94qBe66dLjrfZxgIp04uTYwLfNwX5GrtXVGfWz2CdFcaz1FwIoTf6B2L7M_Oasg7XjiZdKTRUjHI8bLIEx4FHVLZLO4iHWp79S9mHxc4fTbz3aFD-z50iGmnkkoEj99pYwnJ2X6NkTklaqkBrXAC3_x6vOXvB1r_V4jMr5G9DPoKiiG4fUFLBNrey_hN2R6T3lew_UZLp7X7E",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                data = {
                    'balance': '0.00'
                }
                print(f'Endpoint => {endpoint}')
                print(f'Headers => {headers}')
                print(f'Data => {data}')
                response = requests.put(endpoint, headers=headers, json=data)
                print(f'Response => {response}')

                # return # raise SystemExit(0)
            print("All transactions collected. Navigating back to home...")
            time.sleep(5)
            current_app = self.DEVICE.app_current()
            current_activity = current_app['activity']
            if current_activity != HOME_ACTIVITY:
                self.IS_PAUSED = True

                # Press back button until the target activity is reached
                while current_activity != HOME_ACTIVITY:
                    if current_activity == HOME_ACTIVITY:
                        break

                    print(f"Press back button because the app is not in target activity.")
                    self.DEVICE.press("back")
                    time.sleep(1)
                    current_app = self.DEVICE.app_current()
                    current_activity = current_app['activity']

                self.IS_PAUSED = False
            
            print("Navigated back to home.")
            elapsed_time = time.time() - start_time
            cycle_delay_time = max(COLLECT_DURATION - elapsed_time, 0)
            cycle_pause_time = random.randint(MINIMUM_PAUSE_TIME, MAXIMUM_PAUSE_TIME)

            countdown = cycle_delay_time + cycle_pause_time
            print(f"Sleep for {countdown} seconds...", end="\r")
            while countdown > 0:
                if countdown < 4:
                    print(f"Collecting transactions in {countdown} seconds...", end="\r")
                time.sleep(1)
                countdown -= 1
        except Exception as e:
            print(e)
            self.__handle_error(e)


    def _process_memo(self, title_text, memo_text):
        if title_text == "OVERBOOKING TO KWIK" and memo_text != "?":
            match = re.search(r'\S+\s{1,}\S+\s{1,}(\S.*)$', memo_text)
            if match:
                return match.group(1)
        elif title_text == "REMITTANCE CR - BIFAST" and memo_text != "?":
            match = re.search(r'BFS\s{1,}\w{2,}.*UN\s{1,}(\S.*)$', memo_text)
            if match:
                return match.group(1)
        elif (title_text in ["OVERBOOKING TO SA", "OVERBOOKING", "OVERBOOKING FROM SA", "OVERBOOKING FROM CA", "OVERBOOKING CR"]) and memo_text != "?":
            match = re.search(r'(?<=TRF)\s{1,}\w{2,}\s{1,}(\S.*)$', memo_text)
            if match:
                return match.group(1)
        return memo_text

    def _play_core_acquisition(self):
        try:
            self.__wait_for_exists(activity=UPDATE_AVAILABLE_ACTIVITY)

            update_available = self.__wait_for_exists(xpath='//android.widget.ScrollView/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.FrameLayout[1]', timeout=10)
            update_available.click()
        except Exception as e:
            print(e)
            self.__handle_error(e)
        try:
            account_balance = self.__wait_for_exists(xpath='//android.widget.TextView[@text="IDR"]/following-sibling::*[1]')

            return round(float(account_balance.info['text'].replace(',', '')), 2)
        except Exception as e:
            print(e)
            self.__handle_error(e)

            return 0.0

    def run(self):
        try:
            activity_mapping = {
                AUTHENTICATE_ACTIVITY: self._authenticate,
                HOME_ACTIVITY: self._navigate,
                TRANSACTIONS_ACTIVITY: self._collect,
                UPDATE_AVAILABLE_ACTIVITY: self._play_core_acquisition,
            }
            activity_mapping_name = {
                AUTHENTICATE_ACTIVITY: '_authenticate',
                HOME_ACTIVITY: '_navigate',
                TRANSACTIONS_ACTIVITY: '_collect',
                UPDATE_AVAILABLE_ACTIVITY: '_play_core_acquisition',
            }
            random_session_lifetime = random.randint(MINIMUM_LIFETIME, MAXIMUM_LIFETIME)
            session_expiry = datetime.now(TZ) + timedelta(seconds=random_session_lifetime)

            self.__watcher_check_popup()
            self.__initialize()
            time.sleep(1)
           
            while datetime.now(TZ) < session_expiry:
                if self.IS_TASK_COMPLETE:
                    return True

                self.CURRENT_ACTIVITY = self.DEVICE.app_current().get('activity')

                if self.IS_PAUSED or self.CURRENT_ACTIVITY not in activity_mapping:
                    time.sleep(1)

                    continue

                handler = activity_mapping.get(self.CURRENT_ACTIVITY)

                if handler:
                    print(f"Current activity: {activity_mapping_name[self.CURRENT_ACTIVITY]}")
                    handler()
                else:
                    print("No handler for the current activity")

                self.PREVIOUS_ACTIVITY = self.CURRENT_ACTIVITY

                time.sleep(1)

            print("Session expired...")
            print("Session expired. Restarting task...")
            app.send_task(self.TASK_NAME, args=[self.SERIAL, self.PIN, self.ACCOUNT_ID], queue=self.TASK_QUEUE, countdown=3)
            
        except (TimeoutError, HTTPTimeoutError, UiObjectNotFoundError, XPathElementNotFoundError) as e:
            print(f"Timeout occurred: {e}")
            self.__handle_error(e)
            # Re-queue the task in Celery
            app.send_task(
                self.TASK_NAME,
                args=[self.SERIAL, self.PIN, self.ACCOUNT_ID],
                queue=self.TASK_QUEUE,
                countdown=3,
            )
        except Exception as e:
            print(e)
            self.__handle_error(e)
        finally:
            pass


class Automator():
    @classmethod
    def get_statements(cls, task, serial: str, pin: str, account_id: str):
        try:
            automator = RetrieveTransactionHistory(task, serial, pin, account_id)
            result = automator.run()

            if result:
                return
        except Exception as e:
            raise Ignore()
        
    @classmethod
    def import_statements(cls, task, device_id: str = None, queue_name: str = "default"):
        pass

    @classmethod
    def fund_transfer(cls, task, device_id: str = None, queue_name: str = "default"):
        pass

    @classmethod
    def login(cls, serial: str, password: str):
        from backbone.utils.response import Response
        import uiautomator2 as u2
        import time

        # Connect to device
        try:
            device = u2.connect(serial)
        except u2.exceptions.DeviceConnectionError as e:
            print(str(e))
            return Response._failure(
                code="",
                message=str(f"Failed to connect to device with serial '{serial}': {str(e)}"),
                status_code=500,
            )
        except Exception as e:
            print(str(e))
            return Response._failure(
                code="",
                message=str(f"An unexpected error occurred while trying to connect to device with serial '{serial}': {str(e)}"),
                status_code=500,
            )

        # Find and interact with the password field
        try:
            password_field = device.xpath('//android.widget.EditText[@text="Password"]')
            if password_field.exists:
                password_field.click()
                time.sleep(1)
                device.shell(f'input text {password}')
            else:
                raise Exception("Password field not found")
        except Exception as e:
            print(str(e))
            return Response._failure(
                code="",
                message=str(f"Failed to detect password field on device '{serial}': {str(e)}"),
                status_code=500,
            )

        # Find and click the login button
        try:
            login_button = device.xpath('//android.widget.Button[@text="Log In"]')
            if login_button.exists:
                login_button.click()
            else:
                raise Exception("Login button not found")
        except Exception as e:
            print(str(e))
            return Response._failure(
                code="",
                message=str(f"Failed to detect login button on device '{serial}': {str(e)}"),
                status_code=500,
            )
        
        return True

# if __name__ == "__main__":
#     # import sys
    
#     # if len(sys.argv) != 5:
#     #     print("Usage: python automator_BCA.py <task> <serial> <pin> <account_id>")
#     #     sys.exit(1)
 
    
    # test_redis_connection()
    # Automator.get_statements("some_task", "100.79.114.17:5556", "Ningsih221kr", "763817830600")
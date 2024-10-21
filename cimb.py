import uiautomator2 as u2
from uiautomator2 import UiObjectNotFoundError, ConnectError
import time
cimb_banking = "id.co.cimbniaga.mobile.android"

def event_driven_task(device_id):
    try:
        d = u2.connect(device_id)
    except ConnectError as e:
        print(f"Failed to connect to device: {e}")
        return

    try:
        print("App started.")
        time.sleep(5)
    except UiObjectNotFoundError:
        print(f"Failed to start {cimb_banking}. App might not be installed.")
        return

    # placeholder_text = "My Account"
    # text_field = d.xpath(f'//android.widget.TextView[@text="{placeholder_text}"]')
    
    # while True:
    #     if text_field.exists:
    #         print("Text field found. Clicking...")
    #         try:
    #             text_field.click()
    #             print("Clicked on the text field.")
    #             time.sleep(10)
                
    savings_text = "SAVINGS & CURRENT"
    savings_field = d.xpath(f'//android.widget.TextView[@text="{savings_text}"]')
                
    while True:
        if savings_field.exists:
            print("SAVINGS & CURRENT text found. Clicking below...")
            try:
                bounds = savings_field.info['bounds']
                x = (bounds['left'] + bounds['right']) // 2
                y = bounds['bottom'] + 100
                d.click(x, y)
                print("Clicked somewhat below the SAVINGS & CURRENT text.")
                time.sleep(10)
                break
            except UiObjectNotFoundError:
                print("Failed to interact with SAVINGS & CURRENT text. Retrying...")
        else:
            print("SAVINGS & CURRENT text not found. Retrying...")
            time.sleep(1)
            savings_field = d.xpath(f'//android.widget.TextView[@text="{savings_text}"]')
                

    try:
        d.app_stop(cimb_banking)
    except Exception as e:
        print(f"Error stopping the app: {e}")

def batch_pulling_task(device_id):
    try:
        d = u2.connect(device_id)
    except ConnectError as e:
        print(f"Failed to connect to device: {e}")
        return

    recent_text = "Recent"
    recent_field = d.xpath(f'//android.widget.TextView[@text="{recent_text}"]')

    while not recent_field.exists:
        print("Waiting for 'Recent' text field to appear...")
        time.sleep(1)
        recent_field = d.xpath(f'//android.widget.TextView[@text="{recent_text}"]')

    print("'Recent' text field appeared. Starting batch pulling...")

    transaction_title_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_title"
    transaction_date_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_date"
    memo1_id = "id.co.cimbniaga.mobile.android:id/tv_memo1"
    memo2_id = "id.co.cimbniaga.mobile.android:id/tv_memo2"
    transaction_value_id = "id.co.cimbniaga.mobile.android:id/tv_transaction_value"
    segment_line_class = "android.widget.LinearLayout"

    printed_items = set()

    while True:
        try:
            transaction_titles = d(resourceId=transaction_title_id)
            transaction_dates = d(resourceId=transaction_date_id)
            memos1 = d(resourceId=memo1_id)
            memos2 = d(resourceId=memo2_id)
            transaction_values = d(resourceId=transaction_value_id)

            transactions = []
            for title, date, memo1, memo2, value in zip(transaction_titles, transaction_dates, memos1, memos2, transaction_values):
                if title.get_text() == "ATM BERSAMA CHARGES":
                    transaction = (
                        title.get_text(),
                        date.get_text(),
                        value.get_text()
                    )
                else:
                    transaction = (
                        title.get_text(),
                        date.get_text(),
                        memo1.get_text(),
                        memo2.get_text(),
                        value.get_text()
                    )
                if transaction not in printed_items:
                    transactions.append(transaction)
                    printed_items.add(transaction)
            
            for transaction in transactions:
                if len(transaction) == 3:
                    formatted_date = time.strftime('%Y-%m-%d', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    formatted_datetime = time.strftime('%Y-%m-%dT%H:%M:%S+0700', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    title_text = transaction[0]
                    amount_text = transaction[2]
                    transaction_type = "DB" if "-" in amount_text else "CR" if "+" in amount_text else "?"
                    amount_numeric = float(amount_text.replace("IDR", "").replace("-", "").replace("+", "").replace(",", "").strip())
                    result = f"{formatted_date} | {title_text} -- {amount_text} -- {formatted_datetime}| {transaction_type} | {amount_numeric} | {str(float(0))}"
                else:
                    formatted_date = time.strftime('%Y-%m-%d', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    formatted_datetime = time.strftime('%Y-%m-%dT%H:%M:%S+0700', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    tnx_id_text = transaction[2]
                    title_text = transaction[0]
                    remark_text = transaction[3]
                    amount_text = transaction[4]
                    transaction_type = "DB" if "-" in amount_text else "CR" if "+" in amount_text else "?"
                    amount_numeric = float(amount_text.replace("IDR", "").replace("-", "").replace("+", "").replace(",", "").strip())
                    result = f"{formatted_date} | {title_text} -- {tnx_id_text} -- {remark_text} -- {amount_text} -- {formatted_datetime}| {transaction_type} | {amount_numeric} | {str(float(0))}"
                    # result = " | ".join([
                    # formatted_date,
                    # " -- ".join([
                    #     title_text,
                    #     remark_text,
                    #     amount_text,
                    #     formatted_datetime,
                    #     transaction_type
                    # ]),
                    # str(amount_numeric * 1000),  # Convert float to string
                    # str(float(0))  # Convert to string
                    # ]
                    # )
                print(result)

            previous_transactions = [t.info for t in d(resourceId=transaction_title_id)]

            # Get the bounds of the last transaction item
            last_transaction = d(resourceId=transaction_title_id).info['bounds']
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
            d.swipe(start_x, start_y, end_x, end_y, duration=5)

            try:
                d(resourceId=transaction_title_id).wait(timeout=10)
            except UiObjectNotFoundError:
                break

            current_transactions = [t.info for t in d(resourceId=transaction_title_id)]
            if previous_transactions == current_transactions:
                print("No more transactions found. Exiting batch pulling.")
                break

        except UiObjectNotFoundError:
            print("No more transactions found or failed to scroll. Exiting batch pulling.")
            break

device_id = "100.79.114.17:5555"
try:
    batch_pulling_task(device_id)
except Exception as e:
    print(f"Unexpected error occurred: {e}")
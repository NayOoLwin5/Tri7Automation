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

    segment_line_class = "android.widget.LinearLayout"
    recycler_view_id = "id.co.cimbniaga.mobile.android:id/rv_transaction"
    transaction_title_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_title"
    transaction_date_id = "id.co.cimbniaga.mobile.android:id/tv_remarks_date"
    transaction_value_id = "id.co.cimbniaga.mobile.android:id/tv_transaction_value"
    memo1_id = "id.co.cimbniaga.mobile.android:id/tv_memo1"
    memo2_id = "id.co.cimbniaga.mobile.android:id/tv_memo2"
    memo3_id = "id.co.cimbniaga.mobile.android:id/tv_memo3"


    printed_items = set()

    while True:
        try:
            recycler_view = d(resourceId=recycler_view_id)
            transaction_items = recycler_view.child(className="android.view.ViewGroup")

            transactions = []
            for i, item in enumerate(transaction_items):
                if i >= 3:
                    break
                visible_texts = item.child(className="android.widget.TextView")
                
                transaction = tuple(text.get_text() for text in visible_texts if text.get_text() != '00' and 'IDR' not in text.get_text())
                
                transaction_value = item.child(resourceId=transaction_value_id).get_text()
                if any('IDR' in text.get_text() for text in visible_texts):
                    transaction += (transaction_value,)
                if transaction and transaction not in printed_items:
                    transactions.append(transaction)
                    printed_items.add(transaction)
            
            for transaction in transactions:
                try:
                    formatted_date = time.strftime('%Y-%m-%d', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    formatted_datetime = time.strftime('%Y-%m-%dT%H:%M:%S+0700', time.strptime(transaction[1], '%d %b %Y %H:%M'))
                    title_text = transaction[0]
                    memo1_text = "?" if len(transaction) <= 3 or transaction[2] == "-" else transaction[2]
                    memo2_text = "?" if len(transaction) <= 4 or transaction[3] == "-" else transaction[3]
                    memo3_text = "?" if len(transaction) <= 5 or transaction[4] == "-" else transaction[4]
                    amount_text = transaction[-1]
                    transaction_type = "DB" if "-" in amount_text else "CR" if "+" in amount_text else "?"
                    amount_numeric = float(amount_text.replace("IDR", "").replace("-", "").replace("+", "").replace(",", "").strip())
                    memos = [memo1_text, memo2_text, memo3_text]
                    non_question_memos = [memo for memo in memos if memo != "?"]
                    question_memos = [memo for memo in memos if memo == "?"]
                    all_memos = " -- ".join(non_question_memos + question_memos)
                    result = f"{formatted_date} | {title_text} -- {all_memos} -- {amount_text} -- {formatted_datetime} | {transaction_type} | {amount_numeric} | {str(float(0))}"
                    print(result)
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
            d.swipe(start_x, start_y, end_x, end_y, duration=5)

            try:
                d(resourceId=transaction_title_id).wait(timeout=10)
            except UiObjectNotFoundError:
                break

            current_transactions = [t.info for t in d(resourceId=transaction_title_id)]
            if previous_transactions == current_transactions:
                print("No more transactions found. Exiting batch pulling.")
                break

        except UiObjectNotFoundError as e:
            print(f"No more transactions found or failed to scroll. Error: {str(e)}. Exiting batch pulling.")
            break

def write_hierarchy(device_id):
    xml_content = device_id.dump_hierarchy()
    with open("output.xml", "w") as f:
        f.write(xml_content)    
    print("UI hierarchy saved to hierarchy.xml")

device_id = "100.79.114.17:5556"
try:
    batch_pulling_task(device_id)
    # d = u2.connect(device_id)
    # write_hierarchy(d)
except Exception as e:
    print(f"Unexpected error occurred: {e}")
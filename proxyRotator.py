import requests
import threading
import queue
from collections import defaultdict

q = queue.Queue()
valid_proxies = []
proxy_request_count = defaultdict(int)
max_requests_per_ip = 10

sites_to_check = ["https://books.toscrape.com/"]
url_to_check_valid_proxy = "https://jsonplaceholder.typicode.com/todos/1"

with open("proxies_list.txt", "r") as f:
    proxies = f.read().split("\n")
    for p in proxies:
        q.put(p)

def check_proxies():
    while not q.empty():
        proxy = q.get()
        try:
            res = requests.get(url_to_check_valid_proxy, proxies={"http": proxy, "https": proxy})
            if res.status_code == 200:
                valid_proxies.append(proxy)
        except requests.exceptions.RequestException as e:
            continue

threads = []
for _ in range(10):
    t = threading.Thread(target=check_proxies)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

def rotateProxy():
    try:
        if not valid_proxies:
            raise Exception("No valid proxies available")

        while sites_to_check:
            proxy = valid_proxies.pop(0)
            if proxy_request_count[proxy] >= max_requests_per_ip:
                valid_proxies.append(proxy)
                continue

            site = sites_to_check.pop(0)
            try:
                res = requests.get(site, proxies={"http": proxy, "https": proxy})
                if res.status_code == 200:
                    print(f"Successfully accessed {site} with proxy {proxy}")
                else:
                    print(f"Failed to access {site} with proxy {proxy}")
                proxy_request_count[proxy] += 1
            except requests.exceptions.RequestException as e:
                print(f"Error accessing {site} with proxy {proxy}: {e}")
            finally:
                valid_proxies.append(proxy)
                sites_to_check.append(site)

    except Exception as e:
        print(f"Error in rotateProxy: {e}")

rotateProxy()

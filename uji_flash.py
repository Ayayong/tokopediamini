import json, urllib.request, urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

FLASH_ID = 15
URL = f"http://127.0.0.1:8002/flash-sales/{FLASH_ID}/reserve"

def beli(_):
    req = urllib.request.Request(
        URL, data=json.dumps({"quantity": 1}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code

with ThreadPoolExecutor(30) as ex:      # 30 permintaan bersamaan
    hasil = Counter(ex.map(beli, range(30)))
print(hasil)
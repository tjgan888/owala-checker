"""Owala FreeSip Tritan 740ml 進貨查詢小程序

追蹤網站：誠品線上、Finders、JKS、道研
用法:
  python owala_stock.py                查一次，有補貨就通知
  python owala_stock.py --watch 10     每 10 分鐘查一次
  python owala_stock.py --test-notify  送一則測試通知，確認推播/email 設定

通知設定（環境變數，沒設的管道就略過）:
  NTFY_TOPIC          ntfy 頻道名稱（手機 ntfy App 訂閱同一個名稱）
  GMAIL_USER          寄件 Gmail 帳號
  GMAIL_APP_PASSWORD  Gmail 應用程式密碼
  MAIL_TO             收件信箱（沒設就寄給 GMAIL_USER）
"""
import argparse
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

TW = timezone(timedelta(hours=8))

COLORS = ["極夜黑", "柔光粉", "蝶豆紫", "冰河白", "奶茶", "泡泡藍"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
STATE_FILE = Path(__file__).with_name("last_state.json")


def fetch(url):
    # 誠品會擋 Python 的連線，改用 curl（Windows 是 curl.exe）
    curl = shutil.which("curl.exe") or "curl"
    out = subprocess.run([curl, "-s", "-L", "--fail", "-A", UA, url],
                         capture_output=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"讀取失敗 (curl {out.returncode})")
    return out.stdout.decode("utf-8")


def match_color(text):
    return next((c for c in COLORS if c in text), None)


# ---------- 各網站 ----------
# 每個函式回傳 {顏色: (是否有貨, 庫存數或None, 商品網址)}

def eslite():
    api = ("https://athena.eslite.com/api/v2/search?q=owala%20tritan"
           "&final_price=0,&publishDate=0&sort=_weight_+desc&size=40&start=0&exp=c")
    result = {}
    for h in json.loads(fetch(api))["hits"]["hit"]:
        f = h["fields"]
        if f.get("brand") != "Owala" or "tritan" not in f["name"].lower() or "740" not in f["name"]:
            continue
        color = match_color(f["name"])
        if not color:
            continue
        # 搜尋結果的庫存可能有延遲，再查商品頁 API 取即時庫存
        p = json.loads(fetch(f"https://athena.eslite.com/api/v1/products/{h['id']}"))
        stock = int(p.get("stock") or 0)
        result[color] = (stock > 0, stock, f"https://www.eslite.com/product/{h['id']}")
    return result


def shopline(url):
    html = fetch(url)
    m = re.search(r"app\.value\('product', JSON\.parse\('(.*?)'\)\);", html, re.S)
    if not m:
        raise RuntimeError("找不到商品資料（網頁結構可能改了）")
    raw = m.group(1).encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
    p = json.loads(raw)
    unlimited = p.get("unlimited_quantity") or p.get("out_of_stock_orderable")
    result = {}
    for v in p.get("variations", []):
        color = match_color(" ".join(v.get("fields_translations", {}).get("zh-hant", [])))
        if color:
            qty = int(v.get("quantity") or 0)
            result[color] = (bool(unlimited) or qty > 0, qty, url)
    return result


def cyberbiz(url):
    p = json.loads(fetch(url + ".json"))
    result = {}
    for v in p["variants"]:
        color = match_color(v.get("title", ""))
        if color:
            result[color] = (bool(v.get("available")), v.get("inventory_quantity"), url)
    return result


SITES = {
    "誠品": eslite,
    "Finders": lambda: shopline("https://www.finders.com.tw/products/owala-freesip-tritan-25oz"),
    "JKS": lambda: shopline("https://www.jksshop.co/products/owala-freesip-tritan-740ml"),
    "道研": lambda: cyberbiz("https://www.daoyen27.com/products/1210002800174"),
}


# ---------- 主流程 ----------

def notify(title, msg):
    """送到所有有設定的管道：ntfy 推播、Gmail、Windows 通知。"""
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        try:
            body = {"topic": topic, "title": title, "message": msg, "priority": 4, "tags": ["tada"]}
            req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=20)
            print("已送出 ntfy 推播")
        except Exception as e:
            print(f"ntfy 推播失敗：{e}")

    user, password = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if user and password:
        try:
            mail = EmailMessage()
            mail["Subject"], mail["From"] = title, user
            mail["To"] = os.environ.get("MAIL_TO") or user
            mail.set_content(msg)
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(user, password.replace(" ", ""))
                s.send_message(mail)
            print("已寄出 email")
        except Exception as e:
            print(f"email 寄送失敗：{e}")

    if os.name == "nt":
        windows_toast(title, msg)


def windows_toast(title, msg):
    title, msg = title.replace("'", "''"), msg.replace("'", "''")
    ps = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode('{title}')) > $null
$x.Item(1).AppendChild($t.CreateTextNode('{msg}')) > $null
$app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)


def pad(text, width=8):
    # 中文字在終端機佔兩格
    return text + " " * (width - sum(2 if ord(ch) > 0x2E80 else 1 for ch in text))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_once():
    old = load_state()
    new = {}
    restocked = []
    print(f"\n=== Owala Tritan 740ml 庫存  {datetime.now(TW):%Y-%m-%d %H:%M:%S} ===")
    print("        " + "".join(f"{c:　<5}" for c in COLORS))
    links = []
    for site, func in SITES.items():
        try:
            data = func()
        except Exception as e:
            print(f"{pad(site)}查詢失敗：{e}")
            continue
        cells = []
        for c in COLORS:
            if c not in data:
                cells.append("－沒賣　")
                continue
            ok, qty, url = data[c]
            key = f"{site}|{c}"
            new[key] = ok
            if ok:
                cells.append(f"✔{qty}" if qty else "✔有貨")
                links.append(f"  {site} {c}: {url}")
                if old.get(key) is not True:  # 上次缺貨（或第一次看到就有貨）
                    restocked.append((f"{site} {c}", url))
            else:
                cells.append("✘缺貨")
        print(pad(site) + "".join(f"{s:　<5}" for s in cells))
    if links:
        print("\n有貨連結：")
        print("\n".join(dict.fromkeys(links)))
    if restocked:
        print("\n★ 補貨了：" + "、".join(name for name, _ in restocked))
        msg = "\n\n".join(f"{name}\n{url}" for name, url in restocked)
        notify("Owala 補貨了！" + "、".join(name for name, _ in restocked), msg)
    STATE_FILE.write_text(json.dumps({**old, **new}, ensure_ascii=False, indent=1, sort_keys=True),
                          encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Owala Tritan 740ml 進貨查詢")
    ap.add_argument("--watch", type=float, metavar="分鐘", help="每隔幾分鐘自動檢查一次")
    ap.add_argument("--test-notify", action="store_true", help="送一則測試通知")
    args = ap.parse_args()

    if args.test_notify:
        notify("Owala 通知測試", "收到這則訊息代表補貨通知設定成功！")
        return
    if not args.watch:
        run_once()
        return
    print(f"開始監控，每 {args.watch:g} 分鐘檢查一次（Ctrl+C 結束）")
    while True:
        run_once()
        time.sleep(args.watch * 60)


if __name__ == "__main__":
    main()

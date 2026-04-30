import requests
from bs4 import BeautifulSoup
import json
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import time
import re

SENDER_EMAIL    = os.environ.get("SENDER_EMAIL")
APP_PASSWORD    = os.environ.get("APP_PASSWORD")
RECEIVER_EMAIL  = os.environ.get("RECEIVER_EMAIL")
THREADS_TOKEN   = os.environ.get("THREADS_TOKEN")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID")

SITES = [
    {"name": "筑紫野ローンテニスクラブ", "url": "https://chikushinotennis.web.fc2.com/", "encoding": "utf-8"},
    {"name": "筑紫野市テニス協会", "url": "http://chikushino-tennis.com/", "encoding": "shift_jis"},
]

HISTORY_FILE = "tennis_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def fetch_page(url, encoding):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = encoding
        return response.text
    except Exception as e:
        print(f"  エラー: {e}")
        return None

def parse_chikushinotennis(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    date_pattern = re.compile(r"20\d{2}\.\d{1,2}\.\d{1,2}")
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if date_pattern.match(line):
            date_str = line
            content = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j] and not date_pattern.match(lines[j]):
                    content = lines[j]
                    break
            if content:
                items.append({
                    "date": date_str,
                    "content": content,
                    "site": "筑紫野ローンテニスクラブ",
                    "url": "https://chikushinotennis.web.fc2.com/",
                    "id": hashlib.md5(f"{date_str}_{content}".encode()).hexdigest()[:8]
                })
        i += 1
    return items[:15]

def parse_chikushino_city(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    date_pattern = re.compile(r"\d{1,2}/\d{1,2}/20\d{2}")
    dl_elements = soup.find_all("dl")
    for dl in dl_elements:
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            date_str = dt.get_text(strip=True)
            if date_pattern.search(date_str):
                content = dd.get_text(strip=True)
                link = dd.find("a")
                url = link["href"] if link and link.get("href") else ""
                items.append({
                    "date": date_str,
                    "content": content[:80],
                    "site": "筑紫野市テニス協会",
                    "url": url,
                    "id": hashlib.md5(f"{date_str}_{content}".encode()).hexdigest()[:8]
                })
    return items[:15]

def send_email(new_items):
    try:
        body = "【筑紫野エリア テニス新着情報】\n\n"
        for item in new_items:
            body += f"日付: {item['date']}\n"
            body += f"内容: {item['content']}\n"
            body += f"サイト: {item['site']}\n"
            body += f"URL: {item['url']}\n"
            body += "-" * 30 + "\n"
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL
        msg["Subject"] = f"テニス新着情報 {datetime.now().strftime('%Y/%m/%d')}"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print("  メール送信成功！")
    except Exception as e:
        print(f"  メール送信失敗: {e}")

def post_threads_summary(new_items):
    try:
        today = datetime.now().strftime("%Y年%m月%d日")
        text = f"テニス新着情報まとめ {today}\n\n"
        for item in new_items:
            text += f"{item['date']}\n"
            text += f"{item['content']}\n"
            text += f"({item['site']})\n\n"
        text += "#筑紫野テニス #福岡テニス #草トーナメント"
        if len(text) > 500:
            text = text[:490] + "..."
        res1 = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            params={"media_type": "TEXT", "text": text, "access_token": THREADS_TOKEN}
        )
        data1 = res1.json()
        container_id = data1.get("id")
        if not container_id:
            print(f"  Threads投稿失敗: {data1}")
            return
        time.sleep(2)
        requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
            params={"creation_id": container_id, "access_token": THREADS_TOKEN}
        )
        print("  Threads投稿成功！（まとめ1投稿）")
    except Exception as e:
        print(f"  Threads投稿失敗: {e}")

def main():
    print("=" * 50)
    print(f"実行時刻: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    print("=" * 50)

    history = load_history()
    new_items_all = []

    for site in SITES:
        print(f"\n{site['name']} をチェック中...")
        html = fetch_page(site["url"], site["encoding"])
        if not html:
            continue

        if "chikushinotennis" in site["url"]:
            items = parse_chikushinotennis(html)
        else:
            items = parse_chikushino_city(html)

        print(f"  取得件数: {len(items)}件")
        site_key = site["name"]
        known_ids = set(history.get(site_key, []))
        new_items = [item for item in items if item["id"] not in known_ids]

        if new_items:
            print(f"  新着情報: {len(new_items)}件")
            for item in new_items:
                print(f"    [{item['date']}] {item['content']}")
                new_items_all.append(item)
            history[site_key] = list(known_ids | {item["id"] for item in items})
        else:
            print("  新着なし")

    print("\n" + "=" * 50)
    if new_items_all:
        print(f"{len(new_items_all)}件の新着情報を発見！")
        send_email(new_items_all)
        post_threads_summary(new_items_all)
    else:
        print("新着情報はありませんでした")

    save_history(history)
    print("完了！")

if __name__ == "__main__":
    main()
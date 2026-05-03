import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import re

# ===== 設定 =====
SITES = {
    "筑紫野ローンテニスクラブ": "https://chikushinotennis.web.fc2.com/",
}

DATA_FILE = "tennis_data.json"
HTML_FILE = "index.html"

# メール設定（環境変数から取得）
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Threads設定（環境変数から取得）
THREADS_TOKEN = os.getenv("THREADS_TOKEN")
THREADS_USER_ID = os.getenv("THREADS_USER_ID")

# ===== 関数群 =====

def scrape_site(url):
    """
    Claude版：広範囲力技抽出
    サイト内の全テキスト要素から情報を網羅的に収集
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=10, headers=headers)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 全テキスト要素を網羅的に取得（力技）
        all_content = []
        for tag in soup.find_all(['div', 'table', 'p', 'h1', 'h2', 'h3', 'h4', 'li', 'td', 'tr', 'span']):
            text = tag.get_text(separator=' ', strip=True)
            if text and len(text) > 10:
                all_content.append(text)
        
        print(f"   ✓ {len(all_content)}件のコンテンツブロックを取得")
        return all_content
        
    except Exception as e:
        print(f"❌ 収集エラー: {e}")
        return []

def classify_event(text):
    """イベントを分類（ジュニア/一般）"""
    junior_keywords = ["ジュニア", "Jr", "jr", "小学生", "中学生", "高校生", 
                       "こども", "子ども", "キッズ", "ファーストステップ", 
                       "ゴーゴーゴー", "ぽよよん", "チビ", "強化"]
    
    text_lower = text.lower()
    for keyword in junior_keywords:
        if keyword.lower() in text_lower:
            return "junior"
    return "adult"

def extract_events_from_content(content_list, url, source_name):
    """コンテンツからイベント情報を抽出"""
    events = []
    
    # 大会・カップキーワード
    event_keywords = ["大会", "カップ", "レッスン", "イベント", "試合", "結果", "募集"]
    
    # 日付パターン（複数対応）
    date_patterns = [
        r'(\d{1,2})/(\d{1,2})\(([月火水木金土日])\)',  # 5/17(日)
        r'(\d{1,2})/(\d{1,2})',                        # 5/17
        r'(\d{1,2})月(\d{1,2})日',                    # 5月17日
    ]
    
    for text in content_list:
        # イベント関連のキーワードが含まれているか
        has_event_keyword = any(keyword in text for keyword in event_keywords)
        
        if not has_event_keyword:
            continue
        
        # 日付を探す
        date_found = None
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) >= 2:
                    date_found = f"{match.group(1)}/{match.group(2)}"
                break
        
        if date_found:
            # タイトルを抽出
            title = text.split('\n')[0][:100].strip()
            
            # 除外キーワード
            ignore_keywords = ["休講", "定休日", "スクール生"]
            if any(k in title for k in ignore_keywords):
                continue
            
            event = {
                "date": date_found,
                "title": title,
                "url": url,
                "category": classify_event(text)
            }
            
            events.append(event)
    
    return events

def extract_all_events(content, url, site_name):
    """全データからイベント情報を抽出"""
    all_events = {"junior": [], "adult": []}
    
    events = extract_events_from_content(content, url, site_name)
    
    print(f"📊 {site_name}: {len(events)}件のイベントを抽出")
    
    # カテゴリ別に分類
    for event in events:
        category = event["category"]
        all_events[category].append(event)
    
    # 重複削除
    all_events["junior"] = remove_duplicates(all_events["junior"])
    all_events["adult"] = remove_duplicates(all_events["adult"])
    
    print(f"🎾 ジュニア: {len(all_events['junior'])}件")
    print(f"🏆 一般: {len(all_events['adult'])}件")
    
    return all_events

def remove_duplicates(events):
    """重複イベントを削除"""
    seen = set()
    unique_events = []
    
    for event in events:
        key = (event["date"], event["title"][:30])
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    return unique_events

def generate_event_cards(events):
    """イベントカードのHTML生成（オレンジデザイン）"""
    if not events:
        return '<div style="text-align:center; padding:40px; color:#999;">現在、新しい情報はありません。</div>'
    
    html = ""
    for ev in events:
        link_label = "試合結果を見る" if any(x in ev['title'] for x in ["結果", "予選", "本戦"]) else "大会要項を見る"
        link_style = "btn-result" if "結果" in ev['title'] else "btn-info"
        
        html += f"""
        <div class="event-card">
            <div class="event-date">{ev['date']}</div>
            <div class="event-details">
                <div class="event-title">{ev['title']}</div>
                <div class="event-actions">
                    <a href="{ev['url']}" class="btn {link_style}" target="_blank">{link_label}</a>
                </div>
            </div>
        </div>
        """
    
    return html

def update_html(events):
    """HTMLファイルを更新（オレンジデザイン）"""
    update_time = datetime.now().strftime('%Y/%m/%d %H:%M')
    junior_html = generate_event_cards(events.get("junior", []))
    adult_html = generate_event_cards(events.get("adult", []))
    
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>福岡テニス速報</title>
    <meta name="description" content="福岡・筑紫野エリアのテニス大会情報を自動収集・配信">
    <style>
        :root {{
            --main: #FF8C00;
            --sub: #FFD700;
            --bg: #FFFBF5;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
            background: var(--bg);
            margin: 0;
            color: #333;
            padding-bottom: 80px;
        }}
        
        .header {{
            background: linear-gradient(135deg, var(--main), var(--sub));
            color: white;
            padding: 25px 15px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            font-size: 24px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        
        .header p {{
            font-size: 13px;
            opacity: 0.95;
        }}
        
        .tabs {{
            display: flex;
            background: white;
            position: sticky;
            top: 0;
            border-bottom: 2px solid #EEE;
            z-index: 100;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }}
        
        .tab {{
            flex: 1;
            padding: 15px;
            text-align: center;
            font-weight: bold;
            color: #777;
            cursor: pointer;
            transition: all 0.3s;
            border-bottom: 4px solid transparent;
        }}
        
        .tab.active {{
            color: var(--main);
            border-bottom-color: var(--main);
            background: #FFF9F0;
        }}
        
        .tab:hover {{
            background: #FFF9F0;
        }}
        
        .section {{
            display: none;
            padding: 15px;
            max-width: 600px;
            margin: 0 auto;
        }}
        
        .section.active {{
            display: block;
            animation: fadeIn 0.3s;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .event-card {{
            display: flex;
            background: white;
            margin-bottom: 12px;
            border-radius: 8px;
            border: 1px solid #FFE0B2;
            overflow: hidden;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            transition: transform 0.2s;
        }}
        
        .event-card:active {{
            transform: scale(0.98);
        }}
        
        .event-date {{
            background: #FFF3E0;
            color: var(--main);
            width: 70px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            border-right: 1px solid #FFE0B2;
            font-size: 14px;
        }}
        
        .event-details {{
            flex: 1;
            padding: 15px;
        }}
        
        .event-title {{
            font-size: 15px;
            font-weight: bold;
            margin-bottom: 10px;
            line-height: 1.4;
            color: #222;
        }}
        
        .event-actions {{
            margin-top: 8px;
        }}
        
        .btn {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 4px;
            text-decoration: none;
            font-size: 12px;
            font-weight: bold;
            transition: all 0.2s;
        }}
        
        .btn-info {{
            border: 1px solid var(--main);
            color: var(--main);
            background: white;
        }}
        
        .btn-info:hover {{
            background: var(--main);
            color: white;
        }}
        
        .btn-result {{
            background: var(--main);
            color: white;
            border: 1px solid var(--main);
        }}
        
        .btn-result:hover {{
            background: #E07B00;
        }}
        
        .footer {{
            position: fixed;
            bottom: 0;
            width: 100%;
            background: white;
            padding: 15px;
            text-align: center;
            font-size: 11px;
            border-top: 1px solid #EEE;
            color: #999;
        }}
        
        @media (min-width: 768px) {{
            .header h1 {{
                font-size: 32px;
            }}
            .section {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎾 福岡テニス速報</h1>
        <p>筑紫野エリアの大会・結果を自動収集</p>
    </div>
    
    <div class="tabs">
        <div class="tab active" onclick="switchTab('jr')">🎾 ジュニア</div>
        <div class="tab" onclick="switchTab('ad')">🏆 一般・社会人</div>
    </div>
    
    <div id="jr" class="section active">
        {junior_html}
    </div>
    
    <div id="ad" class="section">
        {adult_html}
    </div>
    
    <div class="footer">
        更新: {update_time} | テニスをにぎやかに！ 🎾
    </div>
    
    <script>
        function switchTab(id) {{
            document.querySelectorAll('.tab').forEach((t, i) => {{
                t.classList.toggle('active', (i == 0 && id == 'jr') || (i == 1 && id == 'ad'));
            }});
            
            document.querySelectorAll('.section').forEach(s => {{
                s.classList.toggle('active', s.id == id);
            }});
            
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
    </script>
</body>
</html>"""
    
    try:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ HTMLファイル更新完了")
    except Exception as e:
        print(f"❌ HTMLファイル保存エラー: {e}")

def send_email(subject, body):
    """メール送信"""
    if not all([SENDER_EMAIL, APP_PASSWORD, RECEIVER_EMAIL]):
        print("⚠️ メール設定が不完全です（環境変数未設定）")
        return
    
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        
        print("✅ メール送信成功")
    except Exception as e:
        print(f"❌ メール送信エラー: {e}")

def post_to_threads(text):
    """Threadsに投稿"""
    if not all([THREADS_TOKEN, THREADS_USER_ID]):
        print("⚠️ Threads設定が不完全です（環境変数未設定）")
        return
    
    try:
        url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
        params = {
            "media_type": "TEXT",
            "text": text,
            "access_token": THREADS_TOKEN
        }
        response = requests.post(url, params=params)
        response_data = response.json()
        container_id = response_data.get("id")
        
        if not container_id:
            print(f"❌ Threadsコンテナ作成失敗")
            return
        
        time.sleep(2)
        
        publish_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish"
        publish_params = {
            "creation_id": container_id,
            "access_token": THREADS_TOKEN
        }
        publish_response = requests.post(publish_url, params=publish_params)
        
        if publish_response.status_code == 200:
            print("✅ Threads投稿成功")
        else:
            print(f"❌ Threads投稿エラー")
            
    except Exception as e:
        print(f"❌ Threads投稿エラー: {e}")

def main():
    print("=" * 70)
    print("🎾 福岡テニス情報収集システム v4.2 ULTIMATE")
    print("=" * 70)
    
    all_events = {"junior": [], "adult": []}
    
    for site_name, url in SITES.items():
        print(f"\n📡 {site_name} をチェック中...")
        content = scrape_site(url)
        
        if content:
            events = extract_all_events(content, url, site_name)
            all_events["junior"].extend(events["junior"])
            all_events["adult"].extend(events["adult"])
    
    # HTML更新
    print(f"\n🌐 HTMLファイルを更新中...")
    update_html(all_events)
    
    # 通知送信
    total_events = len(all_events["junior"]) + len(all_events["adult"])
    
    if total_events > 0:
        print(f"\n📢 通知を送信中... (合計{total_events}件)")
        
        email_body = f"""🎾 福岡テニス速報

ジュニア: {len(all_events['junior'])}件
一般: {len(all_events['adult'])}件

詳細: https://hiro-ito1.github.io/tennis-info/
"""
        send_email("【福岡テニス速報】最新情報", email_body)
        
        threads_text = f"""🎾 福岡テニス速報

ジュニア: {len(all_events['junior'])}件
一般: {len(all_events['adult'])}件

https://hiro-ito1.github.io/tennis-info/"""
        
        post_to_threads(threads_text)
    else:
        print(f"\n📭 イベント情報が取得できませんでした")
    
    print("\n" + "=" * 70)
    print("✅ 処理完了！")
    print("=" * 70)

if __name__ == "__main__":
    main()

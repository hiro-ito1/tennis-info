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

def load_previous_data():
    """前回のデータを読み込み"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    """データを保存"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def scrape_site(url):
    """サイトから情報を取得"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=10, headers=headers)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
        
        # すべてのテキスト要素を取得
        all_content = []
        for tag in soup.find_all(['div', 'table', 'p', 'h1', 'h2', 'h3', 'h4', 'li']):
            text = tag.get_text(separator=' ', strip=True)
            if text and len(text) > 10:
                all_content.append(text)
        
        return {
            "url": url,
            "content": all_content,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"❌ エラー: {url} - {e}")
        return None

def classify_event(text):
    """イベントを分類（ジュニア/一般）"""
    junior_keywords = ["ジュニア", "Jr", "jr", "小学生", "中学生", "高校生", 
                       "こども", "子ども", "キッズ", "ファーストステップ", 
                       "ゴーゴーゴー", "ぽよよん", "チビ"]
    
    text_lower = text.lower()
    for keyword in junior_keywords:
        if keyword.lower() in text_lower:
            return "junior"
    return "adult"

def extract_events_from_content(content_list, url, source_name):
    """コンテンツからイベント情報を抽出"""
    events = []
    
    # 大会・カップキーワード
    event_keywords = ["大会", "カップ", "レッスン", "イベント", "試合"]
    
    # 日付パターン
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
            # タイトルを抽出（最初の100文字、または改行まで）
            title = text.split('\n')[0][:100]
            
            # 詳細説明（200文字まで）
            description = text[:200]
            
            event = {
                "date": date_found,
                "title": title.strip(),
                "description": description.strip(),
                "url": url,
                "source": source_name,
                "category": classify_event(text)
            }
            
            events.append(event)
    
    return events

def extract_all_events(data):
    """全データからイベント情報を抽出"""
    all_events = {"junior": [], "adult": []}
    
    for site_name, site_data in data.items():
        if not site_data:
            continue
        
        content = site_data.get("content", [])
        url = site_data.get("url", "")
        
        events = extract_events_from_content(content, url, site_name)
        
        print(f"📊 {site_name}: {len(events)}件のイベントを抽出")
        
        # カテゴリ別に分類
        for event in events:
            category = event["category"]
            all_events[category].append(event)
    
    # 重複削除（同じタイトルのイベントは1つだけ残す）
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
        # タイトルと日付の組み合わせで重複判定
        key = (event["date"], event["title"][:30])
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    return unique_events

def generate_event_cards(events, max_items=10):
    """イベントカードのHTMLを生成"""
    if not events:
        return """
                <div class="card">
                    <div class="card-title">現在、登録されている情報はありません</div>
                    <div class="card-meta">情報が更新され次第、自動で表示されます</div>
                </div>
"""
    
    cards = ""
    for event in events[:max_items]:
        date_display = event.get('date', '日付未定')
        title = event.get('title', '詳細情報')
        
        # タイトルをクリーンアップ
        if len(title) > 80:
            title = title[:80] + "..."
        
        source = event.get('source', '情報元不明')
        url = event.get('url', '#')
        description = event.get('description', '')[:100]
        
        cards += f"""
                <div class="card">
                    <div class="card-date">{date_display}</div>
                    <div class="card-title">{title}</div>
                    <div class="card-meta">{source}</div>
                    <a href="{url}" class="card-link" target="_blank">詳細を見る →</a>
                </div>
"""
    
    return cards

def update_html(events):
    """HTMLファイルを更新"""
    
    junior_cards = generate_event_cards(events.get("junior", []), max_items=15)
    adult_cards = generate_event_cards(events.get("adult", []), max_items=15)
    
    update_time = datetime.now().strftime('%Y年%m月%d日 %H:%M')
    
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>福岡テニス情報 - 最新大会情報</title>
    <meta name="description" content="福岡・筑紫野エリアのテニス大会情報を自動収集・配信">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 15px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            font-size: 22px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        
        .header .subtitle {{
            font-size: 13px;
            opacity: 0.9;
        }}
        
        .tabs {{
            display: flex;
            background: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .tab {{
            flex: 1;
            padding: 15px;
            text-align: center;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.3s;
            font-size: 15px;
            background: white;
        }}
        
        .tab.active {{
            border-bottom-color: #667eea;
            color: #667eea;
            font-weight: bold;
            background: #f8f9ff;
        }}
        
        .tab:hover {{
            background: #f8f9ff;
        }}
        
        .content {{
            padding: 15px;
            max-width: 600px;
            margin: 0 auto;
            padding-bottom: 60px;
        }}
        
        .section {{
            display: none;
        }}
        
        .section.active {{
            display: block;
            animation: fadeIn 0.3s;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .category {{
            margin-bottom: 30px;
        }}
        
        .category-title {{
            font-size: 17px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 15px;
            padding-left: 12px;
            border-left: 4px solid #667eea;
        }}
        
        .card {{
            background: white;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: all 0.2s;
            border: 1px solid #f0f0f0;
        }}
        
        .card:active {{
            transform: scale(0.98);
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }}
        
        .card-date {{
            color: #667eea;
            font-weight: bold;
            font-size: 15px;
            margin-bottom: 8px;
        }}
        
        .card-title {{
            font-size: 14px;
            margin-bottom: 8px;
            line-height: 1.5;
            color: #222;
        }}
        
        .card-meta {{
            font-size: 12px;
            color: #666;
            margin-bottom: 8px;
        }}
        
        .card-link {{
            display: inline-block;
            margin-top: 8px;
            color: #667eea;
            text-decoration: none;
            font-size: 13px;
            font-weight: 500;
        }}
        
        .card-link:hover {{
            text-decoration: underline;
        }}
        
        .footer {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 11px;
            background: white;
            border-top: 1px solid #eee;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
        }}
        
        @media (min-width: 768px) {{
            .header h1 {{
                font-size: 28px;
            }}
            .content {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎾 福岡テニス情報</h1>
        <div class="subtitle">筑紫野エリアの最新大会情報</div>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="switchTab('junior')">🎾 ジュニア</div>
        <div class="tab" onclick="switchTab('adult')">🏆 一般</div>
    </div>

    <div class="content">
        <!-- ジュニアセクション -->
        <div id="junior" class="section active">
            <div class="category">
                <div class="category-title">📅 ジュニア大会情報</div>
                {junior_cards}
            </div>
        </div>

        <!-- 一般セクション -->
        <div id="adult" class="section">
            <div class="category">
                <div class="category-title">📅 一般大会情報</div>
                {adult_cards}
            </div>
        </div>
    </div>

    <div class="footer">
        最終更新: {update_time}<br>
        自動更新システム稼働中 🤖
    </div>

    <script>
        function switchTab(tab) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tab).classList.add('active');
            
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
    </script>
</body>
</html>
"""
    
    try:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ HTMLファイル更新完了: {HTML_FILE}")
        print(f"   - ジュニア: {len(events.get('junior', []))}件")
        print(f"   - 一般: {len(events.get('adult', []))}件")
    except Exception as e:
        print(f"❌ HTMLファイル保存エラー: {e}")

def send_email(subject, body):
    """メール送信"""
    if not all([SENDER_EMAIL, APP_PASSWORD, RECEIVER_EMAIL]):
        print("⚠️ メール設定が不完全です（ローカル実行時は正常）")
        return
    
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        
        print("✅ メール送信成功")
    except Exception as e:
        print(f"❌ メール送信エラー: {e}")

def post_to_threads(text):
    """Threadsに投稿"""
    if not all([THREADS_TOKEN, THREADS_USER_ID]):
        print("⚠️ Threads設定が不完全です（ローカル実行時は正常）")
        return
    
    try:
        url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
        params = {
            "media_type": "TEXT",
            "text": text,
            "access_token": THREADS_TOKEN
        }
        response = requests.post(url, params=params)
        container_id = response.json().get("id")
        
        if not container_id:
            print(f"❌ コンテナ作成失敗: {response.text}")
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
            print(f"❌ Threads投稿エラー: {publish_response.text}")
            
    except Exception as e:
        print(f"❌ Threads投稿エラー: {e}")

def main():
    print("=" * 60)
    print("🎾 福岡テニス情報収集システム v3.0")
    print("=" * 60)
    
    previous_data = load_previous_data()
    
    current_data = {}
    new_items = []
    
    for site_name, url in SITES.items():
        print(f"\n📡 {site_name} をチェック中...")
        data = scrape_site(url)
        
        if data:
            current_data[site_name] = data
            print(f"   ✓ {len(data.get('content', []))}件のコンテンツを取得")
            
            # 差分チェック（簡易版）
            if site_name not in previous_data:
                new_items.append(f"【{site_name}】初回取得\n{url}")
                print(f"   🆕 初回データ取得")
    
    save_data(current_data)
    
    print(f"\n📊 イベント情報を抽出中...")
    events = extract_all_events(current_data)
    
    print(f"\n🌐 HTMLファイルを更新中...")
    update_html(events)
    
    if new_items or len(events.get("junior", [])) > 0 or len(events.get("adult", [])) > 0:
        print(f"\n✅ イベント情報を検出")
        
        # メール本文作成
        email_body = f"""福岡テニス情報更新

ジュニア: {len(events.get('junior', []))}件
一般: {len(events.get('adult', []))}件

詳細: https://hiro-ito1.github.io/tennis-info/
"""
        send_email("【福岡テニス情報】更新あり", email_body)
        
        # Threads投稿
        threads_text = f"🎾 福岡テニス情報更新\n\nジュニア: {len(events.get('junior', []))}件\n一般: {len(events.get('adult', []))}件\n\n詳細: https://hiro-ito1.github.io/tennis-info/"
        post_to_threads(threads_text)
    else:
        print(f"\n📭 イベント情報なし")
    
    print("\n" + "=" * 60)
    print("✅ 処理完了！")
    print("=" * 60)
    print(f"\n📱 確認: {os.path.abspath(HTML_FILE)}")
    print(f"   → ダブルクリックしてブラウザで開いてください\n")

if __name__ == "__main__":
    main()
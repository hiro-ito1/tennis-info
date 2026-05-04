import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse, urljoin
import time
import re

# ===== 設定 =====
SITES = {
    "筑紫野ローンテニスクラブ": "https://chikushinotennis.web.fc2.com/",
}

DATA_FILE = "tennis_data.json"
HTML_FILE = "index.html"
BLACKLIST_FILE = "blacklist.txt"

# メール設定（環境変数から取得）
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Threads設定（環境変数から取得）
THREADS_TOKEN = os.getenv("THREADS_TOKEN")
THREADS_USER_ID = os.getenv("THREADS_USER_ID")

# ===== 曜日マップ =====
WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

# ===== NGキーワード（スクレイピング段階で除外）=====
# ★「ファーストステップ」「ぽよよん」はここから削除 → classify_event側でジュニア判定に使用
NG_KEYWORDS = [
    "休講", "定休日", "スクール生",
    "初心者ジュニアレッスン", "爆進テニス",
    "手ぶらでおいでよ", "通常レッスン",
    "ご参加お待ちしております",
    "木曜１８：００", "木曜18:00",
    "今後の予定：",
    "入賞者 今後の予定",
    "先行エントリーができます",
]

# ===== レッスン除外ワード（NGキーワードとの組み合わせで柔軟に判定）=====
LESSON_CONTEXT_KEYWORDS = ["レッスン", "スクール", "練習会", "講習"]


# ===== 関数群 =====

def load_blacklist():
    """blacklist.txtを読み込む（なければ空リスト）"""
    if not os.path.exists(BLACKLIST_FILE):
        return []
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        print(f"📋 ブラックリスト読み込み: {len(lines)}件")
        return lines
    except Exception as e:
        print(f"⚠️ ブラックリスト読み込みエラー: {e}")
        return []


def apply_blacklist(events, blacklist):
    """ブラックリストに一致するイベントを除外"""
    if not blacklist:
        return events
    filtered = []
    for ev in events:
        hit = any(word in ev["title"] for word in blacklist)
        if hit:
            print(f"🚫 ブラックリスト除外: {ev['title'][:40]}")
        else:
            filtered.append(ev)
    return filtered


def is_lesson_only(text):
    """
    「ファーストステップ」「ぽよよん」単体は大会名の可能性がある。
    レッスン文脈のワードと一緒に出てくる場合のみ除外する。
    """
    soft_ng = ["ファーストステップ", "ぽよよん"]
    for word in soft_ng:
        if word in text:
            # レッスン系ワードと同時に含む場合だけ除外
            if any(lw in text for lw in LESSON_CONTEXT_KEYWORDS):
                return True
    return False


def add_weekday(date_str):
    """
    「5/18」→「5/18(月)」に変換する。
    年は現在年を使用。12月に翌年1月分を表示しても対応できるよう考慮。
    """
    try:
        now = datetime.now()
        month, day = map(int, date_str.split("/"))
        year = now.year
        # 現在月より大幅に小さい月（例：現在12月なのに1月）は翌年と判断
        if now.month >= 10 and month <= 3:
            year += 1
        d = date(year, month, day)
        weekday = WEEKDAY_JP[d.weekday()]
        return f"{month}/{day}({weekday})"
    except Exception:
        return date_str  # 変換失敗時はそのまま返す


def is_past_date(date_str):
    """
    現在年より前（2026年1月より前）のデータは除外する。
    「5/18」形式の場合、現在年を基準に判定。
    """
    try:
        now = datetime.now()
        month, day = map(int, date_str.split("/"))
        year = now.year
        if now.month >= 10 and month <= 3:
            year += 1
        target = date(year, month, day)
        cutoff = date(now.year, 1, 1)  # 現在年の1月1日を下限
        return target < cutoff
    except Exception:
        return False  # 判定できない場合は除外しない


def resolve_url(href, base_url):
    """相対URLや//で始まるURLを絶対URLに変換"""
    if not href:
        return base_url
    return urljoin(base_url, href)


def classify_event(text):
    """イベントを分類（ジュニア/一般）"""
    junior_keywords = [
        "ジュニア", "Jr", "jr", "小学生", "中学生", "高校生",
        "こども", "子ども", "キッズ", "ファーストステップ",
        "ゴーゴーゴー", "ぽよよん", "チビ", "強化",
    ]
    text_lower = text.lower()
    for keyword in junior_keywords:
        if keyword.lower() in text_lower:
            return "junior"
    return "adult"


def classify_event_type(title):
    """
    イベントタイプを分類して表示ラベルを返す
    「結果」「優勝」「スコア」→【結果報告】
    それ以外→【大会募集】
    """
    result_keywords = ["結果", "優勝", "スコア", "入賞", "順位", "報告"]
    for kw in result_keywords:
        if kw in title:
            return "result"
    return "entry"


def scrape_site(url):
    """
    サイト内の全テキスト要素＋リンクを収集
    NGキーワードを含むブロックは即時除外
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")

        all_content = []
        for tag in soup.find_all(["div", "table", "p", "h1", "h2", "h3", "h4", "li", "td", "tr", "span"]):
            text = tag.get_text(separator=" ", strip=True)
            if not text or len(text) < 10:
                continue

            # ハードNGキーワード除外
            if any(ng in text for ng in NG_KEYWORDS):
                continue

            # ソフトNG（ファーストステップ・ぽよよん＋レッスン文脈）除外
            if is_lesson_only(text):
                continue

            # リンクを絶対URLに変換（urljoinで完全対応）
            link = url
            a_tag = tag.find("a", href=True)
            if a_tag:
                link = resolve_url(a_tag["href"], url)

            all_content.append({"text": text, "link": link})

        print(f"   ✓ {len(all_content)}件のコンテンツブロックを取得（NG除外後）")
        return all_content

    except Exception as e:
        print(f"❌ 収集エラー: {e}")
        return []


def extract_events_from_content(content_list, default_url, source_name):
    """コンテンツからイベント情報を抽出"""
    events = []

    event_keywords = ["大会", "カップ", "レッスン", "イベント", "試合", "結果", "募集"]

    date_patterns = [
        r"(\d{1,2})/(\d{1,2})\([月火水木金土日]\)",  # 5/17(日) ← 曜日付きを先に試す
        r"(\d{1,2})/(\d{1,2})",                      # 5/17
        r"(\d{1,2})月(\d{1,2})日",                   # 5月17日
    ]

    for item in content_list:
        text = item["text"]
        link = item["link"]

        if not any(kw in text for kw in event_keywords):
            continue

        date_found = None
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                date_found = f"{match.group(1)}/{match.group(2)}"
                break

        if not date_found:
            continue

        # 古いデータは除外（現在年の1月より前）
        if is_past_date(date_found):
            continue

        # 曜日を自動付与
        date_with_weekday = add_weekday(date_found)

        # タイトル：1行目の先頭100文字、余分な空白を除去
        title = re.sub(r"\s+", " ", text.split("\n")[0]).strip()[:100]

        # タイトルレベルの追加除外
        skip_title_keywords = ["休講", "定休日", "スクール生", "今後の予定"]
        if any(k in title for k in skip_title_keywords):
            continue

        # イベントタイプ判定してラベルを付与
        event_type = classify_event_type(title)
        label = "【結果報告】" if event_type == "result" else "【大会募集】"
        display_title = f"{label} {title}"

        events.append({
            "date": date_found,          # ソートなどに使う生データ
            "date_display": date_with_weekday,  # 表示用（曜日付き）
            "title": display_title,
            "url": link,
            "category": classify_event(text),
            "event_type": event_type,
        })

    return events


def remove_duplicates(events):
    """
    重複削除（強化版）
    「同じ日付」かつ「タイトル先頭5文字が一致」→ 重複とみなす
    「結果」を含む方を優先して残す
    """
    groups = {}
    for ev in events:
        # ラベルを除いた本来のタイトル部分で比較
        title_core = ev["title"].replace("【結果報告】 ", "").replace("【大会募集】 ", "")
        key = (ev["date"], title_core[:5])
        if key not in groups:
            groups[key] = []
        groups[key].append(ev)

    unique_events = []
    for key, group in groups.items():
        if len(group) == 1:
            unique_events.append(group[0])
        else:
            result_events = [e for e in group if e["event_type"] == "result"]
            unique_events.append(result_events[0] if result_events else group[0])

    return unique_events


def extract_all_events(content, url, site_name):
    """全データからイベント情報を抽出・分類"""
    all_events = {"junior": [], "adult": []}

    events = extract_events_from_content(content, url, site_name)
    print(f"📊 {site_name}: 抽出 {len(events)}件")

    for event in events:
        all_events[event["category"]].append(event)

    all_events["junior"] = remove_duplicates(all_events["junior"])
    all_events["adult"] = remove_duplicates(all_events["adult"])

    print(f"🎾 ジュニア: {len(all_events['junior'])}件")
    print(f"🏆 一般: {len(all_events['adult'])}件")

    return all_events


def generate_event_cards(events):
    """イベントカードのHTML生成"""
    if not events:
        return '<div style="text-align:center; padding:40px; color:#999;">現在、新しい情報はありません。</div>'

    html = ""
    for ev in events:
        is_result = ev.get("event_type") == "result"
        link_label = "📊 試合結果を見る" if is_result else "📋 大会要項を見る"
        card_class = "event-card result-card" if is_result else "event-card entry-card"
        date_class = "event-date date-result" if is_result else "event-date date-entry"

        html += f"""
        <div class="{card_class}">
            <div class="{date_class}">{ev['date_display']}</div>
            <div class="event-details">
                <div class="event-title">{ev['title']}</div>
                <div class="event-actions">
                    <a href="{ev['url']}" class="btn {'btn-result' if is_result else 'btn-info'}" target="_blank">{link_label}</a>
                </div>
            </div>
        </div>
        """
    return html


def update_html(events):
    """HTMLファイルを更新"""
    update_time = datetime.now().strftime("%Y/%m/%d %H:%M")
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
            --main-dark: #E07B00;
            --result: #1E7BC4;
            --result-dark: #155FA0;
            --bg: #FFFBF5;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", "Yu Gothic", sans-serif;
            background: var(--bg);
            color: #333;
            padding-bottom: 100px;
        }}

        /* ヘッダー */
        .header {{
            background: linear-gradient(135deg, var(--main), #FFD700);
            color: white;
            padding: 25px 15px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.15);
        }}
        .header h1 {{ font-size: 26px; margin-bottom: 6px; font-weight: 700; }}
        .header p {{ font-size: 13px; opacity: 0.95; }}

        /* ★ 改良タブ：大きくて押しやすいボタン型 */
        .tab-wrapper {{
            display: flex;
            gap: 10px;
            padding: 12px 15px;
            background: white;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .tab-btn {{
            flex: 1;
            padding: 14px 10px;
            border-radius: 10px;
            border: 2px solid #E0E0E0;
            background: #F5F5F5;
            color: #999;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.25s;
            text-align: center;
            line-height: 1.4;
        }}
        .tab-btn .tab-icon {{ font-size: 24px; display: block; margin-bottom: 4px; }}
        .tab-btn.active {{
            background: var(--main);
            border-color: var(--main);
            color: white;
            box-shadow: 0 3px 10px rgba(255,140,0,0.4);
            transform: translateY(-1px);
        }}
        .tab-btn:not(.active):hover {{
            background: #FFF3E0;
            border-color: #FFB74D;
            color: #E07B00;
        }}

        /* セクション */
        .section {{ display: none; padding: 12px 15px; max-width: 600px; margin: 0 auto; }}
        .section.active {{ display: block; animation: fadeIn 0.3s; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}

        /* イベントカード共通 */
        .event-card {{
            display: flex;
            background: white;
            margin-bottom: 12px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 6px rgba(0,0,0,0.07);
            transition: transform 0.15s;
        }}
        .event-card:active {{ transform: scale(0.98); }}

        /* 【大会募集】カード：オレンジ */
        .entry-card {{ border: 1px solid #FFE0B2; }}
        .date-entry {{
            background: #FFF3E0;
            color: var(--main);
            min-width: 72px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            border-right: 1px solid #FFE0B2;
            font-size: 13px;
            padding: 8px 4px;
            text-align: center;
        }}

        /* 【結果報告】カード：ブルー */
        .result-card {{ border: 1px solid #BBDEFB; }}
        .date-result {{
            background: #E3F2FD;
            color: var(--result);
            min-width: 72px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            border-right: 1px solid #BBDEFB;
            font-size: 13px;
            padding: 8px 4px;
            text-align: center;
        }}

        .event-details {{ flex: 1; padding: 13px 15px; }}
        .event-title {{ font-size: 14px; font-weight: bold; margin-bottom: 10px; line-height: 1.5; color: #222; }}
        .event-actions {{ margin-top: 6px; }}

        /* ボタン */
        .btn {{
            display: inline-block;
            padding: 7px 13px;
            border-radius: 5px;
            text-decoration: none;
            font-size: 12px;
            font-weight: bold;
            transition: all 0.2s;
        }}
        .btn-info {{ border: 1.5px solid var(--main); color: var(--main); background: white; }}
        .btn-info:hover {{ background: var(--main); color: white; }}
        .btn-result {{ background: var(--result); color: white; border: 1.5px solid var(--result); }}
        .btn-result:hover {{ background: var(--result-dark); }}

        /* フッター */
        .footer {{
            position: fixed;
            bottom: 0;
            width: 100%;
            background: white;
            padding: 12px 15px;
            text-align: center;
            font-size: 11px;
            border-top: 1px solid #EEE;
            color: #aaa;
        }}

        @media (min-width: 768px) {{
            .header h1 {{ font-size: 32px; }}
            .section {{ padding: 20px; }}
            .tab-btn {{ font-size: 18px; padding: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎾 福岡テニス速報</h1>
        <p>筑紫野エリアの大会・結果を自動収集</p>
    </div>

    <!-- ★ 大きいボタン型タブ -->
    <div class="tab-wrapper">
        <div class="tab-btn active" id="tab-jr" onclick="switchTab('jr')">
            <span class="tab-icon">👦</span>ジュニア
        </div>
        <div class="tab-btn" id="tab-ad" onclick="switchTab('ad')">
            <span class="tab-icon">🏆</span>一般・社会人
        </div>
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
            document.getElementById('tab-jr').classList.toggle('active', id === 'jr');
            document.getElementById('tab-ad').classList.toggle('active', id === 'ad');
            document.querySelectorAll('.section').forEach(s => {{
                s.classList.toggle('active', s.id === id);
            }});
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
    </script>
</body>
</html>"""

    try:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        print("✅ HTMLファイル更新完了")
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
            "access_token": THREADS_TOKEN,
        }
        response = requests.post(url, params=params)
        container_id = response.json().get("id")

        if not container_id:
            print("❌ Threadsコンテナ作成失敗")
            return

        time.sleep(2)

        publish_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish"
        publish_params = {
            "creation_id": container_id,
            "access_token": THREADS_TOKEN,
        }
        publish_response = requests.post(publish_url, params=publish_params)

        if publish_response.status_code == 200:
            print("✅ Threads投稿成功")
        else:
            print(f"❌ Threads投稿エラー: {publish_response.status_code}")

    except Exception as e:
        print(f"❌ Threads投稿エラー: {e}")


def main():
    print("=" * 70)
    print("🎾 福岡テニス情報収集システム v6.0")
    print("=" * 70)

    blacklist = load_blacklist()
    all_events = {"junior": [], "adult": []}

    for site_name, url in SITES.items():
        print(f"\n📡 {site_name} をチェック中...")
        content = scrape_site(url)

        if content:
            events = extract_all_events(content, url, site_name)
            events["junior"] = apply_blacklist(events["junior"], blacklist)
            events["adult"] = apply_blacklist(events["adult"], blacklist)
            all_events["junior"].extend(events["junior"])
            all_events["adult"].extend(events["adult"])

    print("\n🌐 HTMLファイルを更新中...")
    update_html(all_events)

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
        print("\n📭 イベント情報が取得できませんでした")

    print("\n" + "=" * 70)
    print("✅ 処理完了！")
    print("=" * 70)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎾 福岡テニス速報システム v9.0 ULTIMATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 新機能:
✅ 未来（試合要項）: オレンジ系・昇順
✅ 過去（試合結果）: 青系・降順
✅ セパレーターで明確分離
✅ GitHub/Threads自動投稿対応
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [1] 設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_DIR = r"C:\Users\tenni\tennis-info"
EVENTS_FILE = os.path.join(BASE_DIR, "events.json")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
INDEX_HTML = os.path.join(PUBLIC_DIR, "index.html")

# 主催者URL
SITES = {
    "筑紫野ローンテニスクラブ": "https://chikushinotennis.web.fc2.com/",
    "ITS九州": "https://its-kyushu.com/",
    "福岡パシフィックテニスアカデミー": "http://www.sp-fukuoka.com/",
    "城南テニスクラブ": "https://jonantennis.net/"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [2] admin.py が呼び出す関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_events():
    """
    events.json を読み込んで返す
    admin.py の rebuild_html() から呼ばれる
    """
    if not os.path.exists(EVENTS_FILE):
        return []
    
    try:
        with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"エラー: events.json 読み込み失敗: {e}")
        return []


def update_html(approved_events):
    """
    承認済みイベントから index.html を生成
    admin.py の rebuild_html() から呼ばれる
    
    Args:
        approved_events: status が "approved" のイベントリスト
    """
    # public ディレクトリ作成
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    
    # イベントを日付順にソート
    def parse_date(ev):
        try:
            date_str = ev['date'].split('(')[0]  # "2026/5/17(日)" → "2026/5/17"
            y, m, d = map(int, date_str.split('/'))
            return date(y, m, d)
        except:
            return date(2099, 12, 31)
    
    # 今日の日付
    today = date.today()
    
    # 未来と過去に分類
    future_events = [e for e in approved_events if parse_date(e) >= today]
    past_events = [e for e in approved_events if parse_date(e) < today]
    
    # 未来: 昇順（近い順）、過去: 降順（新しい順）
    future_events.sort(key=parse_date)
    past_events.sort(key=parse_date, reverse=True)
    
    # カテゴリ別に分類
    def normalize_category(cat):
        if cat in ["ジュニア", "junior"]:
            return "junior"
        elif cat in ["一般", "adult"]:
            return "adult"
        return "other"
    
    # 未来（ジュニア/一般）
    future_junior = [e for e in future_events if normalize_category(e.get('category')) == 'junior']
    future_adult = [e for e in future_events if normalize_category(e.get('category')) == 'adult']
    
    # 過去（ジュニア/一般）
    past_junior = [e for e in past_events if normalize_category(e.get('category')) == 'junior']
    past_adult = [e for e in past_events if normalize_category(e.get('category')) == 'adult']
    
    # HTML生成
    html_content = generate_html(future_junior, future_adult, past_junior, past_adult)
    
    # ファイル書き込み
    try:
        with open(INDEX_HTML, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ HTML生成成功: {INDEX_HTML}")
        print(f"   未来 - ジュニア: {len(future_junior)}件 / 一般: {len(future_adult)}件")
        print(f"   過去 - ジュニア: {len(past_junior)}件 / 一般: {len(past_adult)}件")
    except Exception as e:
        print(f"❌ HTML生成失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [3] HTML生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_html(future_junior, future_adult, past_junior, past_adult):
    """HTMLテンプレート生成"""
    
    # 未来ジュニアカード生成（オレンジ系）
    future_junior_cards = ""
    if future_junior:
        for ev in future_junior:
            future_junior_cards += f"""
        <div class="event-card future">
            <div class="event-date">{ev['date']}</div>
            <div class="event-title">{ev['title']}</div>
            <div class="event-source">主催: {ev['source']}</div>
            <a href="{ev['url']}" target="_blank" class="event-link">詳細を見る →</a>
        </div>
"""
    else:
        future_junior_cards = '<div class="no-events">現在、募集中の大会はありません。</div>'
    
    # 未来一般カード生成（オレンジ系）
    future_adult_cards = ""
    if future_adult:
        for ev in future_adult:
            future_adult_cards += f"""
        <div class="event-card future">
            <div class="event-date">{ev['date']}</div>
            <div class="event-title">{ev['title']}</div>
            <div class="event-source">主催: {ev['source']}</div>
            <a href="{ev['url']}" target="_blank" class="event-link">詳細を見る →</a>
        </div>
"""
    else:
        future_adult_cards = '<div class="no-events">現在、募集中の大会はありません。</div>'
    
    # 過去ジュニアカード生成（青系）
    past_junior_cards = ""
    if past_junior:
        for ev in past_junior:
            past_junior_cards += f"""
        <div class="event-card past">
            <div class="event-date">{ev['date']}</div>
            <div class="event-title">{ev['title']}</div>
            <div class="event-source">主催: {ev['source']}</div>
            <a href="{ev['url']}" target="_blank" class="event-link">詳細を見る →</a>
        </div>
"""
    else:
        past_junior_cards = '<div class="no-events">過去の結果はまだありません。</div>'
    
    # 過去一般カード生成（青系）
    past_adult_cards = ""
    if past_adult:
        for ev in past_adult:
            past_adult_cards += f"""
        <div class="event-card past">
            <div class="event-date">{ev['date']}</div>
            <div class="event-title">{ev['title']}</div>
            <div class="event-source">主催: {ev['source']}</div>
            <a href="{ev['url']}" target="_blank" class="event-link">詳細を見る →</a>
        </div>
"""
    else:
        past_adult_cards = '<div class="no-events">過去の結果はまだありません。</div>'
    
    # 最終更新日時
    now = datetime.now()
    update_time = now.strftime("%Y/%m/%d %H:%M")
    
    # HTMLテンプレート
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎾 福岡テニス速報</title>
<style>
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", sans-serif;
    background: #f5f5f5;
    color: #333;
}}

.header {{
    background: linear-gradient(135deg, #FF8C00 0%, #FFD700 100%);
    color: white;
    padding: 40px 20px;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}}

.header h1 {{
    font-size: 36px;
    font-weight: bold;
    margin-bottom: 10px;
}}

.header p {{
    font-size: 14px;
    opacity: 0.9;
}}

.notice {{
    background: #FFF3CD;
    border-left: 4px solid #FF8C00;
    padding: 15px 20px;
    margin: 20px auto;
    max-width: 1000px;
    border-radius: 8px;
    text-align: center;
    font-weight: bold;
    color: #856404;
}}

.tabs {{
    display: flex;
    max-width: 1000px;
    margin: 30px auto 0;
    padding: 0 20px;
    gap: 10px;
}}

.tab {{
    flex: 1;
    padding: 18px;
    background: white;
    border: none;
    border-radius: 12px 12px 0 0;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.3s;
    color: #666;
    border-bottom: 4px solid transparent;
}}

.tab.active {{
    background: linear-gradient(135deg, #FF8C00 0%, #FFD700 100%);
    color: white;
    border-bottom-color: #FF8C00;
}}

.tab:hover:not(.active) {{
    background: #f8f8f8;
}}

.tab-content {{
    display: none;
    max-width: 1000px;
    margin: 0 auto;
    padding: 30px 20px;
}}

.tab-content.active {{
    display: block;
}}

.section-separator {{
    margin: 40px 0;
    text-align: center;
    position: relative;
}}

.section-separator::before {{
    content: '';
    display: block;
    height: 2px;
    background: linear-gradient(to right, transparent, #ddd, transparent);
    margin-bottom: 20px;
}}

.section-title {{
    font-size: 24px;
    font-weight: bold;
    margin-bottom: 10px;
    display: inline-block;
    padding: 10px 30px;
    border-radius: 50px;
}}

.section-title.future {{
    background: linear-gradient(135deg, #FF8C00, #FFD700);
    color: white;
}}

.section-title.past {{
    background: linear-gradient(135deg, #1976D2, #42A5F5);
    color: white;
}}

.event-card {{
    background: white;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 15px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    transition: transform 0.2s, box-shadow 0.2s;
}}

.event-card.future {{
    border-left: 5px solid #FF8C00;
}}

.event-card.past {{
    border-left: 5px solid #1976D2;
}}

.event-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}}

.event-date {{
    display: inline-block;
    padding: 6px 12px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 14px;
    margin-bottom: 10px;
}}

.future .event-date {{
    background: #FFF3E0;
    color: #FF8C00;
}}

.past .event-date {{
    background: #E3F2FD;
    color: #1976D2;
}}

.event-title {{
    font-size: 18px;
    font-weight: bold;
    color: #1565C0;
    margin: 10px 0;
    line-height: 1.5;
}}

.event-source {{
    font-size: 13px;
    color: #666;
    margin: 8px 0;
}}

.event-link {{
    display: inline-block;
    margin-top: 12px;
    padding: 10px 20px;
    border-radius: 6px;
    font-weight: bold;
    transition: background 0.3s;
    text-decoration: none;
}}

.future .event-link {{
    background: #FF8C00;
    color: white;
}}

.future .event-link:hover {{
    background: #E67E00;
}}

.past .event-link {{
    background: #1976D2;
    color: white;
}}

.past .event-link:hover {{
    background: #1565C0;
}}

.no-events {{
    text-align: center;
    padding: 60px 20px;
    color: #999;
    font-size: 16px;
}}

.footer {{
    text-align: center;
    padding: 30px 20px;
    color: #999;
    font-size: 12px;
    border-top: 1px solid #e0e0e0;
    margin-top: 40px;
}}

@media (max-width: 768px) {{
    .header h1 {{
        font-size: 28px;
    }}
    
    .tab {{
        font-size: 16px;
        padding: 14px;
    }}
    
    .section-title {{
        font-size: 20px;
    }}
    
    .event-title {{
        font-size: 16px;
    }}
}}
</style>
</head>
<body>

<div class="header">
    <h1>🎾 福岡テニス速報</h1>
    <p>福岡エリアの大会・結果を自動収集 | v9.0 ULTIMATE</p>
</div>

<div class="notice">
    ⚠️ エントリーするときは、必ず主催のHPを確認してください！
</div>

<div class="tabs">
    <button class="tab active" onclick="switchTab('junior')">👦 ジュニア</button>
    <button class="tab" onclick="switchTab('adult')">🏆 一般・社会人</button>
</div>

<div id="junior" class="tab-content active">
    <!-- 未来（試合要項） -->
    <div class="section-separator">
        <div class="section-title future">📋 試合要項（募集中）</div>
    </div>
    {future_junior_cards}
    
    <!-- 過去（試合結果） -->
    <div class="section-separator">
        <div class="section-title past">🏅 試合結果（開催済み）</div>
    </div>
    {past_junior_cards}
</div>

<div id="adult" class="tab-content">
    <!-- 未来（試合要項） -->
    <div class="section-separator">
        <div class="section-title future">📋 試合要項（募集中）</div>
    </div>
    {future_adult_cards}
    
    <!-- 過去（試合結果） -->
    <div class="section-separator">
        <div class="section-title past">🏅 試合結果（開催済み）</div>
    </div>
    {past_adult_cards}
</div>

<div class="footer">
    最終更新: {update_time} | v9.0 ULTIMATE | テニスをいざやかに! 🎾
</div>

<script>
function switchTab(tabName) {{
    // すべてのタブを非アクティブに
    document.querySelectorAll('.tab').forEach(tab => {{
        tab.classList.remove('active');
    }});
    document.querySelectorAll('.tab-content').forEach(content => {{
        content.classList.remove('active');
    }});
    
    // クリックされたタブをアクティブに
    event.target.classList.add('active');
    document.getElementById(tabName).classList.add('active');
}}
</script>

</body>
</html>"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [5] メインエントリーポイント
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    print("=" * 80)
    print("🎾 福岡テニス速報 コレクター v9.0 ULTIMATE")
    print("=" * 80)
    
    # 既存のevents.jsonを読み込んでHTML生成
    events = load_events()
    
    if not events:
        print("⚠️  events.json が見つかりません")
        print("=" * 80)
        exit(1)
    
    # 承認済みイベントのみ抽出
    approved = [e for e in events if e.get("status") == "approved"]
    
    print(f"\n📊 データ状況:")
    print(f"   全データ: {len(events)}件")
    print(f"   承認済み: {len(approved)}件")
    
    # HTML生成
    update_html(approved)
    
    print("\n✅ 処理完了")
    print(f"   公開ページ: {INDEX_HTML}")
    print("=" * 80)
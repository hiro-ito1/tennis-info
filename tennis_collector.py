"""
福岡テニス情報 自動収集スクリプト
対象：筑紫野ローンTC・筑紫野市テニス協会
機能：新しい情報だけを検出して通知
"""

import requests
from bs4 import BeautifulSoup
import json
import hashlib
from datetime import datetime
import os

# ============================
# 設定
# ============================
SITES = [
    {
        "name": "筑紫野ローンテニスクラブ",
        "url": "https://chikushinotennis.web.fc2.com/",
        "encoding": "utf-8",
        "update_section": "更新情報",  # このセクションを監視
    },
    {
        "name": "筑紫野市テニス協会",
        "url": "http://chikushino-tennis.com/",
        "encoding": "shift_jis",       # 文字コードに注意！
        "update_section": "お知らせ",
    },
]

# 過去の情報を保存するファイル
HISTORY_FILE = "tennis_history.json"


# ============================
# 関数1：過去の記録を読み込む
# ============================
def load_history():
    """保存済みの情報を読み込む"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ============================
# 関数2：記録を保存する
# ============================
def save_history(history):
    """情報を保存する"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ============================
# 関数3：ページを取得する
# ============================
def fetch_page(url, encoding):
    """指定したURLのページを取得する"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; TennisBot/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = encoding
        return response.text
    except Exception as e:
        print(f"  ❌ 取得失敗: {e}")
        return None


# ============================
# 関数4：筑紫野ローンTCの更新情報を取得
# ============================
def parse_chikushinotennis(html):
    """筑紫野ローンTCの更新情報を解析する"""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # 「更新情報」セクションの日付と内容を探す
    # サイト構造：日付(例:2026.4.19) + リンクテキスト
    update_section = soup.find_all(string=lambda t: t and "更新情報" in t)

    # 日付パターン(YYYY.M.DD)のテキストを含む要素を探す
    import re
    date_pattern = re.compile(r"20\d{2}\.\d{1,2}\.\d{1,2}")

    all_text = soup.get_text()
    lines = all_text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if date_pattern.match(line):
            date_str = line
            # 次の行が内容
            content = ""
            j = i + 1
            while j < len(lines) and j < i + 4:
                next_line = lines[j].strip()
                if next_line and not date_pattern.match(next_line):
                    content = next_line
                    break
                j += 1

            if content:
                items.append({
                    "date": date_str,
                    "content": content,
                    "id": hashlib.md5(f"{date_str}_{content}".encode()).hexdigest()[:8]
                })
        i += 1

    return items[:15]  # 最新15件


# ============================
# 関数5：筑紫野市テニス協会の更新情報を取得
# ============================
def parse_chikushino_city(html):
    """筑紫野市テニス協会の更新情報を解析する"""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    import re
    # 日付パターン: M/D/YYYY 形式
    date_pattern = re.compile(r"\d{1,2}/\d{1,2}/20\d{2}")

    # dl要素（定義リスト）から情報を取得
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
                    "content": content[:80],  # 長すぎる場合は切る
                    "url": url,
                    "id": hashlib.md5(f"{date_str}_{content}".encode()).hexdigest()[:8]
                })

    # dl形式でない場合のフォールバック
    if not items:
        all_text = soup.get_text()
        lines = all_text.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if date_pattern.search(line):
                content = ""
                if i + 1 < len(lines):
                    content = lines[i + 1].strip()
                if content:
                    items.append({
                        "date": line,
                        "content": content[:80],
                        "id": hashlib.md5(f"{line}_{content}".encode()).hexdigest()[:8]
                    })

    return items[:15]


# ============================
# メイン処理
# ============================
def main():
    print("=" * 50)
    print("🎾 福岡テニス情報 自動収集スクリプト")
    print(f"   実行時刻: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    print("=" * 50)

    history = load_history()
    new_items_all = []

    for site in SITES:
        print(f"\n📡 {site['name']} をチェック中...")
        print(f"   URL: {site['url']}")

        html = fetch_page(site["url"], site["encoding"])
        if not html:
            continue

        # サイトごとに解析関数を切り替え
        if "chikushinotennis" in site["url"]:
            items = parse_chikushinotennis(html)
        else:
            items = parse_chikushino_city(html)

        print(f"   📋 取得件数: {len(items)}件")

        # 過去の記録と比較して新しい情報だけを抽出
        site_key = site["name"]
        known_ids = set(history.get(site_key, []))
        new_items = [item for item in items if item["id"] not in known_ids]

        if new_items:
            print(f"   🆕 新着情報: {len(new_items)}件")
            for item in new_items:
                print(f"      [{item['date']}] {item['content']}")
                new_items_all.append({
                    "site": site["name"],
                    **item
                })
            # 記録を更新
            all_ids = list(known_ids | {item["id"] for item in items})
            history[site_key] = all_ids
        else:
            print(f"   ✅ 新着なし（前回から変化なし）")

    # 結果をまとめて表示
    print("\n" + "=" * 50)
    if new_items_all:
        print(f"🎉 合計 {len(new_items_all)}件の新着情報を発見！")
        print()
        for item in new_items_all:
            print(f"【{item['site']}】")
            print(f"  日付: {item['date']}")
            print(f"  内容: {item['content']}")
            if item.get("url"):
                print(f"  URL: {item['url']}")
            print()

        # 結果をファイルに保存
        result_file = f"tennis_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(new_items_all, f, ensure_ascii=False, indent=2)
        print(f"📁 結果を保存: {result_file}")
    else:
        print("📭 新着情報はありませんでした")

    # 履歴を保存
    save_history(history)
    print("\n✅ 完了！次回実行時は今回の情報をスキップします")
    print("=" * 50)

    return new_items_all


if __name__ == "__main__":
    main()

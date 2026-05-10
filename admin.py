"""
福岡テニス速報 管理画面 v9.0 ULTIMATE (Hybrid Edition)
=====================================
Windows/Linux 完全対応版
"""

from flask import Flask, render_template_string, redirect, url_for, request
import json
import os
from datetime import datetime, date
from pathlib import Path
import shutil
import re

app = Flask(__name__)

def load_config():
    config_file = "config.json"
    if not os.path.exists(config_file):
        return {"data_directory": os.getcwd()}
    try:
        with open(config_file, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print("警告: config.json読み込みエラー: {}".format(e))
        return {"data_directory": os.getcwd()}

def save_config(config):
    config_file = "config.json"
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("エラー: config.json保存エラー: {}".format(e))

# --- DATA_DIR 設定セクション (CLAUDE & 軍師 最終安定版) ---
CONFIG = load_config()
PC_PATH = r"C:\Users\tenni\tennis-info"

# 優先順位: 1.config.json → 2.PCパス(Windows) → 3.カレント(GitHub/Linux)
if CONFIG.get("data_directory") and os.path.exists(CONFIG.get("data_directory")):
    DATA_DIR = Path(CONFIG.get("data_directory"))
elif os.path.exists(PC_PATH):
    DATA_DIR = Path(PC_PATH)
else:
    DATA_DIR = Path(os.getcwd())

DATA_DIR.mkdir(parents=True, exist_ok=True)
# -------------------------------------------------------

EVENTS_FILE = DATA_DIR / "events.json"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

SOURCES = [
    "筑紫野ローンテニスクラブ",
    "ITS九州",
    "福岡パシフィックテニスアカデミー",
    "城南テニスクラブ"
]

def load_events():
    if not EVENTS_FILE.exists():
        return []
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            print("📊 読み込み成功: {}件".format(len(data)))
            return data
    except Exception as e:
        print("警告: events.json読み込みエラー: {}".format(e))
        return []

def save_events(events):
    if EVENTS_FILE.exists():
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / "events_{}.json".format(timestamp)
            shutil.copy2(EVENTS_FILE, backup_file)
            backups = sorted(BACKUP_DIR.glob("events_*.json"), reverse=True)
            for old_backup in backups[5:]:
                old_backup.unlink()
        except Exception:
            pass
    try:
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("エラー: events.json保存エラー: {}".format(e))

def parse_date_for_sorting(date_str):
    try:
        clean_date = date_str.split('(')[0].strip()
        parts = clean_date.split('/')
        
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            now = datetime.now()
            month, day = map(int, parts)
            year = now.year
            if now.month >= 10 and month <= 3:
                year += 1
            return date(year, month, day)
        return date(2099, 12, 31)
    except Exception as e:
        print("日付パースエラー [{}]: {}".format(date_str, e))
        return date(2099, 12, 31)

def add_weekday(date_str):
    try:
        event_date = parse_date_for_sorting(date_str)
        month = event_date.month
        day = event_date.day
        return "{}/{}({})".format(month, day, WEEKDAY_JP[event_date.weekday()])
    except Exception:
        return date_str

def sort_events_by_date(events):
    def get_date_str(e):
        return e.get("date_display") or e.get("date", "")
    
    return sorted(events, key=lambda e: parse_date_for_sorting(get_date_str(e)))

def rebuild_html():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("tc", "tennis_collector.py")
        tc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tc)
        approved = [e for e in tc.load_events() if e["status"] == "approved"]
        tc.update_html(approved)
        return True
    except Exception as e:
        print("HTML再生成エラー: {}".format(e))
        return False

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>テニス速報 管理画面 v9.0</title>
<style>
:root{--main:#FF8C00;--ok:#2E7D32;--ng:#C62828;}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,sans-serif;background:#F5F5F5;}
.header{background:linear-gradient(135deg,var(--main),#FFD700);color:white;padding:20px;text-align:center;position:relative;}
.header h1{font-size:22px;}
.header .public-btn{position:absolute;right:20px;top:20px;background:white;color:var(--main);padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.2);transition:all 0.3s;}
.header .public-btn:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.3);}
.stats{display:flex;gap:10px;padding:15px;max-width:1200px;margin:0 auto;}
.stat-card{flex:1;background:white;border-radius:10px;padding:15px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.08);}
.stat-card .num{font-size:32px;font-weight:bold;}
.stat-card .label{font-size:12px;color:#888;margin-top:4px;}
.pending-num{color:var(--main);}
.approved-num{color:var(--ok);}
.tab-wrapper{display:flex;gap:10px;padding:12px 15px;max-width:1200px;margin:0 auto;background:white;border-radius:10px;margin-bottom:15px;overflow-x:auto;}
.tab-btn{flex:1;padding:12px;border-radius:8px;border:2px solid #E0E0E0;background:#F5F5F5;color:#666;font-size:15px;font-weight:bold;cursor:pointer;transition:all 0.2s;text-align:center;white-space:nowrap;min-width:100px;}
.tab-btn.active{background:var(--main);border-color:var(--main);color:white;}
.section{max-width:1200px;margin:0 auto 20px;padding:0 15px;display:none;}
.section.active{display:block;}
.bulk-actions{background:white;border-radius:10px;padding:15px;margin-bottom:15px;box-shadow:0 2px 6px rgba(0,0,0,0.08);display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
.bulk-actions label{font-weight:bold;font-size:14px;}
.bulk-btn{padding:8px 16px;border:none;border-radius:6px;font-size:13px;font-weight:bold;cursor:pointer;}
.bulk-btn.approve{background:var(--ok);color:white;}
.bulk-btn.reject{background:var(--ng);color:white;}
.bulk-btn.toggle{background:#1976D2;color:white;}
.card{background:white;border-radius:10px;padding:15px;margin-bottom:10px;box-shadow:0 2px 5px rgba(0,0,0,0.07);border-left:4px solid #DDD;}
.card.pending{border-left-color:var(--main);background:#FFF8E1;}
.card.approved{border-left-color:var(--ok);}
.card.rejected{border-left-color:#CCC;opacity:0.6;}
.card-checkbox{margin-right:10px;}
.card-top{display:flex;align-items:flex-start;gap:10px;}
.date-badge{background:#FFF3E0;color:var(--main);border-radius:6px;padding:4px 8px;font-weight:bold;font-size:13px;}
.approved .date-badge{background:#E8F5E9;color:var(--ok);}
.card-title{font-size:14px;font-weight:bold;line-height:1.5;flex:1;color:#1565C0;}
.card-meta{font-size:11px;color:#888;margin-top:6px;}
.card-meta a{color:#1976D2;text-decoration:underline;}
.source-badge{background:#FFF3E0;color:#E65100;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px;}
.actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;}
.btn{padding:8px 16px;border:none;border-radius:6px;font-size:13px;font-weight:bold;cursor:pointer;text-decoration:none;display:inline-block;}
.btn-approve{background:var(--ok);color:white;}
.btn-reject{background:#EEE;color:#555;}
.btn-rebuild{background:var(--main);color:white;}
.btn-edit{background:#1976D2;color:white;}
.msg{background:#D4EDDA;color:#155724;border-radius:8px;padding:12px 15px;margin:10px auto 15px;max-width:1200px;text-align:center;}
.form-group{margin-bottom:15px;}
.form-group label{display:block;font-size:13px;font-weight:bold;margin-bottom:5px;color:#555;}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:10px;border:2px solid #E0E0E0;border-radius:6px;font-size:14px;}
.form-group textarea{resize:vertical;min-height:80px;}
.form-group small{display:block;font-size:11px;color:#888;margin-top:4px;}
.form-box{background:white;border-radius:10px;padding:20px;margin-bottom:20px;box-shadow:0 2px 6px rgba(0,0,0,0.08);}
.form-box h3{font-size:16px;margin-bottom:15px;color:#333;}
</style>
</head>
<body>

<div class="header">
<h1>🎾 テニス速報 管理画面 v9.0 ULTIMATE</h1>
<p>主催者別タブ + 一括処理 + Windows/Linux対応</p>
<a href="../public/index.html" target="_blank" class="public-btn">📄 公開ページを表示</a>
</div>

{% if message %}
<div class="msg">{{ message }}</div>
{% endif %}

<div class="stats">
<div class="stat-card">
<div class="num pending-num">{{ pending_count }}</div>
<div class="label">確認待ち</div>
</div>
<div class="stat-card">
<div class="num approved-num">{{ approved_count }}</div>
<div class="label">公開中</div>
</div>
</div>

<div style="max-width:1200px;margin:0 auto 15px;padding:0 15px;text-align:right;">
<a href="/rebuild" class="btn btn-rebuild">HTMLを再生成</a>
</div>

<div class="tab-wrapper">
<div class="tab-btn active" onclick="switchTab('all')">全て</div>
<div class="tab-btn" onclick="switchTab('chikushino')">筑紫野LTC</div>
<div class="tab-btn" onclick="switchTab('its')">ITS九州</div>
<div class="tab-btn" onclick="switchTab('pacific')">パシフィック</div>
<div class="tab-btn" onclick="switchTab('jonan')">城南TC</div>
<div class="tab-btn" onclick="switchTab('approved')">公開中</div>
<div class="tab-btn" onclick="switchTab('rejected')">却下済み</div>
<div class="tab-btn" onclick="switchTab('manual')">手動入力</div>
</div>

<!-- 全て -->
<div class="section active" id="section-all">
<div class="bulk-actions">
<label><input type="checkbox" id="select-all-all" onclick="toggleAll('all')"> 全選択</label>
<button class="bulk-btn approve" onclick="bulkApprove('all')">一括承認</button>
<button class="bulk-btn reject" onclick="bulkReject('all')">一括却下</button>
<button class="bulk-btn toggle" onclick="bulkToggleCategory('all')">一括カテゴリ変更</button>
</div>
{% for ev in pending %}
<div class="card pending">
<div class="card-top">
<input type="checkbox" class="card-checkbox checkbox-all" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<span class="source-badge">{{ ev.source }}</span>
<div class="card-meta">
<a href="{{ ev.url }}" target="_blank">公式サイト 🔗</a>
{% if ev.source_origin_url %}
 | <a href="{{ ev.source_origin_url }}" target="_blank">情報元 🔍</a>
{% endif %}
</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
<a href="/toggle_cat/{{ ev.id }}" class="btn btn-edit">カテゴリ変更</a>
</div>
</div>
{% endfor %}
</div>

<!-- 筑紫野LTC -->
<div class="section" id="section-chikushino">
<div class="bulk-actions">
<label><input type="checkbox" id="select-all-chikushino" onclick="toggleAll('chikushino')"> 全選択</label>
<button class="bulk-btn approve" onclick="bulkApprove('chikushino')">一括承認</button>
<button class="bulk-btn reject" onclick="bulkReject('chikushino')">一括却下</button>
<button class="bulk-btn toggle" onclick="bulkToggleCategory('chikushino')">一括カテゴリ変更</button>
</div>
{% for ev in pending_chikushino %}
<div class="card pending">
<div class="card-top">
<input type="checkbox" class="card-checkbox checkbox-chikushino" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<div class="card-meta">
<a href="{{ ev.url }}" target="_blank">公式サイト 🔗</a>
{% if ev.source_origin_url %}
 | <a href="{{ ev.source_origin_url }}" target="_blank">情報元 🔍</a>
{% endif %}
</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
<a href="/toggle_cat/{{ ev.id }}" class="btn btn-edit">カテゴリ変更</a>
</div>
</div>
{% endfor %}
</div>

<!-- ITS九州 -->
<div class="section" id="section-its">
<div class="bulk-actions">
<label><input type="checkbox" id="select-all-its" onclick="toggleAll('its')"> 全選択</label>
<button class="bulk-btn approve" onclick="bulkApprove('its')">一括承認</button>
<button class="bulk-btn reject" onclick="bulkReject('its')">一括却下</button>
<button class="bulk-btn toggle" onclick="bulkToggleCategory('its')">一括カテゴリ変更</button>
</div>
{% for ev in pending_its %}
<div class="card pending">
<div class="card-top">
<input type="checkbox" class="card-checkbox checkbox-its" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<div class="card-meta">
<a href="{{ ev.url }}" target="_blank">公式サイト 🔗</a>
{% if ev.source_origin_url %}
 | <a href="{{ ev.source_origin_url }}" target="_blank">情報元 🔍</a>
{% endif %}
</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
<a href="/toggle_cat/{{ ev.id }}" class="btn btn-edit">カテゴリ変更</a>
</div>
</div>
{% endfor %}
</div>

<!-- 福岡パシフィック -->
<div class="section" id="section-pacific">
<div class="bulk-actions">
<label><input type="checkbox" id="select-all-pacific" onclick="toggleAll('pacific')"> 全選択</label>
<button class="bulk-btn approve" onclick="bulkApprove('pacific')">一括承認</button>
<button class="bulk-btn reject" onclick="bulkReject('pacific')">一括却下</button>
<button class="bulk-btn toggle" onclick="bulkToggleCategory('pacific')">一括カテゴリ変更</button>
</div>
{% for ev in pending_pacific %}
<div class="card pending">
<div class="card-top">
<input type="checkbox" class="card-checkbox checkbox-pacific" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<div class="card-meta">
<a href="{{ ev.url }}" target="_blank">公式サイト 🔗</a>
{% if ev.source_origin_url %}
 | <a href="{{ ev.source_origin_url }}" target="_blank">情報元 🔍</a>
{% endif %}
</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
<a href="/toggle_cat/{{ ev.id }}" class="btn btn-edit">カテゴリ変更</a>
</div>
</div>
{% endfor %}
</div>

<!-- 城南TC -->
<div class="section" id="section-jonan">
<div class="bulk-actions">
<label><input type="checkbox" id="select-all-jonan" onclick="toggleAll('jonan')"> 全選択</label>
<button class="bulk-btn approve" onclick="bulkApprove('jonan')">一括承認</button>
<button class="bulk-btn reject" onclick="bulkReject('jonan')">一括却下</button>
<button class="bulk-btn toggle" onclick="bulkToggleCategory('jonan')">一括カテゴリ変更</button>
</div>
{% for ev in pending_jonan %}
<div class="card pending">
<div class="card-top">
<input type="checkbox" class="card-checkbox checkbox-jonan" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<div class="card-meta">
<a href="{{ ev.url }}" target="_blank">公式サイト 🔗</a>
{% if ev.source_origin_url %}
 | <a href="{{ ev.source_origin_url }}" target="_blank">情報元 🔍</a>
{% endif %}
</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
<a href="/toggle_cat/{{ ev.id }}" class="btn btn-edit">カテゴリ変更</a>
</div>
</div>
{% endfor %}
</div>

<!-- 公開中 -->
<div class="section" id="section-approved">
{% if approved %}
{% for ev in approved %}
<div class="card approved">
<div class="card-top">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<span class="source-badge">{{ ev.source }}</span>
<div class="card-meta">
<a href="{{ ev.url }}" target="_blank">公式サイト 🔗</a>
</div>
</div>
</div>
<div class="actions">
<a href="/restore_pending/{{ ev.id }}" class="btn btn-edit">確認待ちへ戻す</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">取り消し</a>
</div>
</div>
{% endfor %}
{% else %}
<div style="text-align:center;padding:40px;color:#999;">公開中のイベントはありません</div>
{% endif %}
</div>

<!-- 却下済み -->
<div class="section" id="section-rejected">
{% if rejected %}
{% for ev in rejected %}
<div class="card rejected">
<div class="card-top">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<span class="card-title">{{ ev.title }}</span>
<span class="source-badge">{{ ev.source }}</span>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/restore_pending/{{ ev.id }}" class="btn btn-edit">確認待ちへ戻す</a>
</div>
</div>
{% endfor %}
{% else %}
<div style="text-align:center;padding:40px;color:#999;">却下済みはありません</div>
{% endif %}
</div>

<!-- 手動入力 -->
<div class="section" id="section-manual">
<div class="form-box">
<h3>📝 手動入力</h3>
<form action="/add_manual" method="post">
<div class="form-group">
<label>日付（例: 5/17）</label>
<input type="text" name="date" required placeholder="5/17">
</div>
<div class="form-group">
<label>タイトル</label>
<input type="text" name="title" required placeholder="春季ジュニア大会">
</div>
<div class="form-group">
<label>URL</label>
<input type="url" name="url" required placeholder="https://example.com/">
</div>
<div class="form-group">
<label>カテゴリ</label>
<select name="category">
<option value="junior">ジュニア</option>
<option value="adult">一般</option>
</select>
</div>
<div class="form-group">
<label>主催者</label>
<input type="text" name="source" placeholder="筑紫野ローンテニスクラブ">
</div>
<button type="submit" class="btn btn-approve" style="padding:12px 24px;">追加して公開</button>
</form>
</div>
</div>

<script>
function switchTab(tab){
document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
if(event) event.target.classList.add('active');
document.querySelectorAll('.section').forEach(s=>s.classList.toggle('active',s.id==='section-'+tab));
}

function toggleAll(source){
const checkboxes = document.querySelectorAll('.checkbox-'+source);
const selectAll = document.getElementById('select-all-'+source);
checkboxes.forEach(cb => cb.checked = selectAll.checked);
}

function bulkApprove(source){
const ids = Array.from(document.querySelectorAll('.checkbox-'+source+':checked')).map(cb=>cb.value);
if(ids.length===0){alert('イベントを選択してください');return;}
if(confirm(ids.length+'件のイベントを承認しますか？')){
window.location.href='/bulk_approve?ids='+ids.join(',');
}
}

function bulkReject(source){
const ids = Array.from(document.querySelectorAll('.checkbox-'+source+':checked')).map(cb=>cb.value);
if(ids.length===0){alert('イベントを選択してください');return;}
if(confirm(ids.length+'件のイベントを却下しますか？')){
window.location.href='/bulk_reject?ids='+ids.join(',');
}
}

function bulkToggleCategory(source){
const ids = Array.from(document.querySelectorAll('.checkbox-'+source+':checked')).map(cb=>cb.value);
if(ids.length===0){alert('イベントを選択してください');return;}
if(confirm(ids.length+'件のカテゴリを変更しますか？')){
window.location.href='/bulk_toggle_cat?ids='+ids.join(',');
}
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    events = load_events()
    msg = request.args.get("msg", "")
    
    events = sort_events_by_date(events)
    
    pending = [e for e in events if e.get("status") == "pending"]
    approved = [e for e in events if e.get("status") == "approved"]
    rejected = [e for e in events if e.get("status") == "rejected"]
    
    pending_chikushino = [e for e in pending if e.get("source") == "筑紫野ローンテニスクラブ"]
    pending_its = [e for e in pending if e.get("source") == "ITS九州"]
    pending_pacific = [e for e in pending if e.get("source") == "福岡パシフィックテニスアカデミー"]
    pending_jonan = [e for e in pending if e.get("source") == "城南テニスクラブ"]
    
    return render_template_string(
        ADMIN_TEMPLATE,
        pending=pending,
        approved=approved,
        rejected=rejected,
        pending_chikushino=pending_chikushino,
        pending_its=pending_its,
        pending_pacific=pending_pacific,
        pending_jonan=pending_jonan,
        pending_count=len(pending),
        approved_count=len(approved),
        message=msg
    )

@app.route("/approve/<ev_id>")
def approve(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            ev["status"] = "approved"
            break
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="承認しました"))

@app.route("/reject/<ev_id>")
def reject(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            ev["status"] = "rejected"
            break
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="却下しました"))

@app.route("/toggle_cat/<ev_id>")
def toggle_cat(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            current = ev.get("category", "adult")
            if current in ["junior", "ジュニア"]:
                ev["category"] = "adult"
            else:
                ev["category"] = "junior"
            break
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="カテゴリーを変更しました"))

@app.route("/bulk_approve")
def bulk_approve():
    ids = request.args.get("ids", "").split(",")
    events = load_events()
    count = 0
    for ev in events:
        if ev["id"] in ids:
            ev["status"] = "approved"
            count += 1
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="{}件を一括承認しました".format(count)))

@app.route("/bulk_reject")
def bulk_reject():
    ids = request.args.get("ids", "").split(",")
    events = load_events()
    count = 0
    for ev in events:
        if ev["id"] in ids:
            ev["status"] = "rejected"
            count += 1
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="{}件を一括却下しました".format(count)))

@app.route("/bulk_toggle_cat")
def bulk_toggle_cat():
    ids = request.args.get("ids", "").split(",")
    events = load_events()
    count = 0
    for ev in events:
        if ev["id"] in ids:
            current = ev.get("category", "adult")
            if current in ["junior", "ジュニア"]:
                ev["category"] = "adult"
            else:
                ev["category"] = "junior"
            count += 1
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="{}件のカテゴリを変更しました".format(count)))

@app.route("/rebuild")
def rebuild():
    rebuild_html()
    return redirect(url_for("index", msg="HTMLを再生成しました"))

@app.route("/restore_pending/<ev_id>")
def restore_pending(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            ev["status"] = "pending"
            break
    save_events(events)
    return redirect(url_for("index", msg="確認待ちに戻しました"))

@app.route("/add_manual", methods=["POST"])
def add_manual():
    date_str = request.form.get("date", "").strip()
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    category = request.form.get("category", "junior")
    source = request.form.get("source", "").strip()
    
    if not all([date_str, title, url]):
        return redirect(url_for("index", msg="日付・タイトル・URLは必須です"))
    
    events = load_events()
    if not source:
        source = "手動入力"
    
    new_event = {
        "id": "manual_{}_{}".format(datetime.now().strftime("%Y%m%d%H%M%S"), re.sub(r"[^\w]", "_", title[:10])),
        "status": "approved",
        "date": add_weekday(date_str),
        "title": title,
        "url": url,
        "category": category,
        "source": source,
        "direct_link": False,
        "collected_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
    }
    
    events.append(new_event)
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="手動入力で追加して公開しました"))

if __name__ == "__main__":
    print("=" * 60)
    print("🎾 福岡テニス速報 管理画面 v9.0 ULTIMATE")
    print("=" * 60)
    print("データ保存先: {}".format(DATA_DIR))
    print("ブラウザで開いてください: http://localhost:5000")
    print("=" * 60)
    print()
    app.run(debug=False, port=5000)
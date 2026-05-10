"""
福岡テニス速報 管理画面 v10.0 ULTIMATE (完全自動化版)
================================================================
Windows/Linux 完全対応 - CSV一括登録 + 自動収集実行
"""

from flask import Flask, render_template_string, redirect, url_for, request, jsonify
import json
import os
from datetime import datetime, date
from pathlib import Path
import shutil
import csv
import io

app = Flask(__name__)

# --- CONFIG 読み込み ---
def load_config():
    """config.json を読み込む"""
    config_file = "config.json"
    
    if not os.path.exists(config_file):
        default_config = {
            "data_directory": "",
            "sources": [
                {
                    "name": "筑紫野ローンテニスクラブ",
                    "urls": ["https://chikushinotennis.web.fc2.com/"],
                    "auto_collect": True,
                    "parser_type": "fc2_site"
                },
                {
                    "name": "ITS九州",
                    "urls": ["https://its-kyushu.com/"],
                    "auto_collect": True,
                    "parser_type": "wordpress"
                }
            ],
            "scraping": {
                "timeout": 10,
                "retry_count": 3,
                "user_agent": "Mozilla/5.0"
            }
        }
        save_config(default_config)
        return default_config
    
    try:
        with open(config_file, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
            
            # 後方互換性
            if "sources" in config:
                for source in config["sources"]:
                    if "url" in source and "urls" not in source:
                        source["urls"] = [source["url"]]
                        del source["url"]
                    if "auto_collect" not in source:
                        source["auto_collect"] = False
                    if "parser_type" not in source:
                        source["parser_type"] = "generic"
            
            return config
    except Exception as e:
        print(f"警告: config.json読み込みエラー: {e}")
        return {"data_directory": "", "sources": [], "scraping": {}}


def save_config(config):
    """config.json を保存"""
    config_file = "config.json"
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"エラー: config.json保存エラー: {e}")


# --- DATA_DIR 設定 ---
CONFIG = load_config()
PC_PATH = r"C:\Users\tenni\tennis-info"

if CONFIG.get("data_directory") and os.path.exists(CONFIG.get("data_directory")):
    DATA_DIR = Path(CONFIG.get("data_directory"))
elif os.path.exists(PC_PATH):
    DATA_DIR = Path(PC_PATH)
else:
    DATA_DIR = Path(os.getcwd())

DATA_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_FILE = DATA_DIR / "events.json"
PUBLIC_DIR = DATA_DIR / "public"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]


def load_events():
    """events.json を読み込む"""
    if not EVENTS_FILE.exists():
        return []
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"警告: events.json読み込みエラー: {e}")
        return []


def save_events(events):
    """events.json を保存"""
    if EVENTS_FILE.exists():
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / f"events_{timestamp}.json"
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
        print(f"エラー: events.json保存エラー: {e}")


def parse_date_for_sorting(date_str):
    """日付文字列をdate型に変換"""
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
    except Exception:
        return date(2099, 12, 31)


def add_weekday(date_str):
    """日付に曜日を追加"""
    try:
        event_date = parse_date_for_sorting(date_str)
        return f"{event_date.month}/{event_date.day}({WEEKDAY_JP[event_date.weekday()]})"
    except Exception:
        return date_str


def sort_events_by_date(events):
    """イベントを日付順にソート"""
    return sorted(events, key=lambda e: parse_date_for_sorting(e.get("date_display") or e.get("date", "")))


def rebuild_html():
    """tennis_collector.py を呼び出してHTML再生成"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("tc", "tennis_collector.py")
        tc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tc)
        
        approved = [e for e in load_events() if e["status"] == "approved"]
        tc.update_html(approved)
        return True
    except Exception as e:
        print(f"HTML再生成エラー: {e}")
        return False


def run_auto_collect():
    """自動収集を実行"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("tc", "tennis_collector.py")
        tc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tc)
        
        new_events = tc.collect_all_events()
        
        if new_events:
            all_events, added_count = tc.merge_with_existing(new_events)
            tc.save_events(all_events)
            return True, added_count
        else:
            return True, 0
    except Exception as e:
        print(f"自動収集エラー: {e}")
        return False, 0


# --- HTML テンプレート (サイドバー + CSV機能) ---
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>テニス速報 管理画面 v10.0 ULTIMATE</title>
<style>
:root{--main:#FF8C00;--ok:#2E7D32;--ng:#C62828;--blue:#1976D2;--sidebar:#263238;}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#F5F5F5;display:flex;height:100vh;overflow:hidden;}
.sidebar{width:280px;background:var(--sidebar);color:white;display:flex;flex-direction:column;box-shadow:2px 0 10px rgba(0,0,0,0.2);}
.sidebar-header{background:linear-gradient(135deg,var(--main),#FFD700);padding:20px;text-align:center;}
.sidebar-header h1{font-size:18px;margin-bottom:5px;}
.sidebar-header p{font-size:11px;opacity:0.9;}
.stats-mini{padding:15px;background:rgba(255,255,255,0.05);display:flex;gap:15px;justify-content:center;}
.stat-mini{text-align:center;}
.stat-mini .num{font-size:24px;font-weight:bold;}
.stat-mini.pending{color:var(--main);}
.stat-mini.approved{color:#4CAF50;}
.stat-mini .label{font-size:10px;margin-top:3px;opacity:0.8;}
.filter-section{flex:1;overflow-y:auto;padding:10px 0;}
.filter-title{padding:10px 20px;font-size:12px;font-weight:bold;color:#B0BEC5;text-transform:uppercase;letter-spacing:0.5px;}
.filter-item{padding:12px 20px;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;justify-content:space-between;font-size:14px;}
.filter-item:hover{background:rgba(255,255,255,0.1);}
.filter-item.active{background:var(--main);font-weight:bold;}
.filter-item .count{background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:10px;font-size:11px;}
.sidebar-footer{padding:15px;border-top:1px solid rgba(255,255,255,0.1);}
.sidebar-footer .btn{width:100%;padding:12px;border:none;border-radius:6px;font-weight:bold;cursor:pointer;margin-bottom:8px;transition:all 0.3s;font-size:13px;}
.btn-public{background:white;color:var(--main);}
.btn-public:hover{transform:translateY(-2px);box-shadow:0 4px 8px rgba(0,0,0,0.3);}
.btn-rebuild{background:var(--main);color:white;}
.btn-rebuild:hover{background:#E67E00;}
.btn-config{background:var(--blue);color:white;}
.btn-config:hover{background:#1565C0;}
.btn-auto-collect{background:#4CAF50;color:white;}
.btn-auto-collect:hover{background:#388E3C;}
.main-area{flex:1;display:flex;flex-direction:column;overflow:hidden;}
.topbar{background:white;padding:15px 30px;box-shadow:0 2px 6px rgba(0,0,0,0.05);display:flex;align-items:center;justify-content:space-between;}
.topbar h2{font-size:20px;color:#333;}
.bulk-actions{display:flex;gap:10px;align-items:center;}
.bulk-actions label{font-size:14px;display:flex;align-items:center;gap:5px;}
.content-area{flex:1;overflow-y:auto;padding:20px 30px;}
.msg{background:#D4EDDA;color:#155724;border-radius:8px;padding:12px 20px;margin-bottom:15px;text-align:center;font-weight:bold;}
.card{background:white;border-radius:10px;padding:15px;margin-bottom:10px;box-shadow:0 2px 5px rgba(0,0,0,0.07);border-left:4px solid #DDD;transition:all 0.2s;}
.card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.12);}
.card.pending{border-left-color:var(--main);background:#FFF8E1;}
.card.approved{border-left-color:var(--ok);}
.card-top{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;}
.date-badge{background:#FFF3E0;color:var(--main);border-radius:6px;padding:4px 8px;font-weight:bold;font-size:13px;white-space:nowrap;}
.card-title{font-size:14px;font-weight:bold;flex:1;color:#1565C0;}
.card-source{font-size:11px;color:#888;margin-top:3px;}
.actions{display:flex;gap:8px;}
.btn{padding:8px 16px;border:none;border-radius:6px;font-size:13px;font-weight:bold;cursor:pointer;text-decoration:none;display:inline-block;transition:all 0.2s;}
.btn-approve{background:var(--ok);color:white;}
.btn-approve:hover{background:#1B5E20;}
.btn-reject{background:#EEE;color:#555;}
.btn-reject:hover{background:#DDD;}
.btn-edit{background:var(--blue);color:white;}
.btn-edit:hover{background:#1565C0;}
.form-box{background:white;border-radius:10px;padding:25px;box-shadow:0 2px 6px rgba(0,0,0,0.08);max-width:800px;}
.form-box h3{margin-bottom:20px;font-size:20px;color:#333;}
.form-group{margin-bottom:15px;}
.form-group label{display:block;font-size:13px;font-weight:bold;margin-bottom:5px;color:#555;}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:10px;border:2px solid #E0E0E0;border-radius:6px;font-size:14px;font-family:inherit;}
.form-group textarea{resize:vertical;min-height:100px;}
.config-club{background:white;border-radius:8px;padding:15px;margin-bottom:15px;box-shadow:0 2px 4px rgba(0,0,0,0.06);}
.config-club-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}
.config-club-header strong{font-size:16px;color:#333;}
.config-club-urls{padding-left:15px;}
.config-club-urls li{list-style:none;padding:5px 0;color:#666;font-size:13px;word-break:break-all;}
.switch{position:relative;display:inline-block;width:50px;height:24px;margin-left:10px;}
.switch input{opacity:0;width:0;height:0;}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background-color:#ccc;transition:.4s;border-radius:24px;}
.slider:before{position:absolute;content:"";height:18px;width:18px;left:3px;bottom:3px;background-color:white;transition:.4s;border-radius:50%;}
input:checked+.slider{background-color:#4CAF50;}
input:checked+.slider:before{transform:translateX(26px);}
.csv-upload{border:2px dashed #E0E0E0;border-radius:8px;padding:30px;text-align:center;margin:20px 0;background:#F9F9F9;}
.csv-upload input{display:none;}
.csv-upload label{cursor:pointer;color:var(--blue);font-weight:bold;text-decoration:underline;}
</style>
</head>
<body>
<div class="sidebar">
<div class="sidebar-header">
<h1>🎾 テニス速報管理</h1>
<p>v10.0 ULTIMATE - 完全自動化</p>
</div>
<div class="stats-mini">
<div class="stat-mini pending"><div class="num">{{ pending_count }}</div><div class="label">確認待ち</div></div>
<div class="stat-mini approved"><div class="num">{{ approved_count }}</div><div class="label">公開中</div></div>
</div>
<div class="filter-section">
<div class="filter-title">フィルタ</div>
<div class="filter-item active" data-filter="all">
<span>すべて</span><span class="count">{{ pending_count }}</span>
</div>
<div class="filter-item" data-filter="approved">
<span>公開中</span><span class="count">{{ approved_count }}</span>
</div>
<div class="filter-item" data-filter="rejected">
<span>却下済み</span><span class="count">{{ rejected|length }}</span>
</div>
<div class="filter-title" style="margin-top:15px;">主催者別</div>
{% for src in source_names %}
<div class="filter-item" data-filter="source-{{ loop.index0 }}" data-source="{{ src }}">
<span>{{ src }}</span>
<span class="count">{{ pending|selectattr('source', 'equalto', src)|list|length }}</span>
</div>
{% endfor %}
<div class="filter-title" style="margin-top:15px;">その他</div>
<div class="filter-item" data-filter="manual"><span>手動入力</span></div>
<div class="filter-item" data-filter="csv"><span>CSV登録</span></div>
</div>
<div class="sidebar-footer">
<button class="btn btn-auto-collect" onclick="location.href='/auto_collect'">🤖 自動収集実行</button>
<button class="btn btn-public" onclick="window.open('/view_public', '_blank')">📄 公開ページ</button>
<button class="btn btn-rebuild" onclick="location.href='/rebuild'">🔄 HTML再生成</button>
<button class="btn btn-config" onclick="showFilter('config')">⚙️ 設定</button>
</div>
</div>
<div class="main-area">
<div class="topbar">
<h2 id="current-filter-name">すべてのイベント</h2>
<div class="bulk-actions" id="bulk-actions">
<label><input type="checkbox" id="select-all"> 全選択</label>
<button class="btn btn-approve" onclick="bulkApprove()">一括承認</button>
<button class="btn btn-reject" onclick="bulkReject()">一括却下</button>
</div>
</div>
<div class="content-area">
{% if message %}<div class="msg">{{ message }}</div>{% endif %}

<!-- すべて -->
<div class="filter-content" data-filter="all">
{% for ev in pending %}
<div class="card pending" data-source="{{ ev.source }}">
<div class="card-top">
<input type="checkbox" class="card-checkbox" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<div class="card-title">{{ ev.title }}</div>
<div class="card-source">{{ ev.source }}{% if ev.get('auto_collected') %} <span style="color:#4CAF50;">🤖自動</span>{% endif %}</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
</div>
</div>
{% endfor %}
</div>

<!-- 公開中 -->
<div class="filter-content" data-filter="approved" style="display:none;">
{% for ev in approved %}
<div class="card approved">
<div class="card-top">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<div class="card-title">{{ ev.title }}</div>
<div class="card-source">{{ ev.source }}</div>
</div>
</div>
<div class="actions">
<a href="/restore_pending/{{ ev.id }}" class="btn btn-edit">待機に戻す</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">削除</a>
</div>
</div>
{% endfor %}
</div>

<!-- 却下済み -->
<div class="filter-content" data-filter="rejected" style="display:none;">
{% for ev in rejected %}
<div class="card">
<div class="card-top">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<div class="card-title">{{ ev.title }}</div>
<div class="card-source">{{ ev.source }}</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
</div>
</div>
{% endfor %}
</div>

<!-- 主催者別 -->
{% for src in source_names %}
<div class="filter-content" data-filter="source-{{ loop.index0 }}" style="display:none;">
{% for ev in pending if ev.source == src %}
<div class="card pending">
<div class="card-top">
<input type="checkbox" class="card-checkbox" value="{{ ev.id }}">
<span class="date-badge">{{ ev.date }}</span>
<div style="flex:1;">
<div class="card-title">{{ ev.title }}</div>
</div>
</div>
<div class="actions">
<a href="/approve/{{ ev.id }}" class="btn btn-approve">承認</a>
<a href="/reject/{{ ev.id }}" class="btn btn-reject">却下</a>
</div>
</div>
{% endfor %}
</div>
{% endfor %}

<!-- 手動入力 -->
<div class="filter-content" data-filter="manual" style="display:none;">
<div class="form-box">
<h3>📝 手動入力</h3>
<form action="/add_manual" method="post">
<div class="form-group"><label>日付（例: 5/17）</label><input type="text" name="date" required placeholder="5/17"></div>
<div class="form-group"><label>タイトル</label><input type="text" name="title" required></div>
<div class="form-group"><label>URL</label><input type="url" name="url" required></div>
<div class="form-group">
<label>カテゴリ</label>
<select name="category">
<option value="junior">ジュニア</option>
<option value="adult">一般</option>
</select>
</div>
<div class="form-group">
<label>主催者</label>
<input type="text" name="source" list="sources">
<datalist id="sources">
{% for s in source_names %}<option value="{{ s }}">{% endfor %}
</datalist>
</div>
<button type="submit" class="btn btn-approve">追加して公開</button>
</form>
</div>
</div>

<!-- CSV一括登録 -->
<div class="filter-content" data-filter="csv" style="display:none;">
<div class="form-box">
<h3>📊 CSV一括登録</h3>
<p style="color:#666;margin-bottom:20px;font-size:14px;">
CSVファイルから大量のイベントを一括登録できます。<br>
フォーマット: 日付,タイトル,URL,カテゴリ,主催者
</p>
<div class="csv-upload">
<input type="file" id="csv-file" accept=".csv" onchange="handleCSV(this)">
<label for="csv-file">📁 CSVファイルを選択</label>
<p style="margin-top:10px;color:#999;font-size:13px;">または、ここにファイルをドラッグ＆ドロップ</p>
</div>
<div id="csv-preview" style="display:none;margin-top:20px;">
<h4>プレビュー</h4>
<div id="csv-preview-content" style="max-height:300px;overflow:auto;background:#F5F5F5;padding:15px;border-radius:6px;"></div>
<button class="btn btn-approve" onclick="uploadCSV()" style="margin-top:15px;">一括登録を実行</button>
</div>
</div>
</div>

<!-- 設定 -->
<div class="filter-content" data-filter="config" style="display:none;">
<div class="form-box">
<h3>⚙️ 主催者・自動収集設定</h3>
<p style="color:#666;font-size:13px;margin-bottom:25px;">
各主催者の自動収集のオン/オフを切り替えできます。
</p>
{% for s in full_sources %}
<div class="config-club">
<div class="config-club-header">
<div>
<strong>{{ s.name }}</strong>
<label class="switch">
<input type="checkbox" {% if s.get('auto_collect') %}checked{% endif %} onchange="toggleAutoCollect({{ loop.index0 }}, this.checked)">
<span class="slider"></span>
</label>
<span style="font-size:12px;color:#666;margin-left:10px;">自動収集</span>
</div>
<a href="/delete_source/{{ loop.index0 }}" class="btn btn-reject btn-small" onclick="return confirm('削除しますか？')">削除</a>
</div>
<div class="config-club-urls">
{% for url in s.urls %}
<li>{{ loop.index }}. {{ url }}</li>
{% endfor %}
<li style="color:#999;font-size:11px;">パーサー: {{ s.get('parser_type', 'generic') }}</li>
</div>
</div>
{% endfor %}
<h4 style="margin:30px 0 15px;">➕ 新規主催者を追加</h4>
<form action="/add_source" method="post">
<div class="form-group">
<label>主催者名</label>
<input type="text" name="name" required>
</div>
<div class="form-group">
<label>URL（複数の場合は改行）</label>
<textarea name="urls" required></textarea>
</div>
<div class="form-group">
<label>パーサータイプ</label>
<select name="parser_type">
<option value="generic">汎用</option>
<option value="fc2_site">FC2サイト</option>
<option value="wordpress">WordPress</option>
</select>
</div>
<div class="form-group">
<label>
<input type="checkbox" name="auto_collect" checked> 自動収集を有効にする
</label>
</div>
<button type="submit" class="btn btn-edit">追加保存</button>
</form>
</div>
</div>

</div>
</div>

<script>
// フィルタ切り替え
document.querySelectorAll('.filter-item').forEach(item=>{
item.addEventListener('click',()=>{
document.querySelectorAll('.filter-item').forEach(i=>i.classList.remove('active'));
item.classList.add('active');
const filter=item.getAttribute('data-filter');
showFilter(filter);
});
});

function showFilter(filter){
document.querySelectorAll('.filter-content').forEach(c=>c.style.display='none');
const target=document.querySelector(`[data-filter="${filter}"]`);
if(target)target.style.display='block';
const filterItem=document.querySelector(`.filter-item[data-filter="${filter}"]`);
const name=filterItem?filterItem.textContent.trim():filter;
document.getElementById('current-filter-name').textContent=name;
const bulkActions=document.getElementById('bulk-actions');
if(['all','approved','rejected'].includes(filter)||filter.startsWith('source-')){
bulkActions.style.display='flex';
}else{
bulkActions.style.display='none';
}
}

document.getElementById('select-all').addEventListener('change',function(){
document.querySelectorAll('.filter-content:not([style*="display: none"]) .card-checkbox').forEach(cb=>{
cb.checked=this.checked;
});
});

function bulkApprove(){
const ids=Array.from(document.querySelectorAll('.filter-content:not([style*="display: none"]) .card-checkbox:checked')).map(cb=>cb.value);
if(ids.length>0){
window.location.href='/bulk_approve?ids='+ids.join(',');
}else{
alert('選択されていません');
}
}

function bulkReject(){
const ids=Array.from(document.querySelectorAll('.filter-content:not([style*="display: none"]) .card-checkbox:checked')).map(cb=>cb.value);
if(ids.length>0){
window.location.href='/bulk_reject?ids='+ids.join(',');
}else{
alert('選択されていません');
}
}

function toggleAutoCollect(idx, enabled){
fetch(`/toggle_auto_collect/${idx}/${enabled?1:0}`)
.then(r=>r.json())
.then(data=>{
if(data.success){
alert('設定を更新しました');
}
});
}

let csvData = [];
function handleCSV(input){
const file = input.files[0];
if(!file) return;
const reader = new FileReader();
reader.onload = function(e){
const text = e.target.result;
const lines = text.split('\n').filter(l=>l.trim());
csvData = [];
for(let i=1; i<lines.length; i++){
const parts = lines[i].split(',');
if(parts.length >= 5){
csvData.push({
date: parts[0].trim(),
title: parts[1].trim(),
url: parts[2].trim(),
category: parts[3].trim(),
source: parts[4].trim()
});
}
}
let html = '<table border="1" cellpadding="5"><tr><th>日付</th><th>タイトル</th><th>URL</th><th>カテゴリ</th><th>主催者</th></tr>';
csvData.forEach(row=>{
html += `<tr><td>${row.date}</td><td>${row.title}</td><td>${row.url}</td><td>${row.category}</td><td>${row.source}</td></tr>`;
});
html += '</table>';
document.getElementById('csv-preview-content').innerHTML = html;
document.getElementById('csv-preview').style.display = 'block';
};
reader.readAsText(file, 'UTF-8');
}

function uploadCSV(){
if(csvData.length === 0) return alert('CSVデータがありません');
fetch('/upload_csv', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({events: csvData})
}).then(r=>r.json()).then(data=>{
alert(`${data.count}件のイベントを登録しました`);
location.reload();
});
}
</script>
</body>
</html>
"""

# --- ルーティング ---

@app.route("/")
def index():
    events = load_events()
    msg = request.args.get("msg", "")
    config = load_config()
    source_names = [s["name"] for s in config.get("sources", [])]
    
    events = sort_events_by_date(events)
    pending = [e for e in events if e.get("status") == "pending"]
    approved = [e for e in events if e.get("status") == "approved"]
    rejected = [e for e in events if e.get("status") == "rejected"]
    
    return render_template_string(
        ADMIN_TEMPLATE,
        pending=pending,
        approved=approved,
        rejected=rejected,
        pending_count=len(pending),
        approved_count=len(approved),
        message=msg,
        source_names=source_names,
        full_sources=config.get("sources", [])
    )


@app.route("/view_public")
def view_public():
    public_html = PUBLIC_DIR / "index.html"
    if not public_html.exists():
        return "<h1>❌ 公開ページが見つかりません</h1><p>HTML再生成を実行してください</p><a href='/'>← 戻る</a>", 404
    try:
        with open(public_html, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"<h1>エラー</h1><p>{e}</p>", 500


@app.route("/auto_collect")
def auto_collect():
    success, count = run_auto_collect()
    if success:
        return redirect(url_for("index", msg=f"✅ 自動収集完了（{count}件追加）"))
    else:
        return redirect(url_for("index", msg="⚠️ 自動収集に失敗しました"))


@app.route("/add_source", methods=["POST"])
def add_source():
    name = request.form.get("name", "").strip()
    urls_text = request.form.get("urls", "").strip()
    parser_type = request.form.get("parser_type", "generic")
    auto_collect = request.form.get("auto_collect") == "on"
    
    if not name or not urls_text:
        return redirect(url_for("index", msg="⚠️ 名前とURLを入力してください"))
    
    urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
    
    config = load_config()
    if "sources" not in config:
        config["sources"] = []
    
    if any(s["name"] == name for s in config["sources"]):
        return redirect(url_for("index", msg=f"⚠️ 「{name}」は既に登録されています"))
    
    config["sources"].append({
        "name": name,
        "urls": urls,
        "auto_collect": auto_collect,
        "parser_type": parser_type
    })
    save_config(config)
    
    return redirect(url_for("index", msg=f"✅ 「{name}」を追加しました"))


@app.route("/delete_source/<int:idx>")
def delete_source(idx):
    config = load_config()
    if 0 <= idx < len(config.get("sources", [])):
        deleted_name = config["sources"][idx]["name"]
        config["sources"].pop(idx)
        save_config(config)
        return redirect(url_for("index", msg=f"✅ 「{deleted_name}」を削除しました"))
    return redirect(url_for("index", msg="⚠️ 削除に失敗しました"))


@app.route("/toggle_auto_collect/<int:idx>/<int:enabled>")
def toggle_auto_collect(idx, enabled):
    config = load_config()
    if 0 <= idx < len(config.get("sources", [])):
        config["sources"][idx]["auto_collect"] = bool(enabled)
        save_config(config)
        return jsonify({"success": True})
    return jsonify({"success": False})


@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    data = request.get_json()
    events = load_events()
    
    new_events = data.get("events", [])
    for ev in new_events:
        events.append({
            "id": f"csv_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(ev['title']) % 10000}",
            "status": "approved",
            "date": add_weekday(ev["date"]),
            "title": ev["title"],
            "url": ev["url"],
            "category": ev["category"],
            "source": ev["source"],
            "collected_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "csv_uploaded": True
        })
    
    save_events(events)
    rebuild_html()
    
    return jsonify({"success": True, "count": len(new_events)})


@app.route("/approve/<ev_id>")
def approve(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            ev["status"] = "approved"
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="✅ 承認しました"))


@app.route("/reject/<ev_id>")
def reject(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            ev["status"] = "rejected"
    save_events(events)
    rebuild_html()
    return redirect(url_for("index", msg="✅ 却下しました"))


@app.route("/restore_pending/<ev_id>")
def restore_pending(ev_id):
    events = load_events()
    for ev in events:
        if ev["id"] == ev_id:
            ev["status"] = "pending"
    save_events(events)
    return redirect(url_for("index", msg="✅ 確認待ちに戻しました"))


@app.route("/add_manual", methods=["POST"])
def add_manual():
    date_str = request.form.get("date", "").strip()
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    category = request.form.get("category", "junior")
    source = request.form.get("source", "").strip() or "手動入力"
    
    if not date_str or not title or not url:
        return redirect(url_for("index", msg="⚠️ 必須項目を入力してください"))
    
    events = load_events()
    new_event = {
        "id": f"manual_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "status": "approved",
        "date": add_weekday(date_str),
        "title": title,
        "url": url,
        "category": category,
        "source": source,
        "direct_link": True,
        "collected_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
    }
    events.append(new_event)
    save_events(events)
    rebuild_html()
    
    return redirect(url_for("index", msg="✅ 追加しました"))


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
    return redirect(url_for("index", msg=f"✅ {count}件を一括承認しました"))


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
    return redirect(url_for("index", msg=f"✅ {count}件を一括却下しました"))


@app.route("/rebuild")
def rebuild():
    success = rebuild_html()
    if success:
        return redirect(url_for("index", msg="✅ HTMLを再生成しました"))
    else:
        return redirect(url_for("index", msg="⚠️ HTML再生成に失敗しました"))


if __name__ == "__main__":
    print("=" * 70)
    print("🎾 福岡テニス速報 管理画面 v10.0 ULTIMATE")
    print("   完全自動化版 - CSV一括登録 + 自動収集")
    print("=" * 70)
    print(f"📂 データディレクトリ: {DATA_DIR}")
    print(f"📄 events.json: {EVENTS_FILE}")
    print(f"📁 public: {PUBLIC_DIR}")
    print("=" * 70)
    
    config = load_config()
    sources = config.get("sources", [])
    auto_sources = [s for s in sources if s.get("auto_collect")]
    total_urls = sum(len(s.get("urls", [])) for s in sources)
    
    print(f"📋 登録主催者: {len(sources)}件")
    print(f"🤖 自動収集: {len(auto_sources)}件")
    print(f"🌐 総URL数: {total_urls}件")
    print("=" * 70)
    print("🌐 管理画面: http://localhost:5000")
    print("=" * 70)
    
    app.run(debug=False, port=5000)

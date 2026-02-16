"""
IG Tool License Server — Flask API for Vercel
Endpoints:
  POST /api/validate          — App validates license key
  POST /api/activate          — App activates license on machine
  POST /api/trial             — App requests trial license
  GET  /api/health            — Health check
  POST /api/admin/generate    — Admin generates a new key
  GET  /api/admin/keys        — Admin lists all keys
  GET  /api/admin/stats       — Admin dashboard stats
  POST /api/admin/revoke      — Admin revokes a key
  POST /api/admin/extend      — Admin extends a key
  POST /api/admin/delete      — Admin deletes a key
  POST /api/admin/deactivate  — Admin removes a machine from a key
"""

from flask import Flask, request, jsonify, make_response
from upstash_redis import Redis
import os
import json
import uuid
import hashlib
import time
from datetime import datetime

app = Flask(__name__)

# ==================== DASHBOARD HTML (inlined) ====================
DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IG Tool — License Admin</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        :root{
            --bg:#0a0a1a;--card:#141428;--card-border:#1e1e3a;
            --accent:#FF4B4B;--accent-hover:#FF6B6B;
            --success:#4ade80;--warning:#fbbf24;--danger:#f87171;--info:#60a5fa;
            --text:#e0e0e0;--text-dim:#8892b0;--text-muted:#555;
        }
        body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
        #login-screen{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
        .login-card{background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:40px;width:100%;max-width:420px;text-align:center}
        .login-card h1{font-size:28px;margin-bottom:8px}
        .login-card p{color:var(--text-dim);margin-bottom:24px;font-size:14px}
        .login-card input{width:100%;padding:12px 16px;border:2px solid var(--card-border);border-radius:8px;background:#0d0d20;color:var(--text);font-size:14px;outline:none;margin-bottom:16px;transition:.2s}
        .login-card input:focus{border-color:var(--accent)}
        #dashboard{display:none;padding:20px 30px;max-width:1400px;margin:0 auto}
        .dash-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;flex-wrap:wrap;gap:12px}
        .dash-header h1{font-size:24px}
        .dash-header .logout-btn{background:transparent;border:1px solid var(--card-border);color:var(--text-dim);padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;transition:.2s}
        .dash-header .logout-btn:hover{border-color:var(--accent);color:var(--accent)}
        .stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:30px}
        .stat-card{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:20px}
        .stat-card .stat-label{font-size:12px;color:var(--text-dim);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
        .stat-card .stat-value{font-size:28px;font-weight:700}
        .stat-card.green .stat-value{color:var(--success)}
        .stat-card.red .stat-value{color:var(--danger)}
        .stat-card.yellow .stat-value{color:var(--warning)}
        .stat-card.blue .stat-value{color:var(--info)}
        .stat-card.accent .stat-value{color:var(--accent)}
        .section{background:var(--card);border:1px solid var(--card-border);border-radius:12px;padding:24px;margin-bottom:24px}
        .section h2{font-size:18px;margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .form-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
        .form-group{display:flex;flex-direction:column;flex:1;min-width:150px}
        .form-group label{font-size:12px;color:var(--text-dim);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
        .form-group input,.form-group select,.form-group textarea{padding:10px 12px;border:2px solid var(--card-border);border-radius:8px;background:#0d0d20;color:var(--text);font-size:13px;outline:none;transition:.2s}
        .form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--accent)}
        .form-group select{cursor:pointer}
        .btn{padding:10px 20px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:.2s;display:inline-flex;align-items:center;gap:6px}
        .btn-primary{background:var(--accent);color:#fff}
        .btn-primary:hover{background:var(--accent-hover)}
        .btn-success{background:#166534;color:var(--success)}
        .btn-success:hover{background:#15803d}
        .btn-danger{background:#7f1d1d;color:var(--danger)}
        .btn-danger:hover{background:#991b1b}
        .btn-warning{background:#78350f;color:var(--warning)}
        .btn-warning:hover{background:#92400e}
        .btn-info{background:#1e3a5f;color:var(--info)}
        .btn-info:hover{background:#1e4976}
        .btn-sm{padding:6px 12px;font-size:11px}
        .btn-ghost{background:transparent;border:1px solid var(--card-border);color:var(--text-dim)}
        .btn-ghost:hover{border-color:var(--accent);color:var(--accent)}
        .table-wrapper{overflow-x:auto}
        table{width:100%;border-collapse:collapse;font-size:13px}
        th{text-align:left;padding:10px 12px;border-bottom:2px solid var(--card-border);color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:1px;white-space:nowrap}
        td{padding:10px 12px;border-bottom:1px solid #1a1a30;white-space:nowrap}
        tr:hover td{background:rgba(255,75,75,.03)}
        .badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;text-transform:uppercase}
        .badge-active{background:#166534;color:var(--success)}
        .badge-expired{background:#78350f;color:var(--warning)}
        .badge-revoked{background:#7f1d1d;color:var(--danger)}
        .badge-trial{background:#312e81;color:#a5b4fc}
        .badge-basic{background:#1e3a5f;color:var(--info)}
        .badge-pro{background:#4c1d95;color:#c4b5fd}
        .badge-agency{background:#701a75;color:#f0abfc}
        .key-display{font-family:'Courier New',monospace;font-size:14px;background:#0d0d20;padding:12px 16px;border-radius:8px;border:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px}
        .key-display .key-text{color:var(--success);font-weight:700;letter-spacing:1px}
        .key-display .copy-btn{background:var(--accent);color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600}
        .key-display .copy-btn:hover{background:var(--accent-hover)}
        .filters{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
        .filters input{padding:8px 12px;border:2px solid var(--card-border);border-radius:8px;background:#0d0d20;color:var(--text);font-size:13px;outline:none;min-width:200px}
        .filters input:focus{border-color:var(--accent)}
        .filters select{padding:8px 12px;border:2px solid var(--card-border);border-radius:8px;background:#0d0d20;color:var(--text);font-size:13px;outline:none;cursor:pointer}
        .modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center;padding:20px}
        .modal-overlay.show{display:flex}
        .modal{background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:28px;width:100%;max-width:550px;max-height:80vh;overflow-y:auto}
        .modal h3{font-size:18px;margin-bottom:16px}
        .modal .close-modal{float:right;background:none;border:none;color:var(--text-dim);font-size:20px;cursor:pointer;padding:4px}
        .modal .close-modal:hover{color:var(--text)}
        .modal-actions{display:flex;gap:8px;margin-top:16px;justify-content:flex-end}
        .machine-item{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:#0d0d20;border-radius:8px;margin-bottom:8px;font-size:12px}
        .machine-item .machine-info{flex:1}
        .machine-item .machine-hwid{color:var(--text-dim);font-family:monospace;font-size:11px}
        #generated-key-result{display:none;margin-top:16px}
        .toast{position:fixed;bottom:24px;right:24px;background:var(--card);border:1px solid var(--card-border);border-radius:10px;padding:14px 20px;font-size:13px;z-index:2000;animation:slideIn .3s ease;box-shadow:0 8px 32px rgba(0,0,0,.4)}
        .toast.success{border-left:4px solid var(--success)}
        .toast.error{border-left:4px solid var(--danger)}
        @keyframes slideIn{from{transform:translateX(100px);opacity:0}to{transform:translateX(0);opacity:1}}
        .spinner{display:inline-block;width:16px;height:16px;border:2px solid var(--text-dim);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite}
        @keyframes spin{to{transform:rotate(360deg)}}
        @media(max-width:768px){
            #dashboard{padding:12px 16px}
            .stats-grid{grid-template-columns:repeat(2,1fr)}
            .form-row{flex-direction:column}
            .table-wrapper{font-size:12px}
        }
    </style>
</head>
<body>
<div id="login-screen">
    <div class="login-card">
        <h1>&#128274; IG Tool Admin</h1>
        <p>License Management Dashboard</p>
        <input type="password" id="login-password" placeholder="Enter admin password" onkeydown="if(event.key==='Enter')doLogin()">
        <button class="btn btn-primary" style="width:100%" onclick="doLogin()">&#128275; Login</button>
        <p id="login-error" style="color:var(--danger);margin-top:12px;font-size:13px;display:none"></p>
    </div>
</div>
<div id="dashboard">
    <div class="dash-header">
        <h1>&#128202; License Dashboard</h1>
        <div style="display:flex;gap:8px;align-items:center">
            <button class="btn btn-ghost btn-sm" onclick="refreshAll()">&#128260; Refresh</button>
            <button class="dash-header logout-btn" onclick="doLogout()">Logout</button>
        </div>
    </div>
    <div class="stats-grid" id="stats-grid">
        <div class="stat-card"><div class="stat-label">Total Keys</div><div class="stat-value" id="s-total">&mdash;</div></div>
        <div class="stat-card green"><div class="stat-label">Active</div><div class="stat-value" id="s-active">&mdash;</div></div>
        <div class="stat-card yellow"><div class="stat-label">Expired</div><div class="stat-value" id="s-expired">&mdash;</div></div>
        <div class="stat-card red"><div class="stat-label">Revoked</div><div class="stat-value" id="s-revoked">&mdash;</div></div>
        <div class="stat-card accent"><div class="stat-label">Monthly Revenue</div><div class="stat-value" id="s-revenue">&mdash;</div></div>
        <div class="stat-card blue"><div class="stat-label">Active Machines</div><div class="stat-value" id="s-machines">&mdash;</div></div>
    </div>
    <div class="section">
        <h2>&#128273; Generate License Key</h2>
        <div class="form-row">
            <div class="form-group">
                <label>Tier</label>
                <select id="gen-tier">
                    <option value="basic">Basic ($29/mo)</option>
                    <option value="pro" selected>Pro ($49/mo)</option>
                    <option value="agency">Agency ($99/mo)</option>
                    <option value="trial">Trial (Free)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Duration (days)</label>
                <input type="number" id="gen-duration" value="30" min="1" max="365">
            </div>
            <div class="form-group">
                <label>Max Machines (0 = tier default)</label>
                <input type="number" id="gen-machines" value="0" min="0" max="100">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Notes (optional)</label>
                <input type="text" id="gen-notes" placeholder="Customer name, order ID, etc.">
            </div>
        </div>
        <button class="btn btn-primary" onclick="generateKey()" id="gen-btn">&#128273; Generate Key</button>
        <div id="generated-key-result">
            <div class="key-display">
                <span class="key-text" id="gen-key-text"></span>
                <button class="copy-btn" onclick="copyKey()">&#128203; Copy</button>
            </div>
        </div>
    </div>
    <div class="section">
        <h2>&#128203; All License Keys</h2>
        <div class="filters">
            <input type="text" id="filter-search" placeholder="&#128269; Search key, notes..." oninput="filterKeys()">
            <select id="filter-status" onchange="filterKeys()">
                <option value="">All Status</option>
                <option value="active">Active</option>
                <option value="expired">Expired</option>
                <option value="revoked">Revoked</option>
            </select>
            <select id="filter-tier" onchange="filterKeys()">
                <option value="">All Tiers</option>
                <option value="trial">Trial</option>
                <option value="basic">Basic</option>
                <option value="pro">Pro</option>
                <option value="agency">Agency</option>
            </select>
        </div>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Key</th><th>Tier</th><th>Status</th><th>Machines</th>
                        <th>Created</th><th>Expires</th><th>Notes</th><th>Actions</th>
                    </tr>
                </thead>
                <tbody id="keys-tbody"></tbody>
            </table>
        </div>
        <p id="keys-empty" style="text-align:center;color:var(--text-dim);padding:30px;display:none">No license keys found. Generate one above.</p>
    </div>
</div>
<div class="modal-overlay" id="modal-details">
    <div class="modal">
        <button class="close-modal" onclick="closeModal('modal-details')">&times;</button>
        <h3>&#128269; Key Details</h3>
        <div id="modal-details-body"></div>
    </div>
</div>
<div class="modal-overlay" id="modal-extend">
    <div class="modal">
        <button class="close-modal" onclick="closeModal('modal-extend')">&times;</button>
        <h3>&#9200; Extend License</h3>
        <p style="color:var(--text-dim);margin-bottom:16px;font-size:13px">Extending key: <code id="extend-key-display" style="color:var(--accent)"></code></p>
        <div class="form-group" style="margin-bottom:16px">
            <label>Days to Add</label>
            <input type="number" id="extend-days" value="30" min="1" max="365">
        </div>
        <div class="modal-actions">
            <button class="btn btn-ghost" onclick="closeModal('modal-extend')">Cancel</button>
            <button class="btn btn-warning" onclick="doExtend()" id="extend-btn">&#9200; Extend</button>
        </div>
    </div>
</div>
<script>
let API_BASE='';let adminPassword='';let allKeys=[];let currentActionKey='';
function doLogin(){const pw=document.getElementById('login-password').value.trim();if(!pw)return;adminPassword=pw;apiGet('/api/admin/stats').then(r=>{if(r.success){document.getElementById('login-screen').style.display='none';document.getElementById('dashboard').style.display='block';localStorage.setItem('ig_admin_pw',pw);refreshAll()}else{showLoginError('Invalid password')}}).catch(()=>showLoginError('Connection error'))}
function doLogout(){adminPassword='';localStorage.removeItem('ig_admin_pw');document.getElementById('dashboard').style.display='none';document.getElementById('login-screen').style.display='flex';document.getElementById('login-password').value=''}
function showLoginError(msg){const el=document.getElementById('login-error');el.textContent=msg;el.style.display='block';setTimeout(()=>el.style.display='none',3000)}
window.addEventListener('DOMContentLoaded',()=>{const saved=localStorage.getItem('ig_admin_pw');if(saved){adminPassword=saved;apiGet('/api/admin/stats').then(r=>{if(r.success){document.getElementById('login-screen').style.display='none';document.getElementById('dashboard').style.display='block';refreshAll()}}).catch(()=>{})}});
async function apiGet(path){const res=await fetch(API_BASE+path,{headers:{'X-Admin-Password':adminPassword}});return res.json()}
async function apiPost(path,body){const res=await fetch(API_BASE+path,{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Password':adminPassword},body:JSON.stringify(body)});return res.json()}
async function refreshAll(){loadStats();loadKeys()}
async function loadStats(){try{const r=await apiGet('/api/admin/stats');if(r.success){const s=r.stats;document.getElementById('s-total').textContent=s.total_keys;document.getElementById('s-active').textContent=s.active;document.getElementById('s-expired').textContent=s.expired;document.getElementById('s-revoked').textContent=s.revoked;document.getElementById('s-revenue').textContent='$'+s.monthly_revenue;document.getElementById('s-machines').textContent=s.total_machines}}catch(e){toast('Failed to load stats','error')}}
async function loadKeys(){try{const r=await apiGet('/api/admin/keys');if(r.success){allKeys=r.keys;filterKeys()}}catch(e){toast('Failed to load keys','error')}}
function filterKeys(){const search=document.getElementById('filter-search').value.toLowerCase();const status=document.getElementById('filter-status').value;const tier=document.getElementById('filter-tier').value;let filtered=allKeys.filter(k=>{if(search&&!k.key.toLowerCase().includes(search)&&!(k.notes||'').toLowerCase().includes(search))return false;if(status&&k.status!==status)return false;if(tier&&k.tier!==tier)return false;return true});renderKeys(filtered)}
function renderKeys(keys){const tbody=document.getElementById('keys-tbody');const empty=document.getElementById('keys-empty');if(keys.length===0){tbody.innerHTML='';empty.style.display='block';return}empty.style.display='none';tbody.innerHTML=keys.map(k=>'<tr><td><code style="color:var(--accent);font-size:12px">'+k.key+'</code></td><td><span class="badge badge-'+k.tier+'">'+k.tier_name+'</span></td><td><span class="badge badge-'+k.status+'">'+k.status+'</span></td><td>'+k.machine_count+'/'+k.max_machines+'</td><td style="color:var(--text-dim)">'+k.created_at_human+'</td><td style="color:var(--text-dim)">'+k.expires_at_human+'</td><td style="color:var(--text-dim);max-width:120px;overflow:hidden;text-overflow:ellipsis">'+(k.notes||'\u2014')+'</td><td><button class="btn btn-info btn-sm" onclick="showDetails(\''+k.key+'\')" title="Details">&#128269;</button> <button class="btn btn-warning btn-sm" onclick="showExtend(\''+k.key+'\')" title="Extend">&#9200;</button> '+(k.status==='active'?'<button class="btn btn-danger btn-sm" onclick="doRevoke(\''+k.key+'\')" title="Revoke">&#128683;</button> ':'')+(k.status==='revoked'?'<button class="btn btn-success btn-sm" onclick="doUnrevoke(\''+k.key+'\')" title="Re-activate">&#9989;</button> ':'')+'<button class="btn btn-danger btn-sm" onclick="doDelete(\''+k.key+'\')" title="Delete">&#128465;</button></td></tr>').join('')}
async function generateKey(){const btn=document.getElementById('gen-btn');btn.innerHTML='<div class="spinner"></div> Generating...';btn.disabled=true;try{const r=await apiPost('/api/admin/generate',{tier:document.getElementById('gen-tier').value,duration_days:parseInt(document.getElementById('gen-duration').value),max_machines:parseInt(document.getElementById('gen-machines').value),notes:document.getElementById('gen-notes').value});if(r.success){document.getElementById('gen-key-text').textContent=r.key;document.getElementById('generated-key-result').style.display='block';toast('License key generated!','success');refreshAll()}else{toast(r.error||'Failed to generate','error')}}catch(e){toast('Network error','error')}btn.innerHTML='&#128273; Generate Key';btn.disabled=false}
function copyKey(){const key=document.getElementById('gen-key-text').textContent;navigator.clipboard.writeText(key).then(()=>toast('Key copied!','success'))}
function showDetails(key){const k=allKeys.find(x=>x.key===key);if(!k)return;const machines=(k.machines||[]).map(m=>'<div class="machine-item"><div class="machine-info"><div><strong>'+(m.machine_name||'Unknown')+'</strong></div><div class="machine-hwid">'+m.hwid+'</div><div style="color:var(--text-dim);font-size:11px">Activated: '+new Date(m.activated_at*1000).toLocaleString()+'</div></div><button class="btn btn-danger btn-sm" onclick="doDeactivateMachine(\''+key+"','"+m.hwid+'\')">Remove</button></div>').join('')||'<p style="color:var(--text-dim);font-size:13px">No machines activated</p>';document.getElementById('modal-details-body').innerHTML='<div style="margin-bottom:16px"><div style="font-size:12px;color:var(--text-dim)">License Key</div><div style="font-family:monospace;font-size:16px;color:var(--accent);margin:4px 0">'+k.key+'</div></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px"><div><span style="color:var(--text-dim);font-size:12px">Tier</span><br><span class="badge badge-'+k.tier+'">'+k.tier_name+'</span></div><div><span style="color:var(--text-dim);font-size:12px">Status</span><br><span class="badge badge-'+k.status+'">'+k.status+'</span></div><div><span style="color:var(--text-dim);font-size:12px">Created</span><br>'+k.created_at_human+'</div><div><span style="color:var(--text-dim);font-size:12px">Expires</span><br>'+k.expires_at_human+'</div><div><span style="color:var(--text-dim);font-size:12px">Machines</span><br>'+k.machine_count+'/'+k.max_machines+'</div><div><span style="color:var(--text-dim);font-size:12px">Last Validated</span><br>'+(k.last_validated?new Date(k.last_validated*1000).toLocaleString():'Never')+'</div></div>'+(k.notes?'<div style="margin-bottom:16px"><span style="color:var(--text-dim);font-size:12px">Notes</span><br>'+k.notes+'</div>':'')+'<h4 style="font-size:14px;margin-bottom:10px">&#128187; Activated Machines</h4>'+machines;openModal('modal-details')}
function showExtend(key){currentActionKey=key;document.getElementById('extend-key-display').textContent=key;document.getElementById('extend-days').value=30;openModal('modal-extend')}
async function doExtend(){const btn=document.getElementById('extend-btn');btn.innerHTML='<div class="spinner"></div>';btn.disabled=true;try{const r=await apiPost('/api/admin/extend',{key:currentActionKey,days:parseInt(document.getElementById('extend-days').value)});if(r.success){toast(r.message,'success');closeModal('modal-extend');refreshAll()}else{toast(r.error,'error')}}catch(e){toast('Network error','error')}btn.innerHTML='&#9200; Extend';btn.disabled=false}
async function doRevoke(key){if(!confirm('Revoke license '+key+'?'))return;try{const r=await apiPost('/api/admin/revoke',{key});toast(r.success?'License revoked':r.error,r.success?'success':'error');refreshAll()}catch(e){toast('Network error','error')}}
async function doUnrevoke(key){try{const r=await apiPost('/api/admin/extend',{key,days:0});toast(r.success?'License re-activated':r.error,r.success?'success':'error');refreshAll()}catch(e){toast('Network error','error')}}
async function doDelete(key){if(!confirm('PERMANENTLY DELETE license '+key+'?\n\nThis cannot be undone!'))return;try{const r=await apiPost('/api/admin/delete',{key});toast(r.success?'License deleted':r.error,r.success?'success':'error');refreshAll()}catch(e){toast('Network error','error')}}
async function doDeactivateMachine(key,hwid){if(!confirm('Remove this machine from the license?'))return;try{const r=await apiPost('/api/admin/deactivate',{key,hwid});if(r.success){toast('Machine removed','success');closeModal('modal-details');refreshAll()}else{toast(r.error,'error')}}catch(e){toast('Network error','error')}}
function openModal(id){document.getElementById(id).classList.add('show')}
function closeModal(id){document.getElementById(id).classList.remove('show')}
function toast(msg,type){type=type||'success';const el=document.createElement('div');el.className='toast '+type;el.textContent=msg;document.body.appendChild(el);setTimeout(()=>el.remove(),3000)}
document.querySelectorAll('.modal-overlay').forEach(overlay=>{overlay.addEventListener('click',e=>{if(e.target===overlay)closeModal(overlay.id)})});
</script>
</body>
</html>'''

# ==================== CONFIG ====================
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

TIERS = {
    "trial": {
        "name": "Trial",
        "max_machines": 1,
        "features": ["home_feed_warmup"],
        "max_profiles": 1,
        "duration_days": 3,
        "price": 0
    },
    "basic": {
        "name": "Basic",
        "max_machines": 1,
        "features": ["home_feed_warmup", "dm_outreach"],
        "max_profiles": 1,
        "duration_days": 30,
        "price": 29
    },
    "pro": {
        "name": "Pro",
        "max_machines": 3,
        "features": [
            "home_feed_warmup", "reels_warmup", "story_warmup",
            "keyword_search", "profile_visit", "dm_outreach",
            "voice_notes"
        ],
        "max_profiles": 3,
        "duration_days": 30,
        "price": 49
    },
    "agency": {
        "name": "Agency",
        "max_machines": 10,
        "features": [
            "home_feed_warmup", "reels_warmup", "story_warmup",
            "keyword_search", "profile_visit", "dm_outreach",
            "voice_notes", "unlimited_profiles"
        ],
        "max_profiles": 999,
        "duration_days": 30,
        "price": 99
    }
}

# ==================== HELPERS ====================

def get_redis():
    """Get Upstash Redis client"""
    return Redis(
        url=os.environ.get("UPSTASH_REDIS_REST_URL", "").strip(),
        token=os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    )


def generate_key():
    """Generate license key: IGTOOL-XXXX-XXXX-XXXX-XXXX"""
    parts = [uuid.uuid4().hex[:4].upper() for _ in range(4)]
    return f"IGTOOL-{'-'.join(parts)}"


def verify_admin(req):
    """Verify admin password from header or body"""
    password = req.headers.get("X-Admin-Password", "")
    if not password:
        data = req.get_json(silent=True) or {}
        password = data.get("admin_password", "")
    return password == ADMIN_PASSWORD


def cors_response(data, status=200):
    """JSON response with CORS headers"""
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Password"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
    return resp


def get_license(redis, key):
    """Fetch and parse license data from Redis"""
    raw = redis.get(f"license:{key}")
    if not raw:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def save_license(redis, key, data):
    """Save license data to Redis"""
    redis.set(f"license:{key}", json.dumps(data))


# ==================== CORS PREFLIGHT ====================

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Password"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
        return resp


# ==================== APP ENDPOINTS ====================

@app.route("/api/validate", methods=["POST", "OPTIONS"])
def validate_license():
    """Validate a license key from the desktop app"""
    data = request.get_json(silent=True)
    if not data:
        return cors_response({"valid": False, "error": "Invalid request"}, 400)

    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()
    if not key or not hwid:
        return cors_response({"valid": False, "error": "Missing key or hwid"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"valid": False, "error": "Invalid license key"})

    if lic.get("revoked"):
        return cors_response({"valid": False, "error": "License has been revoked"})

    expires_at = lic.get("expires_at", 0)
    if time.time() > expires_at:
        return cors_response({"valid": False, "error": "License has expired"})

    machines = lic.get("machines", [])
    if hwid not in [m["hwid"] for m in machines]:
        return cors_response({"valid": False, "error": "Machine not activated"})

    tier = lic.get("tier", "basic")
    tier_info = TIERS.get(tier, TIERS["basic"])

    lic["last_validated"] = time.time()
    save_license(redis, key, lic)

    return cors_response({
        "valid": True,
        "tier": tier,
        "tier_name": tier_info["name"],
        "features": tier_info["features"],
        "max_profiles": tier_info["max_profiles"],
        "expires_at": expires_at,
        "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/activate", methods=["POST", "OPTIONS"])
def activate_license():
    """Activate a license key on a new machine"""
    data = request.get_json(silent=True)
    if not data:
        return cors_response({"success": False, "error": "Invalid request"}, 400)

    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()
    machine_name = data.get("machine_name", "Unknown")
    if not key or not hwid:
        return cors_response({"success": False, "error": "Missing key or hwid"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Invalid license key"})

    if lic.get("revoked"):
        return cors_response({"success": False, "error": "License has been revoked"})

    expires_at = lic.get("expires_at", 0)
    if time.time() > expires_at:
        return cors_response({"success": False, "error": "License has expired"})

    machines = lic.get("machines", [])
    tier = lic.get("tier", "basic")
    tier_info = TIERS.get(tier, TIERS["basic"])
    max_machines = lic.get("max_machines_override") or tier_info["max_machines"]

    # Already activated on this machine
    for m in machines:
        if m["hwid"] == hwid:
            return cors_response({
                "success": True,
                "message": "Machine already activated",
                "tier": tier,
                "tier_name": tier_info["name"],
                "features": tier_info["features"],
                "max_profiles": tier_info["max_profiles"],
                "expires_at": expires_at
            })

    if len(machines) >= max_machines:
        return cors_response({
            "success": False,
            "error": f"Machine limit reached ({max_machines} max). Deactivate a machine first or upgrade your plan."
        })

    machines.append({
        "hwid": hwid,
        "machine_name": machine_name,
        "activated_at": time.time()
    })
    lic["machines"] = machines
    lic["last_validated"] = time.time()
    save_license(redis, key, lic)

    return cors_response({
        "success": True,
        "message": "Machine activated successfully",
        "tier": tier,
        "tier_name": tier_info["name"],
        "features": tier_info["features"],
        "max_profiles": tier_info["max_profiles"],
        "expires_at": expires_at
    })


@app.route("/api/trial", methods=["POST", "OPTIONS"])
def create_trial():
    """Create a free trial license tied to hardware ID"""
    data = request.get_json(silent=True)
    if not data:
        return cors_response({"success": False, "error": "Invalid request"}, 400)

    hwid = data.get("hwid", "").strip()
    machine_name = data.get("machine_name", "Unknown")
    if not hwid:
        return cors_response({"success": False, "error": "Missing hwid"}, 400)

    redis = get_redis()

    # Check if HWID already used a trial
    existing = redis.get(f"trial_hwid:{hwid}")
    if existing:
        return cors_response({"success": False, "error": "Trial already used on this machine. Please purchase a license."})

    key = generate_key()
    tier_info = TIERS["trial"]
    expires_at = time.time() + (tier_info["duration_days"] * 86400)

    lic = {
        "key": key,
        "tier": "trial",
        "created_at": time.time(),
        "expires_at": expires_at,
        "revoked": False,
        "machines": [{
            "hwid": hwid,
            "machine_name": machine_name,
            "activated_at": time.time()
        }],
        "last_validated": time.time(),
        "notes": "Auto-generated trial"
    }

    save_license(redis, key, lic)
    redis.set(f"trial_hwid:{hwid}", key)
    redis.sadd("all_license_keys", key)

    return cors_response({
        "success": True,
        "key": key,
        "tier": "trial",
        "tier_name": tier_info["name"],
        "features": tier_info["features"],
        "max_profiles": tier_info["max_profiles"],
        "expires_at": expires_at,
        "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
    })


# ==================== ADMIN ENDPOINTS ====================

@app.route("/api/admin/generate", methods=["POST", "OPTIONS"])
def admin_generate():
    """Generate a new license key"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    tier = data.get("tier", "basic")
    duration_days = int(data.get("duration_days", 30))
    max_machines = int(data.get("max_machines", 0))
    notes = data.get("notes", "")

    if tier not in TIERS:
        return cors_response({"success": False, "error": f"Invalid tier: {tier}"}, 400)

    tier_info = TIERS[tier]
    if max_machines <= 0:
        max_machines = tier_info["max_machines"]

    key = generate_key()
    expires_at = time.time() + (duration_days * 86400)

    lic = {
        "key": key,
        "tier": tier,
        "created_at": time.time(),
        "expires_at": expires_at,
        "revoked": False,
        "machines": [],
        "max_machines_override": max_machines if max_machines != tier_info["max_machines"] else None,
        "last_validated": None,
        "notes": notes
    }

    redis = get_redis()
    save_license(redis, key, lic)
    redis.sadd("all_license_keys", key)

    return cors_response({
        "success": True,
        "key": key,
        "tier": tier,
        "tier_name": tier_info["name"],
        "expires_at": expires_at,
        "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S"),
        "max_machines": max_machines
    })


@app.route("/api/admin/keys", methods=["GET", "OPTIONS"])
def admin_list_keys():
    """List all license keys"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    redis = get_redis()
    all_keys = redis.smembers("all_license_keys")

    if not all_keys:
        return cors_response({"success": True, "keys": []})

    keys_data = []
    for key in all_keys:
        lic = get_license(redis, key)
        if not lic:
            continue

        tier = lic.get("tier", "basic")
        tier_info = TIERS.get(tier, TIERS["basic"])
        expires_at = lic.get("expires_at", 0)

        status = "active"
        if lic.get("revoked"):
            status = "revoked"
        elif time.time() > expires_at:
            status = "expired"

        keys_data.append({
            "key": key,
            "tier": tier,
            "tier_name": tier_info["name"],
            "status": status,
            "created_at": lic.get("created_at", 0),
            "created_at_human": datetime.fromtimestamp(lic.get("created_at", 0)).strftime("%Y-%m-%d %H:%M") if lic.get("created_at") else "N/A",
            "expires_at": expires_at,
            "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M") if expires_at else "N/A",
            "machines": lic.get("machines", []),
            "machine_count": len(lic.get("machines", [])),
            "max_machines": lic.get("max_machines_override") or tier_info["max_machines"],
            "last_validated": lic.get("last_validated"),
            "notes": lic.get("notes", "")
        })

    keys_data.sort(key=lambda x: x["created_at"], reverse=True)
    return cors_response({"success": True, "keys": keys_data})


@app.route("/api/admin/stats", methods=["GET", "OPTIONS"])
def admin_stats():
    """Dashboard statistics"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    try:
        redis = get_redis()
        all_keys = redis.smembers("all_license_keys")

        stats = {
            "total_keys": 0, "active": 0, "expired": 0, "revoked": 0,
            "trial": 0, "basic": 0, "pro": 0, "agency": 0,
            "total_machines": 0, "monthly_revenue": 0
        }

        if all_keys:
            stats["total_keys"] = len(all_keys)
            for key in all_keys:
                lic = get_license(redis, key)
                if not lic:
                    continue
                tier = lic.get("tier", "basic")
                stats[tier] = stats.get(tier, 0) + 1
                stats["total_machines"] += len(lic.get("machines", []))

                if lic.get("revoked"):
                    stats["revoked"] += 1
                elif time.time() > lic.get("expires_at", 0):
                    stats["expired"] += 1
                else:
                    stats["active"] += 1
                    stats["monthly_revenue"] += TIERS.get(tier, {}).get("price", 0)

        return cors_response({"success": True, "stats": stats})
    except Exception as e:
        return cors_response({"success": False, "error": f"Server error: {str(e)}"}, 500)


@app.route("/api/admin/revoke", methods=["POST", "OPTIONS"])
def admin_revoke():
    """Revoke a license key"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key:
        return cors_response({"success": False, "error": "Missing key"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Key not found"})

    lic["revoked"] = True
    lic["revoked_at"] = time.time()
    save_license(redis, key, lic)
    return cors_response({"success": True, "message": "License revoked"})


@app.route("/api/admin/extend", methods=["POST", "OPTIONS"])
def admin_extend():
    """Extend a license expiry"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    days = int(data.get("days", 30))
    if not key:
        return cors_response({"success": False, "error": "Missing key"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Key not found"})

    base_time = max(lic.get("expires_at", time.time()), time.time())
    new_expiry = base_time + (days * 86400)
    lic["expires_at"] = new_expiry
    lic["revoked"] = False
    save_license(redis, key, lic)

    return cors_response({
        "success": True,
        "message": f"License extended by {days} days",
        "new_expires_at": new_expiry,
        "new_expires_at_human": datetime.fromtimestamp(new_expiry).strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/admin/delete", methods=["POST", "OPTIONS"])
def admin_delete():
    """Permanently delete a license key"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key:
        return cors_response({"success": False, "error": "Missing key"}, 400)

    redis = get_redis()
    redis.delete(f"license:{key}")
    redis.srem("all_license_keys", key)
    return cors_response({"success": True, "message": "License deleted permanently"})


@app.route("/api/admin/deactivate", methods=["POST", "OPTIONS"])
def admin_deactivate_machine():
    """Remove a machine from a license"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()
    if not key or not hwid:
        return cors_response({"success": False, "error": "Missing key or hwid"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Key not found"})

    lic["machines"] = [m for m in lic.get("machines", []) if m["hwid"] != hwid]
    save_license(redis, key, lic)
    return cors_response({"success": True, "message": "Machine deactivated"})


@app.route("/api/health", methods=["GET", "OPTIONS"])
def health():
    return cors_response({"status": "ok", "service": "IG Tool License Server", "timestamp": time.time()})


@app.route("/api/debug", methods=["GET", "OPTIONS"])
def debug_env():
    """Debug endpoint — check env vars and Redis connectivity"""
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    result = {
        "has_redis_url": bool(url),
        "redis_url_prefix": url[:30] + "..." if len(url) > 30 else url,
        "has_redis_token": bool(token),
        "token_length": len(token),
        "has_admin_pw": bool(os.environ.get("ADMIN_PASSWORD", "")),
    }
    # Test Redis connection
    try:
        redis = get_redis()
        redis.ping()
        result["redis_connected"] = True
    except Exception as e:
        result["redis_connected"] = False
        result["redis_error"] = str(e)
    return cors_response(result)


@app.route("/", methods=["GET"])
def serve_dashboard():
    """Serve the admin dashboard HTML — inlined to avoid file-path issues on Vercel"""
    resp = make_response(DASHBOARD_HTML)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

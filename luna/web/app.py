from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml
from flask import Flask, jsonify, render_template_string, request
from pydantic import ValidationError

from luna.core.config import Settings, _resolve_path, load_config

ALIASES = {
    "runtime.name": ("runtime_name", "name"),
    "runtime.environment": ("runtime_environment", "environment"),
    "runtime.debug": ("runtime_debug", "debug"),
    "models.default": ("models_default", "default"),
    "models.providers": ("models_providers", "providers"),
    "execution.max_steps": ("execution_max_steps", "max_steps"),
    "execution.timeout_seconds": ("execution_timeout_seconds", "timeout_seconds"),
    "execution.workdir": ("execution_workdir", "workdir"),
    "memory.backend": ("memory_backend", "backend"),
    "memory.path": ("memory_path", "path"),
}


PAGE = r"""<!doctype html>
<html lang="pt-BR" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luna Config</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0c0f14;--bg-2:#121720;--panel:#171d28;--panel-2:#1e2533;--border:#2a3344;--border-2:#3a465c;
  --text:#e8ecf4;--muted:#8a97ad;--accent:#ff7a3d;--accent-2:#ffb07a;--ok:#3dd68c;--err:#ff5a6b;--warn:#f6c343;
  --radius:14px;--radius-sm:10px;--shadow:0 18px 40px rgba(0,0,0,.35);
  --ease:cubic-bezier(.2,.7,.2,1);
}
[data-theme="light"]{
  --bg:#f4f6fa;--bg-2:#eef1f7;--panel:#ffffff;--panel-2:#f8f9fc;--border:#d9dfe8;--border-2:#c2cad6;
  --text:#1a2230;--muted:#5b6678;--shadow:0 18px 40px rgba(20,30,60,.12);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:'Space Grotesk',system-ui,-apple-system,sans-serif;
  background:radial-gradient(1200px 600px at 10% -10%,rgba(255,122,61,.10),transparent 60%),radial-gradient(900px 500px at 100% 0%,rgba(61,214,140,.06),transparent 55%),var(--bg);
  color:var(--text);min-height:100vh;transition:background .4s var(--ease),color .2s var(--ease);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;
}
.wrap{max-width:980px;margin:0 auto;padding:32px 20px 64px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:28px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,var(--accent),#ff3d6e);display:grid;place-items:center;font-weight:700;color:#fff;box-shadow:0 8px 20px rgba(255,122,61,.35);font-size:18px}
h1{margin:0;font-size:26px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.btn{appearance:none;border:1px solid var(--border);background:var(--panel);color:var(--text);padding:9px 14px;border-radius:10px;cursor:pointer;font:inherit;font-size:13px;font-weight:500;transition:transform .15s var(--ease),background .2s,border-color .2s,box-shadow .2s;display:inline-flex;align-items:center;gap:8px}
.btn:hover{border-color:var(--border-2);transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn.primary{background:linear-gradient(135deg,var(--accent),#ff5a2a);border-color:transparent;color:#fff;box-shadow:0 10px 22px rgba(255,122,61,.3)}
.btn.primary:hover{box-shadow:0 12px 26px rgba(255,122,61,.4)}
.status-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.pill{background:var(--panel);border:1px solid var(--border);border-radius:999px;padding:6px 12px;font-size:12px;color:var(--muted);display:inline-flex;align-items:center;gap:7px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pill strong{color:var(--text);font-weight:600}
.pill .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px rgba(61,214,140,.15)}

/* cards with scroll reveal (stacking removed: natural flow, no overlap) */
.card{
  background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:0;margin:0 0 20px;
  box-shadow:var(--shadow);overflow:hidden;transition:transform .2s var(--ease),box-shadow .2s var(--ease);
  position:relative;
}
.card:hover{box-shadow:0 22px 46px rgba(0,0,0,.4)}
/* reveal is an enhancement: content stays visible by default, including reduced-motion */
html.js .reveal-card{opacity:1;transform:none}
@media (prefers-reduced-motion: no-preference){
  html.js .reveal-card{opacity:0;transform:translateY(24px);transition:opacity .45s var(--ease),transform .45s var(--ease)}
  html.js .reveal-card.is-visible{opacity:1;transform:none}
}
.card details{padding:0}
summary{list-style:none;cursor:pointer;padding:18px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-weight:600;font-size:15px;user-select:none}
summary::-webkit-details-marker{display:none}
summary .left{display:flex;align-items:center;gap:12px}
.summary-icon{width:30px;height:30px;border-radius:9px;background:var(--panel-2);border:1px solid var(--border);display:grid;place-items:center;font-size:12px;font-weight:700;color:var(--accent);font-family:'JetBrains Mono',monospace}
.chev{transition:transform .25s var(--ease);color:var(--muted)}
details[open] .chev{transform:rotate(180deg)}
details[open] summary{border-bottom:1px solid var(--border)}
.body{padding:20px;display:grid;gap:16px;animation:fadeIn .25s var(--ease)}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.field{display:grid;gap:6px}
.field label{font-size:12.5px;color:var(--muted);font-weight:500;letter-spacing:.02em;text-transform:uppercase}
.field input,.field textarea,.field select{
  width:100%;background:var(--bg-2);border:1px solid var(--border);color:var(--text);
  padding:11px 13px;border-radius:var(--radius-sm);font:inherit;font-size:14px;
  transition:border-color .2s,box-shadow .2s,background .2s;resize:vertical;
}
.field textarea{min-height:96px;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px}
.field input:focus,.field textarea:focus,.field select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,122,61,.18)}
.field .hint{font-size:12px;color:var(--muted)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:640px){.row{grid-template-columns:1fr}}
.check{display:flex;align-items:center;gap:10px;padding:11px 13px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm)}
.check input{width:16px;height:16px;accent-color:var(--accent)}
.check span{font-size:14px}
.footer{display:flex;justify-content:flex-end;gap:12px;align-items:center;margin-top:6px}
.toast{
  position:fixed;top:20px;right:20px;z-index:9999;min-width:240px;max-width:380px;
  background:var(--panel);border:1px solid var(--border);border-left:4px solid var(--accent);
  border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);font-size:13.5px;
  transform:translateX(120%);opacity:0;transition:transform .35s var(--ease),opacity .35s var(--ease);
  display:flex;align-items:center;gap:10px;
}
.toast.show{transform:none;opacity:1}
.toast.ok{border-left-color:var(--ok)}
.toast.err{border-left-color:var(--err)}
.toast .tbtn{margin-left:auto;background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;line-height:1}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12px}

/* waffle app launcher */
.waffle{
  width:40px;height:40px;border-radius:50%;border:1px solid var(--border);background:var(--panel);
  color:var(--text);display:grid;place-items:center;cursor:pointer;padding:0;
  transition:transform .15s var(--ease),border-color .2s,background .2s;
}
.waffle:hover{border-color:var(--border-2);transform:translateY(-1px)}
.waffle-grid{display:grid;grid-template-columns:repeat(3,4px);gap:3px}
.waffle-grid span{width:4px;height:4px;border-radius:50%;background:currentColor}
.app-launcher{
  position:fixed;top:76px;right:20px;width:min(320px,calc(100vw - 24px));
  background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px;
  box-shadow:var(--shadow);z-index:10000;
}
.app-launcher[hidden]{display:none}
.launcher-head{font-weight:600;font-size:13px;color:var(--muted);margin-bottom:10px;letter-spacing:.04em;text-transform:uppercase}
.launcher-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.app-tile{
  appearance:none;border:1px solid var(--border);background:var(--bg-2);color:var(--text);
  border-radius:12px;padding:10px 6px;display:flex;flex-direction:column;align-items:center;gap:6px;
  cursor:pointer;font:inherit;font-size:12px;font-weight:500;transition:transform .15s var(--ease),border-color .2s,background .2s;
}
.app-tile:hover{border-color:var(--accent);transform:translateY(-2px);background:var(--panel-2)}
.app-tile:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,122,61,.18)}
.app-icon{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:var(--panel);border:1px solid var(--border);font-size:12px;font-weight:700;color:var(--accent);font-family:'JetBrains Mono',monospace}
.app-label{font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <img class="logo" src="/static/logo.png" alt="Luna Runtime logo">
      <div>
        <h1>Luna Configuration</h1>
        <div class="sub">Painel de configuração do runtime &middot; edição segura, sem XSS</div>
      </div>
    </div>
    <div class="actions">
      <button class="waffle" id="appLauncherToggle" type="button" aria-label="Abrir launcher de aplicativos" aria-expanded="false" aria-controls="appLauncherPanel" aria-haspopup="dialog">
        <span class="waffle-grid" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span></span>
      </button>
      <button class="btn" id="themeToggle" type="button" aria-label="Alternar tema">Tema</button>
      <a class="btn" href="/health">Health</a>
    </div>
  </header>

  <div id="appLauncherPanel" class="app-launcher" role="dialog" aria-modal="false" aria-label="Aplicativos" hidden>
    <div class="launcher-head">Aplicativos</div>
    <div class="launcher-grid">
      <button class="app-tile" type="button" data-section="runtime"><span class="app-icon">RT</span><span class="app-label">Runtime</span></button>
      <button class="app-tile" type="button" data-section="models"><span class="app-icon">MD</span><span class="app-label">Models</span></button>
      <button class="app-tile" type="button" data-section="agents"><span class="app-icon">AG</span><span class="app-label">Agents</span></button>
      <button class="app-tile" type="button" data-section="execution"><span class="app-icon">EX</span><span class="app-label">Execution</span></button>
      <button class="app-tile" type="button" data-section="memory"><span class="app-icon">MM</span><span class="app-label">Memory</span></button>
    </div>
  </div>

  <div class="status-bar">
    <span class="pill"><span class="dot"></span><strong>Config</strong> <span class="mono" id="configPath">{{ config_path | e }}</span></span>
    <span class="pill"><strong>Providers</strong> <span id="provCount">0</span></span>
  </div>

  <form id="cfgForm" method="post" action="/save" novalidate>
    <div class="card reveal-card" id="section-runtime">
      <details open>
        <summary>
          <span class="left"><span class="summary-icon">RT</span>Runtime</span>
          <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </summary>
        <div class="body">
          <div class="row">
            <div class="field">
              <label for="runtime.name">Nome</label>
              <input id="runtime.name" name="runtime.name" value="{{ v['runtime.name'] | e }}" required>
            </div>
            <div class="field">
              <label for="runtime.environment">Ambiente</label>
              <input id="runtime.environment" name="runtime.environment" value="{{ v['runtime.environment'] | e }}">
            </div>
          </div>
          <div class="check">
            <input type="checkbox" id="runtime.debug" name="runtime.debug" value="true" {% if v['runtime.debug'] %}checked{% endif %}>
            <span>Debug ativado</span>
          </div>
        </div>
      </details>
    </div>

    <div class="card reveal-card" id="section-models">
      <details open>
        <summary>
          <span class="left"><span class="summary-icon">MD</span>Models</span>
          <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </summary>
        <div class="body">
          <div class="field">
            <label for="models.default">Modelo padrao</label>
            <input id="models.default" name="models.default" value="{{ v['models.default'] | e }}" placeholder="ollama/llama3">
          </div>
          <div class="field">
            <label>Providers</label>
            <div id="providersContainer"></div>
            <button class="btn" type="button" id="addProviderBtn">Adicionar provedor</button>
            <input type="hidden" name="providers_json" id="providersJson">
            <textarea id="models.providers" name="models.providers" hidden>{{ v['models.providers'] | e }}</textarea>
            <div class="hint">Cada linha: ID/nome, type, base_url, api_key, api_key_env.</div>
          </div>
        </div>
      </details>
    </div>

    <div class="card reveal-card" id="section-execution">
      <details open>
        <summary>
          <span class="left"><span class="summary-icon">EX</span>Execution</span>
          <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </summary>
        <div class="body">
          <div class="row">
            <div class="field">
              <label for="execution.max_steps">Max steps</label>
              <input type="number" id="execution.max_steps" name="execution.max_steps" min="0" value="{{ v['execution.max_steps'] | e }}">
            </div>
            <div class="field">
              <label for="execution.timeout_seconds">Timeout (s)</label>
              <input type="number" id="execution.timeout_seconds" name="execution.timeout_seconds" min="0" value="{{ v['execution.timeout_seconds'] | e }}">
            </div>
          </div>
          <div class="field">
            <label for="execution.workdir">Workdir</label>
            <input id="execution.workdir" name="execution.workdir" value="{{ v['execution.workdir'] | e }}" placeholder="/tmp/work">
          </div>
        </div>
      </details>
    </div>

    <div class="card reveal-card" id="section-memory">
      <details>
        <summary>
          <span class="left"><span class="summary-icon">MM</span>Memory</span>
          <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </summary>
        <div class="body">
          <div class="row">
            <div class="field">
              <label for="memory.backend">Backend</label>
              <input id="memory.backend" name="memory.backend" value="{{ v['memory.backend'] | e }}" placeholder="sqlite">
            </div>
            <div class="field">
              <label for="memory.path">Path</label>
              <input id="memory.path" name="memory.path" value="{{ v['memory.path'] | e }}" placeholder="/tmp/mem.db">
            </div>
          </div>
        </div>
      </details>
    </div>

    <div class="card reveal-card" id="section-agents">
      <details>
        <summary>
          <span class="left"><span class="summary-icon">AG</span>Agents</span>
          <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </summary>
        <div class="body">
          <div id="agentsContainer"></div>
          <button class="btn" type="button" id="addAgentBtn">Adicionar agente</button>
          <input type="hidden" name="agents_json" id="agentsJson">
          <div class="hint">Cada linha: ID/nome, model id, papel, system prompt, tools, permissions. Separe tools/permissions por virgula.</div>
        </div>
      </details>
    </div>

    <div class="footer">
      <button class="btn" type="reset">Resetar</button>
      <button class="btn primary" type="submit" id="saveBtn">Salvar configuracao</button>
    </div>
  </form>
</div>

<div id="toast" class="toast" role="status" aria-live="polite" hidden>
  <span id="toastMsg"></span>
  <button class="tbtn" id="toastClose" type="button" aria-label="Fechar">X</button>
</div>

<script>
(function(){
  document.documentElement.classList.add('js');
  const root = document.documentElement;
  const toggle = document.getElementById('themeToggle');
  const saved = localStorage.getItem('luna-theme');
  if(saved) root.setAttribute('data-theme', saved);
  function label(){ toggle.textContent = root.getAttribute('data-theme')==='dark' ? 'Tema claro' : 'Tema escuro'; }
  label();
  toggle.addEventListener('click',()=>{ const n = root.getAttribute('data-theme')==='dark'?'light':'dark'; root.setAttribute('data-theme',n); localStorage.setItem('luna-theme',n); label(); });

  // app launcher (waffle menu)
  const launcherToggle = document.getElementById('appLauncherToggle');
  const launcherPanel = document.getElementById('appLauncherPanel');
  let lastFocus = null;
  function openLauncher(){ lastFocus = document.activeElement; launcherPanel.hidden = false; launcherToggle.setAttribute('aria-expanded','true'); const first = launcherPanel.querySelector('.app-tile'); if(first) first.focus(); }
  function closeLauncher(){ launcherPanel.hidden = true; launcherToggle.setAttribute('aria-expanded','false'); if(lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus(); }
  if(launcherToggle && launcherPanel){
    launcherToggle.addEventListener('click', (e)=>{ e.stopPropagation(); if(launcherPanel.hidden) openLauncher(); else closeLauncher(); });
    document.addEventListener('click', (e)=>{ if(!launcherPanel.hidden && !launcherPanel.contains(e.target) && e.target !== launcherToggle){ closeLauncher(); } });
    document.addEventListener('keydown', (e)=>{ if(e.key === 'Escape' && !launcherPanel.hidden){ e.preventDefault(); closeLauncher(); } });
    launcherPanel.querySelectorAll('.app-tile').forEach((tile)=>{
      tile.addEventListener('click', ()=>{
        const id = tile.getAttribute('data-section');
        closeLauncher();
        const el = document.getElementById('section-' + id);
        if(el){ el.scrollIntoView({behavior: prefersReducedMotion ? 'auto' : 'smooth', block:'start'}); try { el.focus({preventScroll:true}); } catch(err) {} }
      });
    });
  }

  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');
  let toastTimer;
  function showToast(msg, kind){
    if(!msg) return;
    toast.classList.remove('ok','err');
    if(kind) toast.classList.add(kind);
    toastMsg.textContent = msg;
    toast.hidden = false;
    requestAnimationFrame(()=>toast.classList.add('show'));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 4200);
  }
  function hideToast(){ toast.classList.remove('show'); setTimeout(()=>{ toast.hidden=true; },350); }
  const toastClose = document.getElementById('toastClose');
  if(toastClose){ toastClose.addEventListener('click', hideToast); }

  const provContainer = document.getElementById('providersContainer');
  const addProviderBtn = document.getElementById('addProviderBtn');
  const initialProviders = {{ (providers or []) | tojson }};
  function addProviderRow(p){
    p = p || {};
    const wrap = document.createElement('div');
    wrap.style.display='grid';
    wrap.style.gap='8px';
    wrap.style.padding='10px 0';
    wrap.style.borderBottom='1px solid var(--border)';
    function esc(v){ return String(v==null?'':v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }
    wrap.innerHTML =
      '<input name="provider_id[]" placeholder="ID/nome" value="' + esc(p.name||p.id||'') + '">' +
      '<input name="provider_type[]" placeholder="type (ollama/openai/...)" value="' + esc(p.type||p.kind||p.provider||'') + '">' +
      '<input name="provider_base_url[]" placeholder="base_url" value="' + esc(p.base_url||p.url||'') + '">' +
      '<input name="provider_api_key[]" placeholder="api_key" value="' + esc(p.api_key||'') + '">' +
      '<input name="provider_api_key_env[]" placeholder="api_key_env" value="' + esc(p.api_key_env||p.env||'') + '">' +
      '<button type="button" class="btn">Remover</button>';
    const removeBtn = wrap.querySelector('button');
    if(removeBtn){ removeBtn.addEventListener('click', ()=>{ wrap.remove(); updateProvCount(); }); }
    if(provContainer){ provContainer.appendChild(wrap); }
    updateProvCount();
  }
  function updateProvCount(){
    const rows = provContainer ? provContainer.querySelectorAll('div').length : 0;
    const el = document.getElementById('provCount');
    if(el) el.textContent = rows;
  }
  initialProviders.forEach(addProviderRow);
  if(addProviderBtn){ addProviderBtn.addEventListener('click', ()=>addProviderRow()); }
  updateProvCount();

  const agentsContainer = document.getElementById('agentsContainer');
  const addAgentBtn = document.getElementById('addAgentBtn');
  const initialAgents = {{ (agents or []) | tojson }};
  function addAgentRow(a){
    a = a || {};
    const wrap = document.createElement('div');
    wrap.style.display='grid';
    wrap.style.gap='8px';
    wrap.style.padding='10px 0';
    wrap.style.borderBottom='1px solid var(--border)';
    function esc(v){ return String(v==null?'':v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }
    wrap.innerHTML =
      '<input name="agent_id[]" placeholder="ID/nome" value="' + esc(a.name||a.id||'') + '">' +
      '<input name="agent_model[]" placeholder="model id" value="' + esc(a.model||'') + '">' +
      '<input name="agent_role[]" placeholder="papel/role" value="' + esc(a.role||'') + '">' +
      '<textarea name="agent_system_prompt[]" placeholder="system prompt">' + esc(a.system_prompt||'') + '</textarea>' +
      '<input name="agent_tools[]" placeholder="tools (virgula)" value="' + esc(Array.isArray(a.tools)?a.tools.join(','): (a.tools||'')) + '">' +
      '<input name="agent_permissions[]" placeholder="permissions (virgula)" value="' + esc(Array.isArray(a.permissions)?a.permissions.join(','): (a.permissions||'')) + '">' +
      '<button type="button" class="btn">Remover</button>';
    const removeBtn = wrap.querySelector('button');
    if(removeBtn){ removeBtn.addEventListener('click', ()=>wrap.remove()); }
    if(agentsContainer){ agentsContainer.appendChild(wrap); }
  }
  initialAgents.forEach(addAgentRow);
  if(addAgentBtn){ addAgentBtn.addEventListener('click', ()=>addAgentRow()); }

  const form = document.getElementById('cfgForm');
  const btn = document.getElementById('saveBtn');
  if(form){
    form.addEventListener('submit', (e)=>{
      const provJsonEl = document.getElementById('providersJson');
      const pc = document.getElementById('providersContainer');
      if(provJsonEl && pc){
        const arr = [];
        Array.from(pc.children).forEach((wrap)=>{
          function val(nm){ const el = wrap.querySelector('input[name=\"'+nm+'\"]'); return el ? el.value : ''; }
          arr.push({
            id: val('provider_id[]'),
            type: val('provider_type[]'),
            base_url: val('provider_base_url[]'),
            api_key: val('provider_api_key[]'),
            api_key_env: val('provider_api_key_env[]')
          });
        });
        provJsonEl.value = JSON.stringify(arr);
      }
      const name = form.querySelector('[name="runtime.name"]').value.trim();
      const ms = form.querySelector('[name="execution.max_steps"]').value.trim();
      const ts = form.querySelector('[name="execution.timeout_seconds"]').value.trim();
      if(!name){ e.preventDefault(); showToast('Nome do runtime e obrigatorio.','err'); return; }
      if(ms && !/^-?\d+$/.test(ms)){ e.preventDefault(); showToast('Max steps deve ser numero inteiro.','err'); return; }
      if(ts && !/^-?\d+$/.test(ts)){ e.preventDefault(); showToast('Timeout deve ser numero inteiro.','err'); return; }
      btn.disabled = true;
      btn.textContent = 'Salvando...';
    });
  }

  // scroll reveal (IntersectionObserver only; safe, visible-by-default fallback)
  const prefersReducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const revealEls = document.querySelectorAll('.reveal-card');
  if(prefersReducedMotion){
    revealEls.forEach((el)=>el.classList.add('is-visible'));
  } else if('IntersectionObserver' in window){
    const io = new IntersectionObserver((entries)=>{
      entries.forEach((en)=>{ if(en.isIntersecting){ en.target.classList.add('is-visible'); io.unobserve(en.target); } });
    }, {threshold:0, rootMargin:'0px 0px -8% 0px'});
    revealEls.forEach((el)=>io.observe(el));
    // make anything already in view visible immediately
    revealEls.forEach((el)=>{
      const r = el.getBoundingClientRect();
      if(r.top < window.innerHeight * 0.92 && r.bottom > 0){ el.classList.add('is-visible'); }
    });
  } else {
    revealEls.forEach((el)=>el.classList.add('is-visible'));
  }

  const msg = {{ message | tojson }};
  const errors = {% if errors %}{{ errors | tojson }}{% else %}[]{% endif %};
  if(msg){ showToast(msg, msg==='saved'?'ok':''); }
  if(Array.isArray(errors) && errors.length){
    showToast(errors.join(' | '), 'err');
  }
})();
</script>
</body></html>"""



def _get(form: Any, key: str) -> str | None:
    if key in form:
        return form.get(key)
    for alias in ALIASES.get(key, ()):
        if alias in form:
            return form.get(alias)
    return None


def _resolve_config_path(config_path) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser()
    return _resolve_path(None)


def _settings_to_values(settings: Settings) -> dict[str, Any]:
    return {
        "runtime.name": settings.runtime.name,
        "runtime.environment": settings.runtime.environment,
        "runtime.debug": settings.runtime.debug,
        "models.default": settings.models.default,
        "models.providers": "\n".join(
            (str(p.get("name") or p.get("id")) if isinstance(p, dict) else str(p))
            for p in settings.models.providers
            if (str(p.get("name") or p.get("id")) if isinstance(p, dict) else str(p)).strip()
        ),
        "execution.max_steps": settings.execution.max_steps,
        "execution.timeout_seconds": settings.execution.timeout_seconds,
        "execution.workdir": settings.execution.workdir or "",
        "memory.backend": settings.memory.backend,
        "memory.path": settings.memory.path or "",
    }


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    val = str(value).strip().lower()
    return val in ("1", "true", "yes", "on")


def _parse_providers(text: Any) -> list[str]:
    if text is None:
        return []
    if isinstance(text, list):
        return [str(x).strip() for x in text if str(x).strip()]
    return [p.strip() for p in re.split(r"[\n,]", str(text)) if p.strip()]


def _parse_list(text: Any) -> list[Any]:
    if text is None:
        return []
    if isinstance(text, list):
        return [x for x in text]
    val = str(text).strip()
    if not val:
        return []
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return [p.strip() for p in re.split(r"[\n,]", val) if p.strip()]


def create_app(config_path=None) -> Flask:
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).resolve().parents[2] / "assets"),
        static_url_path="/static",
    )
    resolved = _resolve_config_path(config_path)

    def _load_values() -> tuple[dict[str, Any], list[str]]:
        errors: list[str] = []
        try:
            settings = load_config(resolved)
        except Exception as exc:
            settings = Settings()
            if resolved.exists():
                errors.append(str(exc))
        return _settings_to_values(settings), errors

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "luna-web"})

    @app.get("/")
    def index():
        values, errors = _load_values()
        # allow query overrides? no
        agents = []
        providers = []
        try:
            settings = load_config(resolved)
            agents = [a.model_dump() for a in settings.agents]
            providers = [p if isinstance(p, dict) else {"name": p, "id": p} for p in settings.models.providers]
        except Exception:
            agents = []
            providers = []
        return render_template_string(PAGE, v=values, errors=errors, message=None, config_path=str(resolved), agents=agents, providers=providers)

    @app.post("/save")
    def save():
        form = request.form
        errors: list[str] = []

        def raw(key):
            return _get(form, key)

        def present(key):
            if key in form:
                return True
            return any(alias in form for alias in ALIASES.get(key, ()))

        runtime_name = raw("runtime.name")
        runtime_environment = raw("runtime.environment")
        runtime_debug_present = present("runtime.debug")
        runtime_debug_raw = _parse_bool(raw("runtime.debug")) if runtime_debug_present else None
        models_default = raw("models.default")
        models_providers = raw("models.providers")
        execution_max_steps = raw("execution.max_steps")
        execution_timeout_seconds = raw("execution.timeout_seconds")
        execution_workdir = raw("execution.workdir")
        memory_backend = raw("memory.backend")
        memory_path = raw("memory.path")
        agents_json_raw = raw("agents") or raw("agents_json")
        values = {
            "runtime.name": runtime_name if runtime_name is not None else "",
            "runtime.environment": runtime_environment if runtime_environment is not None else "",
            "runtime.debug": runtime_debug_raw if runtime_debug_raw is not None else False,
            "models.default": models_default if models_default is not None else "",
            "models.providers": models_providers if models_providers is not None else "",
            "execution.max_steps": execution_max_steps if execution_max_steps is not None else "",
            "execution.timeout_seconds": execution_timeout_seconds if execution_timeout_seconds is not None else "",
            "execution.workdir": execution_workdir if execution_workdir is not None else "",
            "memory.backend": memory_backend if memory_backend is not None else "",
            "memory.path": memory_path if memory_path is not None else "",
        }

        # load existing raw config to preserve permissions/extras
        existing: dict[str, Any] = {}
        if resolved.exists():
            try:
                loaded = yaml.safe_load(resolved.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = copy.deepcopy(loaded)
            except Exception:
                existing = {}
        data = copy.deepcopy(existing)

        runtime_section = data.setdefault("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            data["runtime"] = runtime_section
        models_section = data.setdefault("models", {})
        if not isinstance(models_section, dict):
            models_section = {}
            data["models"] = models_section
        execution_section = data.setdefault("execution", {})
        if not isinstance(execution_section, dict):
            execution_section = {}
            data["execution"] = execution_section
        memory_section = data.setdefault("memory", {})
        if not isinstance(memory_section, dict):
            memory_section = {}
            data["memory"] = memory_section

        # merge only submitted form fields
        if present("runtime.name") and runtime_name is not None:
            runtime_section["name"] = runtime_name
        if present("runtime.environment") and runtime_environment is not None:
            runtime_section["environment"] = runtime_environment
        if runtime_debug_present:
            runtime_section["debug"] = runtime_debug_raw if runtime_debug_raw is not None else False
        if present("models.default") and models_default is not None:
            models_section["default"] = models_default
        # providers handling (dynamic rows + hidden json + legacy text)
        provider_id_lists = []
        for candidate in ("provider_id[]", "provider_name[]", "provider[]", "providers_id[]", "providers_name[]"):
            vals = request.form.getlist(candidate) if hasattr(request.form, "getlist") else []
            if vals:
                provider_id_lists.append(vals)
        provider_type_lists = []
        for candidate in ("provider_type[]", "provider_kind[]"):
            vals = request.form.getlist(candidate) if hasattr(request.form, "getlist") else []
            if vals:
                provider_type_lists.append(vals)
        provider_base_lists = []
        for candidate in ("provider_base_url[]", "provider_url[]", "provider_base[]"):
            vals = request.form.getlist(candidate) if hasattr(request.form, "getlist") else []
            if vals:
                provider_base_lists.append(vals)
        provider_key_lists = []
        for candidate in ("provider_api_key[]", "provider_key[]", "provider_apikey[]"):
            vals = request.form.getlist(candidate) if hasattr(request.form, "getlist") else []
            if vals:
                provider_key_lists.append(vals)
        provider_env_lists = []
        for candidate in ("provider_api_key_env[]", "provider_env[]", "provider_apikey_env[]"):
            vals = request.form.getlist(candidate) if hasattr(request.form, "getlist") else []
            if vals:
                provider_env_lists.append(vals)

        if provider_id_lists or provider_type_lists or provider_base_lists or provider_key_lists or provider_env_lists:
            ids = provider_id_lists[0] if provider_id_lists else []
            types = provider_type_lists[0] if provider_type_lists else []
            bases = provider_base_lists[0] if provider_base_lists else []
            keys = provider_key_lists[0] if provider_key_lists else []
            envs = provider_env_lists[0] if provider_env_lists else []
            n = max(len(ids), len(types), len(bases), len(keys), len(envs), 0)
            new_providers = []
            for i in range(n):
                raw_id = ids[i] if i < len(ids) else ""
                pid = str(raw_id).strip() if raw_id is not None else ""
                if not pid:
                    # allow rows identified only by other fields
                    if not any(str((vals[i] if i < len(vals) else "")).strip() for vals in (types, bases, keys, envs)):
                        continue
                    pid = f"provider-{i+1}"
                t = types[i] if i < len(types) else ""
                b = bases[i] if i < len(bases) else ""
                k = keys[i] if i < len(keys) else ""
                e = envs[i] if i < len(envs) else ""
                new_providers.append(
                    {
                        "id": pid,
                        "name": pid,
                        "type": (str(t).strip() if t is not None else ""),
                        "base_url": (str(b).strip() if b is not None else ""),
                        "api_key": (str(k).strip() if k is not None else ""),
                        "api_key_env": (str(e).strip() if e is not None else ""),
                    }
                )
            models_section["providers"] = new_providers
        else:
            providers_json_raw = raw("providers_json") or raw("providers_json")
            # also accept models.providers hidden json? 
            if isinstance(providers_json_raw, str) and providers_json_raw.strip().startswith(("[", "{")):
                parsed = None
                try:
                    parsed = json.loads(providers_json_raw)
                except Exception:
                    try:
                        import yaml as _y

                        parsed = _y.safe_load(providers_json_raw)
                    except Exception:
                        parsed = None
                if isinstance(parsed, list):
                    models_section["providers"] = parsed
                elif isinstance(parsed, dict) and "providers" in parsed:
                    models_section["providers"] = parsed.get("providers") or []
            elif present("models.providers") and models_providers is not None:
                models_section["providers"] = _parse_providers(models_providers)
        if present("execution.max_steps"):
            try:
                max_steps_int = int(str(execution_max_steps).strip()) if str(execution_max_steps).strip() != "" else 0
            except (TypeError, ValueError):
                max_steps_int = None
            execution_section["max_steps"] = max_steps_int
        if present("execution.timeout_seconds"):
            try:
                timeout_int = int(str(execution_timeout_seconds).strip()) if str(execution_timeout_seconds).strip() != "" else 0
            except (TypeError, ValueError):
                timeout_int = None
            execution_section["timeout_seconds"] = timeout_int
        if present("execution.workdir"):
            execution_section["workdir"] = (
                execution_workdir.strip()
                if isinstance(execution_workdir, str) and execution_workdir.strip()
                else None
            )
        if present("memory.backend") and memory_backend is not None:
            memory_section["backend"] = memory_backend
        if present("memory.path"):
            memory_section["path"] = (
                memory_path.strip()
                if isinstance(memory_path, str) and memory_path.strip()
                else None
            )

        # agents handling
        _agent_ids = []
        try:
            _agent_ids = request.form.getlist("agent_id[]") or request.form.getlist("agents_id[]")
        except Exception:
            _agent_ids = []
        _agent_models = request.form.getlist("agent_model[]") if hasattr(request.form, "getlist") else []
        _agent_roles = request.form.getlist("agent_role[]") if hasattr(request.form, "getlist") else []
        _agent_prompts = request.form.getlist("agent_system_prompt[]") if hasattr(request.form, "getlist") else []
        _agent_tools = request.form.getlist("agent_tools[]") if hasattr(request.form, "getlist") else []
        _agent_perms = request.form.getlist("agent_permissions[]") if hasattr(request.form, "getlist") else []

        if _agent_ids:
            new_agents = []
            for i, aid in enumerate(_agent_ids):
                if not str(aid).strip():
                    continue
                tools_raw = _agent_tools[i] if i < len(_agent_tools) else ""
                perms_raw = _agent_perms[i] if i < len(_agent_perms) else ""
                new_agents.append(
                    {
                        "name": str(aid).strip(),
                        "id": str(aid).strip(),
                        "model": (_agent_models[i].strip() if i < len(_agent_models) and _agent_models[i] is not None else "default") or "default",
                        "role": (_agent_roles[i].strip() if i < len(_agent_roles) and _agent_roles[i] is not None else ""),
                        "system_prompt": (_agent_prompts[i] if i < len(_agent_prompts) else "") or "",
                        "tools": _parse_list(tools_raw),
                        "permissions": _parse_list(perms_raw),
                    }
                )
            data["agents"] = new_agents
        elif agents_json_raw:
            parsed = None
            try:
                parsed = json.loads(agents_json_raw)
            except Exception:
                try:
                    import yaml as _y

                    parsed = _y.safe_load(agents_json_raw)
                except Exception:
                    parsed = None
            if isinstance(parsed, list):
                data["agents"] = parsed
            elif isinstance(parsed, dict) and "agents" in parsed:
                data["agents"] = parsed.get("agents") or []

        try:
            settings = Settings.model_validate(data)
        except (ValidationError, ValueError, TypeError) as exc:
            errors.append(str(exc))
            return render_template_string(PAGE, v=values, errors=errors, message=None, config_path=str(resolved), agents=[], providers=[]), 400

        # build output preserving extras/permissions
        out = copy.deepcopy(data)
        for section_key in ("runtime", "models", "permissions", "memory", "execution"):
            if section_key not in out or not isinstance(out.get(section_key), dict):
                out[section_key] = {}
            section_obj = getattr(settings, section_key)
            for k, v in section_obj.model_dump().items():
                out[section_key][k] = v

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
        agents = [a.model_dump() for a in settings.agents]
        providers = [p if isinstance(p, dict) else {"name": p, "id": p} for p in settings.models.providers]
        return render_template_string(PAGE, v=_settings_to_values(settings), errors=[], message="saved", config_path=str(resolved), agents=agents, providers=providers)

    return app


__all__ = ["create_app"]
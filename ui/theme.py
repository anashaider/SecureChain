"""
Visual theme of the SecureChain command center.

One block of CSS, injected once per run by `apply_theme()`. Base colours
come from .streamlit/config.toml; this file adds the design system:

  * layered dark background with a faint technical grid
  * glass cards (translucent, blurred, soft glowing border on hover)
  * animated KPI counters, gauges, timelines and step flows (pure CSS)
  * restyled Streamlit widgets (sidebar menu, buttons, inputs, tabs...)

All animations use only `transform` and `opacity` (GPU-friendly) and are
switched off automatically when the visitor prefers reduced motion.
"""

import streamlit as st

# Colour palette (also used by Python code that builds charts)
ACCENT = "#22d3ee"   # electric cyan - primary
BLUE = "#3b82f6"
PURPLE = "#8b5cf6"
OK = "#34d399"       # green  - verified / success
WARN = "#fbbf24"     # amber  - flagged / warning
BAD = "#f87171"      # red    - rejected / invalid
MUTED = "#8a9bb8"
TEXT = "#e2e8f0"
BORDER = "rgba(56, 189, 248, 0.16)"

SEVERITY_COLORS = {"LOW": ACCENT, "MEDIUM": WARN, "HIGH": "#fb923c", "CRITICAL": BAD}

_CSS = """
<style>
@property --sc-n { syntax: "<integer>"; initial-value: 0; inherits: false; }
@property --sc-p { syntax: "<number>"; initial-value: 0; inherits: false; }

:root {
  --sc-cyan: #22d3ee; --sc-blue: #3b82f6; --sc-purple: #8b5cf6;
  --sc-ok: #34d399; --sc-warn: #fbbf24; --sc-bad: #f87171;
  --sc-text: #e2e8f0; --sc-muted: #8a9bb8; --sc-dim: #5b6b88;
  --sc-stroke: rgba(56, 189, 248, 0.16);
  --sc-glass: linear-gradient(160deg, rgba(20, 32, 58, 0.62) 0%, rgba(9, 15, 30, 0.58) 100%);
  --sc-mono: "JetBrains Mono", "Cascadia Code", "Cascadia Mono", Consolas, monospace;
  --sc-ease: cubic-bezier(.2, .8, .2, 1);
}

/* ================= app shell ================= */
[data-testid="stApp"] {
  background-color: #04070e;
  background-image:
    radial-gradient(1100px 560px at 10% -10%, rgba(34, 211, 238, 0.11), transparent 60%),
    radial-gradient(1000px 640px at 100% -5%, rgba(139, 92, 246, 0.11), transparent 58%),
    radial-gradient(900px 600px at 55% 115%, rgba(59, 130, 246, 0.10), transparent 60%),
    linear-gradient(rgba(56, 189, 248, 0.028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.028) 1px, transparent 1px);
  background-size: auto, auto, auto, 46px 46px, 46px 46px;
  background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stMainBlockContainer"] { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1320px; }
::selection { background: rgba(34, 211, 238, 0.3); }
* { scrollbar-width: thin; scrollbar-color: rgba(56, 189, 248, 0.28) transparent; }

/* page transition: every page lives in a container whose key changes with the page */
[class*="st-key-page-"] { animation: sc-page .5s var(--sc-ease) both; }
@keyframes sc-page { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes sc-rise { from { opacity: 0; transform: translateY(12px) scale(.985); } to { opacity: 1; transform: none; } }
@keyframes sc-slide { from { opacity: 0; transform: translateX(-14px); } to { opacity: 1; transform: none; } }
@keyframes sc-pulse { 0% { box-shadow: 0 0 0 0 rgba(34, 211, 238, .55); } 70% { box-shadow: 0 0 0 9px rgba(34, 211, 238, 0); } 100% { box-shadow: 0 0 0 0 rgba(34, 211, 238, 0); } }
@keyframes sc-pulse-bad { 0% { box-shadow: 0 0 0 0 rgba(248, 113, 113, .6); } 70% { box-shadow: 0 0 0 9px rgba(248, 113, 113, 0); } 100% { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0); } }
@keyframes sc-count { from { --sc-n: 0; } to { --sc-n: var(--to); } }
@keyframes sc-gauge { from { --sc-p: 0; } to { --sc-p: var(--to); } }
@keyframes sc-sheen { from { transform: translateX(-120%); } to { transform: translateX(220%); } }
@keyframes sc-flow { to { background-position: -200% 0; } }
@keyframes sc-shake { 10%, 90% { transform: translateX(-1px); } 30%, 70% { transform: translateX(3px); } 50% { transform: translateX(-4px); } }
@keyframes sc-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

/* ================= sidebar ================= */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(8, 13, 26, 0.86), rgba(4, 7, 14, 0.9));
  backdrop-filter: blur(18px) saturate(140%); -webkit-backdrop-filter: blur(18px) saturate(140%);
  border-right: 1px solid var(--sc-stroke);
}
[data-testid="stSidebarContent"] { background: transparent; }
.sc-brand { display: flex; align-items: center; gap: .8rem; margin: 0 0 1.2rem 0; }
.sc-brand-logo {
  position: relative; width: 44px; height: 44px; border-radius: 13px; flex: none;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
  background: linear-gradient(135deg, #22d3ee 0%, #3b82f6 55%, #8b5cf6 100%);
  color: #04101c; font-weight: 800; font-size: 1.02rem; letter-spacing: -.02em;
  box-shadow: 0 0 24px rgba(34, 211, 238, .35), inset 0 1px 0 rgba(255, 255, 255, .35);
}
.sc-brand-logo::after {
  content: ""; position: absolute; inset: 0; width: 40%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .55), transparent);
  animation: sc-sheen 4.5s ease-in-out infinite;
}
.sc-brand-name { font-size: 1.22rem; font-weight: 700; line-height: 1.1; color: #f1f5f9; letter-spacing: -.01em; }
.sc-brand-tag { font-size: .66rem; color: var(--sc-muted); letter-spacing: .16em; text-transform: uppercase; margin-top: 2px; }

/* navigation: the radio group is restyled as a menu with an animated indicator */
[data-testid="stSidebar"] [data-testid="stRadio"], [data-testid="stSidebar"] [data-testid="stRadio"] > div { width: 100%; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: .12rem; width: 100%; align-items: stretch; }
[data-testid="stSidebar"] label[data-testid="stRadioOption"] {
  position: relative; display: flex; width: 100%; max-width: none; box-sizing: border-box; margin: 0; padding: .5rem .8rem; border-radius: 11px; cursor: pointer;
  border: 1px solid transparent; transition: background .2s, border-color .2s, transform .2s var(--sc-ease);
}
[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child { display: none; }
[data-testid="stSidebar"] label[data-testid="stRadioOption"] p { color: #b6c2d6; font-size: .93rem; transition: color .2s; }
[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover { background: rgba(34, 211, 238, .06); transform: translateX(3px); }
[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover p { color: #f1f5f9; }
[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {
  background: linear-gradient(90deg, rgba(34, 211, 238, .17), rgba(59, 130, 246, .05) 70%, transparent);
  border-color: rgba(34, 211, 238, .26);
}
[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p { color: #e6fbff; font-weight: 600; }
[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"]::before {
  content: ""; position: absolute; left: -1px; top: 20%; bottom: 20%; width: 3px; border-radius: 3px;
  background: var(--sc-cyan); box-shadow: 0 0 12px var(--sc-cyan); transform-origin: center;
  animation: sc-nav .4s var(--sc-ease) both;
}
@keyframes sc-nav { from { transform: scaleY(0); opacity: 0; } to { transform: scaleY(1); opacity: 1; } }

.sc-status {
  display: flex; align-items: center; gap: .6rem; padding: .6rem .8rem; border-radius: 11px;
  font-size: .82rem; font-weight: 600; border: 1px solid;
}
.sc-status.ok { color: var(--sc-ok); background: rgba(52, 211, 153, .07); border-color: rgba(52, 211, 153, .32); }
.sc-status.bad { color: var(--sc-bad); background: rgba(248, 113, 113, .09); border-color: rgba(248, 113, 113, .45); animation: sc-shake .5s; }
.sc-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex: none; animation: sc-pulse 2.2s infinite; }
.sc-status.bad .sc-dot { animation-name: sc-pulse-bad; }
.sc-side-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: .4rem; margin-top: .6rem; }
.sc-side-meta div { padding: .4rem .5rem; border-radius: 9px; background: rgba(13, 22, 40, .6); border: 1px solid var(--sc-stroke); text-align: center; }
.sc-side-meta b { display: block; font-size: .98rem; color: #f1f5f9; font-variant-numeric: tabular-nums; }
.sc-side-meta span { font-size: .6rem; letter-spacing: .12em; text-transform: uppercase; color: var(--sc-dim); }
.sc-side-tip { font-size: .72rem; color: var(--sc-dim); margin-top: .55rem; }

/* ================= headings ================= */
.sc-header { margin-bottom: 1.3rem; }
.sc-eyebrow {
  display: inline-flex; align-items: center; gap: .5rem; font-size: .68rem; font-weight: 600;
  letter-spacing: .2em; text-transform: uppercase; color: var(--sc-cyan);
}
.sc-eyebrow::before { content: ""; width: 22px; height: 1px; background: var(--sc-cyan); box-shadow: 0 0 8px var(--sc-cyan); }
.sc-header h1 {
  font-size: 2.05rem; font-weight: 700; margin: .25rem 0 0 0; padding: 0; letter-spacing: -.02em;
  background: linear-gradient(90deg, #f8fafc 0%, #c7e9f7 55%, #a5b4fc 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.sc-header p { margin: .35rem 0 0 0; color: var(--sc-muted); font-size: .97rem; max-width: 760px; }
.sc-section {
  display: flex; align-items: center; gap: .7rem; margin: 1.5rem 0 .7rem 0;
  font-size: .72rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase; color: var(--sc-muted);
}
.sc-section::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, var(--sc-stroke), transparent); }

/* ================= glass cards / KPI tiles ================= */
.sc-card {
  position: relative; overflow: hidden; min-height: 112px; margin-bottom: .9rem; padding: 1rem 1.15rem;
  background: var(--sc-glass); border: 1px solid var(--sc-stroke); border-radius: 16px;
  backdrop-filter: blur(14px) saturate(140%); -webkit-backdrop-filter: blur(14px) saturate(140%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .35), inset 0 1px 0 rgba(255, 255, 255, .045);
  transition: transform .28s var(--sc-ease), border-color .28s, box-shadow .28s;
  animation: sc-rise .6s var(--sc-ease) both; --tone: var(--sc-cyan);
}
.sc-card::before {
  content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--tone), transparent); opacity: .85;
}
.sc-card::after {
  content: ""; position: absolute; right: -40px; top: -40px; width: 130px; height: 130px; border-radius: 50%;
  background: radial-gradient(circle, var(--tone), transparent 68%); opacity: .13; transition: opacity .3s;
}
.sc-card:hover { transform: translateY(-4px); border-color: color-mix(in srgb, var(--tone) 55%, transparent);
  box-shadow: 0 16px 42px rgba(0, 0, 0, .45), 0 0 28px color-mix(in srgb, var(--tone) 22%, transparent); }
.sc-card:hover::after { opacity: .26; }
.sc-card.ok { --tone: var(--sc-ok); } .sc-card.warn { --tone: var(--sc-warn); }
.sc-card.bad { --tone: var(--sc-bad); } .sc-card.purple { --tone: var(--sc-purple); }
.sc-card-label { font-size: .68rem; letter-spacing: .14em; text-transform: uppercase; color: var(--sc-muted); font-weight: 600; }
.sc-card-value {
  font-size: 1.9rem; font-weight: 700; color: #f8fafc; line-height: 1.25; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; overflow-wrap: anywhere;
}
.sc-card.ok .sc-card-value { color: var(--sc-ok); text-shadow: 0 0 22px rgba(52, 211, 153, .35); }
.sc-card.bad .sc-card-value { color: var(--sc-bad); text-shadow: 0 0 22px rgba(248, 113, 113, .4); }
.sc-card-hint { font-size: .76rem; color: var(--sc-dim); margin-top: .15rem; }
.sc-card-unit { font-size: .85rem; font-weight: 600; color: var(--sc-muted); margin-left: .3rem; letter-spacing: 0; }
/* animated counter: the number is drawn by a CSS counter that animates from 0 to --to */
.sc-count { counter-reset: n var(--sc-n); --sc-n: var(--to); animation: sc-count 1.5s var(--sc-ease) both; }
.sc-count::after { content: counter(n); }

.sc-panel {
  position: relative; background: var(--sc-glass); border: 1px solid var(--sc-stroke); border-radius: 16px;
  padding: 1.05rem 1.2rem; margin-bottom: .9rem; animation: sc-rise .55s var(--sc-ease) both;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .3), inset 0 1px 0 rgba(255, 255, 255, .04);
}
.sc-panel.bad { border-color: rgba(248, 113, 113, .45); }
.sc-panel.ok { border-color: rgba(52, 211, 153, .4); }
.sc-kv { display: grid; grid-template-columns: 150px 1fr; gap: .5rem .9rem; align-items: baseline; }
.sc-kv .k { font-size: .68rem; letter-spacing: .12em; text-transform: uppercase; color: var(--sc-muted); }
.sc-kv .v { font-size: .9rem; color: var(--sc-text); overflow-wrap: anywhere; }
.sc-mono, .sc-kv code { font-family: var(--sc-mono); font-size: .78rem; color: #a5f3fc; overflow-wrap: anywhere; background: none; padding: 0; }
.sc-note { font-size: .82rem; color: var(--sc-muted); line-height: 1.55; }

/* ================= badges ================= */
.sc-badge {
  display: inline-block; padding: .14rem .6rem; border-radius: 999px; font-size: .64rem; font-weight: 700;
  letter-spacing: .09em; border: 1px solid currentColor; white-space: nowrap; background: color-mix(in srgb, currentColor 9%, transparent);
}

/* ================= alert cards ================= */
.sc-alert {
  position: relative; border: 1px solid var(--sc-stroke); border-left: 3px solid var(--tone, var(--sc-cyan));
  border-radius: 12px; padding: .65rem .9rem; margin-bottom: .5rem; background: var(--sc-glass);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  animation: sc-slide .5s var(--sc-ease) both; transition: transform .22s var(--sc-ease), box-shadow .22s, border-color .22s;
}
.sc-alert:hover { transform: translateX(4px); box-shadow: 0 0 24px color-mix(in srgb, var(--tone, #22d3ee) 20%, transparent); }
.sc-alert.critical { animation: sc-slide .5s var(--sc-ease) both, sc-pulse-bad 2.4s 1s 3; }
.sc-alert-top { display: flex; justify-content: space-between; gap: .6rem; align-items: center; }
.sc-alert-rule { font-size: .8rem; font-weight: 600; color: #f1f5f9; overflow-wrap: anywhere; letter-spacing: .02em; }
.sc-alert-msg { font-size: .82rem; color: #b6c2d6; margin-top: .25rem; }
.sc-alert-meta { font-size: .7rem; color: var(--sc-dim); margin-top: .25rem; }

/* ================= step flow (vertical, steps appear one after another) ================= */
.sc-flow { position: relative; margin: .2rem 0 .9rem 0; }
.sc-step { position: relative; display: flex; gap: .85rem; padding: 0 0 .95rem 0; animation: sc-slide .55s var(--sc-ease) both; --tone: var(--sc-cyan); }
.sc-step:last-child { padding-bottom: 0; }
.sc-step::before {
  content: ""; position: absolute; left: 13px; top: 28px; bottom: 0; width: 2px;
  background: linear-gradient(180deg, var(--tone), rgba(56, 189, 248, .08));
}
.sc-step:last-child::before { display: none; }
.sc-step-dot {
  flex: none; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: .74rem; font-weight: 700; color: #04101c; background: var(--tone);
  box-shadow: 0 0 16px color-mix(in srgb, var(--tone) 55%, transparent); z-index: 1;
}
.sc-step.ok { --tone: var(--sc-ok); } .sc-step.bad { --tone: var(--sc-bad); }
.sc-step.warn { --tone: var(--sc-warn); } .sc-step.idle { --tone: #475569; }
.sc-step.bad .sc-step-body { border-color: rgba(248, 113, 113, .45); background: rgba(248, 113, 113, .07); }
.sc-step.ok .sc-step-body { border-color: rgba(52, 211, 153, .32); }
.sc-step-body { flex: 1; min-width: 0; padding: .55rem .8rem; border-radius: 12px; border: 1px solid var(--sc-stroke); background: rgba(13, 22, 40, .55); }
.sc-step-body b { display: block; font-size: .88rem; color: #f1f5f9; font-weight: 600; }
.sc-step-body span { display: block; font-size: .79rem; color: var(--sc-muted); margin-top: .12rem; overflow-wrap: anywhere; line-height: 1.5; }
.sc-step-body code { font-family: var(--sc-mono); font-size: .74rem; color: #a5f3fc; background: none; padding: 0; overflow-wrap: anywhere; }

/* ================= gauge ================= */
.sc-gauge-wrap { display: flex; align-items: center; gap: 1.1rem; }
.sc-gauge {
  position: relative; --to: 0; --sc-p: var(--to); --tone: var(--sc-cyan); flex: none; width: 124px; height: 124px; border-radius: 50%;
  background: conic-gradient(from 220deg, var(--tone) calc(var(--sc-p) * 0.78%), rgba(56, 189, 248, .1) 0 78%, transparent 0);
  display: flex; align-items: center; justify-content: center; animation: sc-gauge 1.6s var(--sc-ease) both;
  filter: drop-shadow(0 0 14px color-mix(in srgb, var(--tone) 40%, transparent));
}
.sc-gauge::before { content: ""; position: absolute; width: 98px; height: 98px; border-radius: 50%; background: #070c18; border: 1px solid var(--sc-stroke); }
.sc-gauge-value { position: relative; font-size: 1.7rem; font-weight: 700; color: #f8fafc; font-variant-numeric: tabular-nums; }
.sc-gauge-text b { display: block; font-size: 1.02rem; color: var(--tone-text, #f1f5f9); }
.sc-gauge-text span { display: block; font-size: .8rem; color: var(--sc-muted); margin-top: .2rem; line-height: 1.5; }

/* ================= bars ================= */
.sc-bars { display: flex; flex-direction: column; gap: .55rem; }
.sc-bar-row { animation: sc-slide .5s var(--sc-ease) both; }
.sc-bar-top { display: flex; justify-content: space-between; gap: .6rem; font-size: .82rem; color: var(--sc-text); margin-bottom: .22rem; }
.sc-bar-top span:last-child { color: var(--sc-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.sc-bar { height: 7px; border-radius: 99px; background: rgba(56, 189, 248, .1); overflow: hidden; }
.sc-bar i {
  display: block; height: 100%; border-radius: 99px; transform-origin: left; animation: sc-grow 1.1s var(--sc-ease) both;
  background: linear-gradient(90deg, var(--sc-blue), var(--tone, var(--sc-cyan)));
  box-shadow: 0 0 12px color-mix(in srgb, var(--tone, #22d3ee) 55%, transparent);
}

/* ================= transaction timeline + expandable cards ================= */
.sc-tl { position: relative; padding-left: 1.5rem; }
.sc-tl::before { content: ""; position: absolute; left: 6px; top: 6px; bottom: 6px; width: 2px; background: linear-gradient(180deg, var(--sc-cyan), rgba(139, 92, 246, .35), transparent); }
.sc-tx {
  position: relative; margin-bottom: .55rem; border: 1px solid var(--sc-stroke); border-radius: 13px; background: var(--sc-glass);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); animation: sc-slide .5s var(--sc-ease) both;
  transition: border-color .22s, box-shadow .22s, transform .22s var(--sc-ease); --tone: var(--sc-ok);
}
.sc-tx::before {
  content: ""; position: absolute; left: calc(-1.5rem + 1px); top: 1.05rem; width: 12px; height: 12px; border-radius: 50%;
  background: #04070e; border: 2px solid var(--tone); box-shadow: 0 0 10px var(--tone);
}
.sc-tx:hover { border-color: color-mix(in srgb, var(--tone) 50%, transparent); transform: translateX(3px);
  box-shadow: 0 0 22px color-mix(in srgb, var(--tone) 16%, transparent); }
.sc-tx.pending { --tone: var(--sc-cyan); } .sc-tx.flagged { --tone: var(--sc-warn); }
.sc-tx.rejected { --tone: var(--sc-bad); } .sc-tx.reward { --tone: var(--sc-purple); }
.sc-tx summary { list-style: none; cursor: pointer; padding: .65rem .9rem; display: grid; grid-template-columns: 1fr auto; gap: .2rem .8rem; align-items: center; }
.sc-tx summary::-webkit-details-marker { display: none; }
.sc-tx-route { font-size: .9rem; font-weight: 600; color: #f1f5f9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sc-tx-route em { font-style: normal; color: var(--tone); margin: 0 .35rem; }
.sc-tx-amount { font-size: .95rem; font-weight: 700; color: #f8fafc; font-variant-numeric: tabular-nums; white-space: nowrap; text-align: right; }
.sc-tx-meta { font-size: .72rem; color: var(--sc-dim); }
.sc-tx-state { text-align: right; }
.sc-tx-body { padding: .2rem .9rem .8rem .9rem; border-top: 1px dashed rgba(56, 189, 248, .14); animation: sc-rise .35s var(--sc-ease) both; }
.sc-tx-body .sc-kv { grid-template-columns: 120px 1fr; margin-top: .6rem; }
.sc-tx[open] { border-color: color-mix(in srgb, var(--tone) 45%, transparent); }

/* ================= wallet cards ================= */
.sc-wallet { min-height: 150px; }
.sc-wallet-name { font-size: 1.08rem; font-weight: 650; color: #f1f5f9; display: flex; align-items: center; gap: .55rem; }
.sc-avatar {
  width: 30px; height: 30px; border-radius: 10px; flex: none; display: flex; align-items: center; justify-content: center;
  font-size: .82rem; font-weight: 800; color: #04101c; background: linear-gradient(135deg, var(--a, #22d3ee), var(--b, #8b5cf6));
}
.sc-wallet-balance { font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-top: .5rem; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }

/* ================= validation scanner ================= */
.sc-scan { display: flex; flex-wrap: wrap; gap: .55rem; margin-bottom: .6rem; }
.sc-scan-block {
  position: relative; width: 118px; padding: .6rem .7rem; border-radius: 12px; border: 1px solid rgba(52, 211, 153, .35);
  background: var(--sc-glass); animation: sc-rise .5s var(--sc-ease) both; overflow: hidden;
  transition: transform .22s var(--sc-ease), box-shadow .22s;
}
.sc-scan-block:hover { transform: translateY(-3px); box-shadow: 0 0 22px rgba(52, 211, 153, .2); }
.sc-scan-block.bad { border-color: rgba(248, 113, 113, .6); box-shadow: 0 0 20px rgba(248, 113, 113, .18); }
.sc-scan-block.bad:hover { box-shadow: 0 0 26px rgba(248, 113, 113, .35); }
.sc-scan-block::after {     /* scanning light that sweeps across each block once */
  content: ""; position: absolute; top: 0; bottom: 0; width: 45%; left: 0;
  background: linear-gradient(90deg, transparent, rgba(34, 211, 238, .28), transparent);
  transform: translateX(-120%); animation: sc-sheen 1.1s ease-out both; animation-delay: inherit;
}
.sc-scan-title { font-size: .8rem; font-weight: 700; color: #f1f5f9; }
.sc-scan-hash { font-family: var(--sc-mono); font-size: .64rem; color: #a5f3fc; margin-top: .1rem; }
.sc-scan-dots { display: flex; gap: 4px; margin-top: .45rem; }
.sc-scan-dots i { width: 14px; height: 5px; border-radius: 3px; background: var(--sc-ok); box-shadow: 0 0 6px var(--sc-ok); }
.sc-scan-dots i.bad { background: var(--sc-bad); box-shadow: 0 0 8px var(--sc-bad); }
.sc-scan-dots i.na { background: #334155; box-shadow: none; }
.sc-legend { display: flex; flex-wrap: wrap; gap: .4rem 1rem; font-size: .74rem; color: var(--sc-muted); margin-bottom: 1rem; }
.sc-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: .35rem; vertical-align: baseline; }

/* ================= live mining console ================= */
.sc-mine { position: relative; }
.sc-mine-hash { font-family: var(--sc-mono); font-size: .8rem; color: #a5f3fc; overflow-wrap: anywhere; margin-top: .5rem; }
.sc-mine-hash b { color: var(--sc-bad); }
.sc-mine-num { font-size: 2rem; font-weight: 700; color: #f8fafc; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.sc-mine-bar { height: 6px; border-radius: 99px; background: rgba(56, 189, 248, .12); overflow: hidden; margin-top: .5rem; }
.sc-mine-bar i {
  display: block; height: 100%; border-radius: 99px; transition: width .2s linear;
  background: linear-gradient(90deg, var(--sc-blue), var(--sc-cyan), var(--sc-blue)); background-size: 200% 100%;
  animation: sc-flow 1.2s linear infinite; box-shadow: 0 0 12px rgba(34, 211, 238, .7);
}

/* ================= before / after ================= */
.sc-compare { display: grid; grid-template-columns: 1fr auto 1fr; gap: .8rem; align-items: stretch; }
.sc-compare-arrow { align-self: center; color: var(--sc-bad); font-size: 1.4rem; }
.sc-compare .sc-panel { margin-bottom: 0; }
.sc-strike { color: var(--sc-bad); font-weight: 700; }

/* ================= Streamlit widgets ================= */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(135deg, #22d3ee 0%, #3b82f6 100%); color: #04101c; font-weight: 700; border: 0; border-radius: 11px;
  box-shadow: 0 6px 20px rgba(34, 211, 238, .25), inset 0 1px 0 rgba(255, 255, 255, .35);
  transition: transform .18s var(--sc-ease), box-shadow .18s, filter .18s;
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  transform: translateY(-2px); box-shadow: 0 10px 30px rgba(34, 211, 238, .42); filter: brightness(1.08); color: #04101c;
}
[data-testid="stBaseButton-primary"]:active, [data-testid="stBaseButton-primaryFormSubmit"]:active { transform: translateY(0); }
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p { color: #04101c; font-weight: 700; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stDownloadButton"] button {
  background: rgba(13, 22, 40, .6); border: 1px solid rgba(56, 189, 248, .26); border-radius: 11px; color: var(--sc-text);
  transition: transform .18s var(--sc-ease), border-color .18s, box-shadow .18s, background .18s;
}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover, [data-testid="stDownloadButton"] button:hover {
  border-color: var(--sc-cyan); background: rgba(34, 211, 238, .09); box-shadow: 0 0 20px rgba(34, 211, 238, .2); transform: translateY(-1px); color: #f1f5f9;
}
[data-testid="stBaseButton-secondary"]:disabled { opacity: .45; transform: none; box-shadow: none; }

[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stSelectbox"] div[role="group"],
[data-testid="stMultiSelect"] div[role="group"] {
  background: rgba(8, 14, 28, .65); border: 1px solid var(--sc-stroke); border-radius: 11px;
  transition: border-color .2s, box-shadow .2s;
}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stSelectbox"] div[role="group"]:focus-within {
  border-color: var(--sc-cyan); box-shadow: 0 0 0 3px rgba(34, 211, 238, .13), 0 0 22px rgba(34, 211, 238, .12);
}
[data-testid="stWidgetLabel"] p { font-size: .8rem; color: #b6c2d6; letter-spacing: .01em; }

[data-testid="stForm"] {
  background: var(--sc-glass); border: 1px solid var(--sc-stroke); border-radius: 16px; padding: 1.1rem 1.2rem;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); box-shadow: 0 10px 30px rgba(0, 0, 0, .3);
}
[data-testid="stTabs"] [role="tablist"] { gap: .3rem; border-bottom: 1px solid var(--sc-stroke); }
[data-testid="stTab"] { padding: .5rem .95rem; border-radius: 10px 10px 0 0; transition: background .2s, color .2s; }
[data-testid="stTab"] p { font-size: .9rem; color: var(--sc-muted); transition: color .2s; }
[data-testid="stTab"]:hover { background: rgba(34, 211, 238, .06); }
[data-testid="stTab"]:hover p { color: #f1f5f9; }
[data-testid="stTab"][data-selected="true"] { background: linear-gradient(180deg, rgba(34, 211, 238, .13), transparent); }
[data-testid="stTab"][data-selected="true"] p { color: var(--sc-cyan); font-weight: 600; }
[data-testid="stTabPanel"] { animation: sc-rise .4s var(--sc-ease) both; padding-top: .9rem; }

[data-testid="stExpander"] details {
  background: var(--sc-glass); border: 1px solid var(--sc-stroke); border-radius: 14px; overflow: hidden;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); transition: border-color .2s, box-shadow .2s;
}
[data-testid="stExpander"] details:hover { border-color: rgba(34, 211, 238, .4); }
[data-testid="stExpander"] details[open] { box-shadow: 0 0 24px rgba(34, 211, 238, .08); }
[data-testid="stAlertContainer"] { border-radius: 13px; border: 1px solid rgba(148, 163, 184, .18); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); animation: sc-rise .45s var(--sc-ease) both; }
[data-testid="stDataFrame"] { border: 1px solid var(--sc-stroke); border-radius: 13px; overflow: hidden; box-shadow: 0 8px 26px rgba(0, 0, 0, .28); }
[data-testid="stVegaLiteChart"] { border: 1px solid var(--sc-stroke); border-radius: 16px; padding: .6rem .6rem .2rem .6rem; background: var(--sc-glass); }
iframe[title*="securechain_viz"] { border-radius: 18px; box-shadow: 0 18px 50px rgba(0, 0, 0, .5), 0 0 40px rgba(34, 211, 238, .06); }
[data-testid="stCaptionContainer"] { color: var(--sc-dim); }
hr { border-color: var(--sc-stroke) !important; }

@media (max-width: 900px) {
  .sc-header h1 { font-size: 1.6rem; }
  .sc-kv { grid-template-columns: 1fr; gap: .1rem; }
  .sc-kv .v { margin-bottom: .45rem; }
  .sc-compare { grid-template-columns: 1fr; }
  .sc-compare-arrow { transform: rotate(90deg); justify-self: center; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .001s !important; animation-iteration-count: 1 !important; transition-duration: .001s !important; }
}
</style>
"""


def apply_theme() -> None:
    """Inject the design system (call once at the top of the app)."""
    st.markdown(_CSS, unsafe_allow_html=True)

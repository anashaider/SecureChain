"""
Building blocks shared by every page of the command center.

Everything here produces small pieces of HTML styled by ui/theme.py.
Text that comes from the user or the ledger (wallet names, messages,
addresses) is always passed through html.escape before it is placed
inside custom HTML.
"""

import html
from datetime import datetime

import pandas as pd
import streamlit as st

import config
from node import SecureChainNode
from ui.theme import ACCENT, BAD, MUTED, OK, PURPLE, SEVERITY_COLORS, WARN


# --------------------------------------------------------------------------
# The node (one shared instance for the whole app)
# --------------------------------------------------------------------------
@st.cache_resource
def get_node() -> SecureChainNode:
    """Create the node once and reuse it across reruns and browser sessions."""
    return SecureChainNode()


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def short(text: str, head: int = 10, tail: int = 6) -> str:
    """Shorten a long hash/address: 'SC3f9a12bc...9e01ab'."""
    text = str(text)
    if len(text) <= head + tail + 3:
        return text
    return f"{text[:head]}...{text[-tail:]}"


def fmt_amount(amount: float) -> str:
    return f"{amount:,.2f} {config.COIN_SYMBOL}"


def fmt_time(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError, TypeError):
        return "invalid time"


def party_label(address: str, book: dict[str, str]) -> str:
    """Readable name for a sender/receiver: wallet name if known, else short address."""
    if address == config.COINBASE_SENDER:
        return "Mining reward"
    if address in book:
        return f"{book[address]} ({short(address, 6, 4)})"
    return short(address)


def party_name(address: str, book: dict[str, str]) -> str:
    """Like party_label but without the address suffix (for compact cards)."""
    if address == config.COINBASE_SENDER:
        return "Mining reward"
    return book.get(address) or short(address, 8, 4)


def esc(value) -> str:
    return html.escape(str(value))


def render_html(markup: str) -> None:
    """Render a block of trusted, already-escaped HTML."""
    st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Flash messages (survive the st.rerun() that follows an action)
# --------------------------------------------------------------------------
def flash(kind: str, message: str) -> None:
    """Queue a message to be shown at the top of the page after the next rerun."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flashes() -> None:
    renderers = {"success": st.success, "error": st.error, "warning": st.warning, "info": st.info}
    for kind, message in st.session_state.pop("_flash", []):
        renderers.get(kind, st.info)(message)


# --------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------
def page_header(title: str, subtitle: str, eyebrow: str = "SecureChain") -> None:
    render_html(
        f'<div class="sc-header"><div class="sc-eyebrow">{esc(eyebrow)}</div>'
        f"<h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>"
    )
    show_flashes()


def section(title: str) -> None:
    render_html(f'<div class="sc-section">{esc(title)}</div>')


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------
def stat_card(label: str, value, hint: str = "", tone: str = "", delay: float = 0.0, unit: str = "") -> None:
    """
    A KPI tile. Whole numbers count up from zero when the tile appears.

    tone:  '' (cyan), 'ok', 'warn', 'bad' or 'purple'
    delay: seconds before the entrance animation starts (for a staggered row)
    """
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10_000_000:
        # The digits are drawn by a CSS counter (see .sc-count in theme.py).
        number = f'<span class="sc-count" style="--to:{value};animation-delay:{delay + 0.15:.2f}s" aria-label="{value}"></span>'
    else:
        number = esc(value)
    unit_html = f'<span class="sc-card-unit">{esc(unit)}</span>' if unit else ""
    render_html(
        f'<div class="sc-card {tone}" style="animation-delay:{delay:.2f}s">'
        f'<div class="sc-card-label">{esc(label)}</div>'
        f'<div class="sc-card-value">{number}{unit_html}</div>'
        f'<div class="sc-card-hint">{esc(hint)}</div>'
        f"</div>"
    )


def stat_row(cards: list[dict]) -> None:
    """A row of KPI tiles with a staggered entrance. Each dict holds stat_card arguments."""
    for index, (column, card) in enumerate(zip(st.columns(len(cards)), cards)):
        with column:
            stat_card(delay=index * 0.07, **card)


def key_value_panel(rows: list[tuple[str, str]], mono: set[str] | None = None, tone: str = "") -> None:
    """A two-column 'label: value' glass panel. Labels listed in `mono` use a code font."""
    mono = mono or set()
    cells = []
    for label, value in rows:
        value_html = esc(value)
        if label in mono:
            value_html = f"<code>{value_html}</code>"
        cells.append(f'<div class="k">{esc(label)}</div><div class="v">{value_html}</div>')
    render_html(f'<div class="sc-panel {tone}"><div class="sc-kv">{"".join(cells)}</div></div>')


def note_panel(text: str, tone: str = "") -> None:
    render_html(f'<div class="sc-panel {tone}"><div class="sc-note">{esc(text)}</div></div>')


def table(rows: list[dict], empty_message: str = "Nothing to show yet.", height: int | None = None) -> None:
    """Show a list of dictionaries as a table (or a friendly note when empty)."""
    if not rows:
        st.caption(empty_message)
        return
    options = {"hide_index": True, "width": "stretch"}
    if height is not None:
        options["height"] = height
    st.dataframe(pd.DataFrame(rows), **options)


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
def severity_badge(severity: str) -> str:
    color = SEVERITY_COLORS.get(severity, ACCENT)
    return f'<span class="sc-badge" style="color:{color}">{esc(severity)}</span>'


def badge(text: str, color: str) -> str:
    return f'<span class="sc-badge" style="color:{color}">{esc(text)}</span>'


def alert_html(alert: dict, book: dict[str, str], delay: float = 0.0) -> str:
    """HTML for one fraud-log entry (a row from the database)."""
    color = SEVERITY_COLORS.get(alert["severity"], ACCENT)
    meta = [fmt_time(alert["created_at"])]
    if alert.get("sender"):
        meta.append(f"from {party_label(alert['sender'], book)}")
    if alert.get("amount"):
        meta.append(fmt_amount(alert["amount"]))
    critical = " critical" if alert["severity"] == "CRITICAL" else ""
    return (
        f'<div class="sc-alert{critical}" style="--tone:{color};animation-delay:{delay:.2f}s">'
        f'<div class="sc-alert-top"><span class="sc-alert-rule">{esc(alert["rule"].replace("_", " "))}</span>'
        f"{severity_badge(alert['severity'])}</div>"
        f'<div class="sc-alert-msg">{esc(alert["message"])}</div>'
        f'<div class="sc-alert-meta">{esc(" · ".join(meta))}</div>'
        f"</div>"
    )


def alert_row(alert: dict, book: dict[str, str], delay: float = 0.0) -> None:
    render_html(alert_html(alert, book, delay))


def alert_feed(alerts: list[dict], book: dict[str, str]) -> None:
    """A list of alert cards that slide in one after another."""
    render_html("".join(alert_html(alert, book, min(i, 12) * 0.05) for i, alert in enumerate(alerts)))


# --------------------------------------------------------------------------
# Step flow, gauge, bars
# --------------------------------------------------------------------------
def flow(steps: list[dict], start_delay: float = 0.0, gap: float = 0.28) -> None:
    """
    A vertical sequence of steps that appear one after another.

    Each step: {"state": ok|bad|warn|info|idle, "title": str, "text": str, "code": str (optional)}
    """
    marks = {"ok": "✓", "bad": "✗", "warn": "!", "idle": "·"}
    parts = []
    for index, step in enumerate(steps):
        state = step.get("state", "info")
        code = f'<span><code>{esc(step["code"])}</code></span>' if step.get("code") else ""
        text = f'<span>{esc(step["text"])}</span>' if step.get("text") else ""
        parts.append(
            f'<div class="sc-step {state}" style="animation-delay:{start_delay + index * gap:.2f}s">'
            f'<div class="sc-step-dot">{marks.get(state, index + 1)}</div>'
            f'<div class="sc-step-body"><b>{esc(step["title"])}</b>{text}{code}</div></div>'
        )
    render_html(f'<div class="sc-flow">{"".join(parts)}</div>')


def gauge(value: int, title: str, text: str, tone: str = ACCENT) -> None:
    """An animated ring gauge for a 0-100 value."""
    value = max(0, min(100, int(value)))
    render_html(
        f'<div class="sc-panel"><div class="sc-gauge-wrap">'
        f'<div class="sc-gauge" style="--to:{value};--tone:{tone}"><span class="sc-gauge-value">{value}</span></div>'
        f'<div class="sc-gauge-text" style="--tone-text:{tone}"><b>{esc(title)}</b><span>{esc(text)}</span></div>'
        f"</div></div>"
    )


def bars(rows: list[dict]) -> None:
    """
    Horizontal bars that grow in. Each row: {"label", "value" (text), "fraction" (0-1), "tone" (css colour)}
    """
    parts = []
    for index, row in enumerate(rows):
        width = max(2.0, min(100.0, row["fraction"] * 100))
        tone = row.get("tone", ACCENT)
        parts.append(
            f'<div class="sc-bar-row" style="animation-delay:{index * 0.07:.2f}s">'
            f'<div class="sc-bar-top"><span>{esc(row["label"])}</span><span>{esc(row["value"])}</span></div>'
            f'<div class="sc-bar"><i style="width:{width:.1f}%;--tone:{tone};animation-delay:{0.15 + index * 0.07:.2f}s"></i></div>'
            f"</div>"
        )
    render_html(f'<div class="sc-panel"><div class="sc-bars">{"".join(parts)}</div></div>')


# --------------------------------------------------------------------------
# Transaction timeline (expandable cards)
# --------------------------------------------------------------------------
STATE_STYLE = {
    "confirmed": ("CONFIRMED", OK),
    "pending": ("PENDING", ACCENT),
    "flagged": ("FLAGGED", WARN),
    "rejected": ("REJECTED", BAD),
    "reward": ("MINING REWARD", PURPLE),
}


def tx_timeline(items: list[dict]) -> None:
    """
    An animated timeline of expandable transaction cards.

    Each item: {"state": confirmed|pending|flagged|rejected|reward, "sender", "receiver",
                "amount", "meta", "details": [(label, value, is_mono)]}
    """
    parts = []
    for index, item in enumerate(items):
        label, color = STATE_STYLE.get(item["state"], STATE_STYLE["confirmed"])
        rows = "".join(
            f'<div class="k">{esc(k)}</div><div class="v">{"<code>" + esc(v) + "</code>" if mono else esc(v)}</div>'
            for k, v, mono in item.get("details", [])
        )
        parts.append(
            f'<details class="sc-tx {item["state"]}" style="animation-delay:{min(index, 14) * 0.045:.2f}s">'
            f"<summary>"
            f'<span class="sc-tx-route">{esc(item["sender"])}<em>→</em>{esc(item["receiver"])}</span>'
            f'<span class="sc-tx-amount">{esc(item["amount"])}</span>'
            f'<span class="sc-tx-meta">{esc(item["meta"])}</span>'
            f'<span class="sc-tx-state">{badge(label, color)}</span>'
            f"</summary>"
            f'<div class="sc-tx-body"><div class="sc-kv">{rows}</div></div>'
            f"</details>"
        )
    render_html(f'<div class="sc-tl">{"".join(parts)}</div>')


# --------------------------------------------------------------------------
# Charts (Vega-Lite, themed to match the glass UI; hover for tooltips)
# --------------------------------------------------------------------------
_VEGA_CONFIG = {
    "background": "transparent",
    "view": {"stroke": None},
    "font": "Segoe UI, Inter, system-ui, sans-serif",
    "axis": {
        "labelColor": MUTED, "titleColor": MUTED, "labelFontSize": 11, "titleFontSize": 11,
        "titleFontWeight": 500, "gridColor": "rgba(56,189,248,0.08)", "domainColor": "rgba(56,189,248,0.22)",
        "tickColor": "rgba(56,189,248,0.22)", "labelPadding": 6, "titlePadding": 10,
    },
    "legend": {"labelColor": "#b6c2d6", "titleColor": MUTED, "orient": "top", "labelFontSize": 11, "symbolType": "circle"},
    "bar": {"cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4},
    "arc": {"stroke": "#070c18", "strokeWidth": 2},
}


def area_gradient(color: str = "34,211,238") -> dict:
    return {
        "x1": 1, "y1": 1, "x2": 1, "y2": 0, "gradient": "linear",
        "stops": [{"offset": 0, "color": f"rgba({color},0.02)"}, {"offset": 1, "color": f"rgba({color},0.45)"}],
    }


def chart(rows: list[dict], spec: dict, height: int = 240) -> None:
    """Draw a Vega-Lite chart from a list of dictionaries."""
    full_spec = {"height": height, **spec, "config": _VEGA_CONFIG}
    st.vega_lite_chart(pd.DataFrame(rows), full_spec, width="stretch", theme=None)


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------
def wallet_select(label: str, wallets: list[dict], key: str, show_balance: bool = True):
    """Dropdown to pick one of the node's wallets. Returns the wallet dict (or None)."""
    if not wallets:
        return None

    def describe(index: int) -> str:
        wallet = wallets[index]
        return f"{wallet['name']}  ·  {short(wallet['address'], 8, 4)}"

    # The option text deliberately contains NO balance: text that changes after
    # every payment makes Streamlit reset the dropdown or show a stale value.
    # The live balance is shown in a caption underneath instead, and the chosen
    # ADDRESS is remembered so the same wallet stays selected between reruns.
    memory_key = f"{key}__address"
    remembered = st.session_state.get(memory_key)
    default = next((i for i, wallet in enumerate(wallets) if wallet["address"] == remembered), 0)
    index = st.selectbox(label, range(len(wallets)), index=default, format_func=describe, key=key)
    st.session_state[memory_key] = wallets[index]["address"]
    if show_balance:
        st.caption(f"Available: {fmt_amount(wallets[index]['available'])}")
    return wallets[index]


def need_wallets_notice(node) -> bool:
    """Show a hint when no wallet exists yet. Returns True if the page should stop."""
    if node.list_wallets():
        return False
    st.info(
        "No wallets yet. Create one on the **Wallets** page, or use "
        "**Load demo data** in the sidebar to get three funded demo wallets."
    )
    return True

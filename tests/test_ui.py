"""
Smoke tests for the Streamlit dashboard.

Streamlit's AppTest runs app.py without a browser. These tests open every
page (with an empty ledger, with demo data, and with a tampered chain) and
fail if any page raises an exception. They also click through the main
actions: load demo data, mine a block, send a payment.
"""

import pytest

st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import config  # noqa: E402
from node import DEMO_PASSWORD  # noqa: E402
from ui.components import get_node  # noqa: E402

PAGES = [
    "Dashboard", "Wallets", "Send Transaction", "Transaction History", "Mining",
    "Fraud Alerts", "Blockchain Explorer", "Chain Validation", "Attack Lab",
]
APP = str(config.BASE_DIR / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """The dashboard running against a temporary database with fast mining."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ui.db")
    monkeypatch.setattr(config, "MINING_DIFFICULTY", 2)
    st.cache_resource.clear()            # make the app build a fresh node for this test
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    yield at
    st.cache_resource.clear()


def open_page(at: AppTest, page: str) -> AppTest:
    at.sidebar.radio(key="nav").set_value(page).run()
    assert not at.exception, f"{page} raised: {[e.value for e in at.exception]}"
    return at


def all_text(at: AppTest) -> str:
    """Every message currently shown in success/error/warning/info boxes."""
    boxes = list(at.success) + list(at.error) + list(at.warning) + list(at.info)
    return " | ".join(str(box.value) for box in boxes)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_on_an_empty_ledger(app, page):
    open_page(app, page)


def test_every_page_renders_with_demo_data(app):
    get_node().seed_demo_data()
    for page in PAGES:
        open_page(app, page)


def test_every_page_renders_with_a_tampered_chain(app):
    node = get_node()
    node.seed_demo_data()
    node.tamper_with_transaction(4, 1, 5000)
    for page in PAGES:
        open_page(app, page)
    open_page(app, "Chain Validation")
    assert "INVALID" in all_text(app)


def test_load_demo_data_button(app):
    app.sidebar.button(key="demo_load").click().run()
    assert not app.exception
    assert [w["name"] for w in get_node().list_wallets()] == ["Alice", "Bob", "Charlie"]
    assert "Demo data loaded" in all_text(app)


def test_mine_block_from_the_ui(app):
    node = get_node()
    node.seed_demo_data()
    height = len(node.blockchain.chain)
    open_page(app, "Mining")
    mine_button = next(b for b in app.button if b.label == "Mine block")
    mine_button.click().run()
    assert not app.exception
    assert len(node.blockchain.chain) == height + 1
    assert "mined" in all_text(app)


def test_send_payment_from_the_ui(app):
    node = get_node()
    node.seed_demo_data()
    open_page(app, "Send Transaction")
    password_box = next(t for t in app.text_input if "password" in t.label.lower())
    password_box.set_value(DEMO_PASSWORD)
    send_button = next(b for b in app.button if b.label == "Sign and send")
    send_button.click().run()
    assert not app.exception
    assert len(node.blockchain.pending_transactions) == 1
    assert "accepted" in all_text(app)


def test_wrong_password_is_reported_in_the_ui(app):
    node = get_node()
    node.seed_demo_data()
    open_page(app, "Send Transaction")
    next(t for t in app.text_input if "password" in t.label.lower()).set_value("wrong-password")
    next(b for b in app.button if b.label == "Sign and send").click().run()
    assert not app.exception
    assert node.blockchain.pending_transactions == []
    assert "Could not unlock" in all_text(app)

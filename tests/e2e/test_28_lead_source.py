import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import button_labels, find_button
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))
ACCOUNT_3_TG_ID = int(os.environ.get("TEST_ACCOUNT_3_TG_ID", "0"))

_state: dict = {}


# ── helpers ──


def _extract_buttons(msg) -> list[dict]:
    buttons = []
    if msg.reply_markup and hasattr(msg.reply_markup, "rows"):
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                data = btn.data.decode() if isinstance(btn.data, bytes) else btn.data
                buttons.append({"text": btn.text, "data": data})
    return buttons


# ── tests (sequential, order matters) ──


async def test_01_start_plain_no_lead_source(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Plain /start without payload -> lead_source_id is NULL."""
    await account1.send_command_multi("/start", count=2)

    lead_source_id = await db.get_user_lead_source_id(ACCOUNT_1_TG_ID)
    assert lead_source_id is None, (
        f"Expected lead_source_id=None for plain /start, got {lead_source_id}"
    )


async def test_02_referral_link_button_visible(
    account1: TelegramTestClient,
    bot_setup: BotSetup,
):
    """Admin menu should contain menu_referral_link button."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    await account1.send_command_multi("/start", count=2)
    msg = await account1.send_command("/menu")

    if msg.reply_markup is None:
        await account1.send_command_multi("/start", count=2)
        msg = await account1.send_command("/menu")

    btn = find_button(msg, "menu_referral_link")
    assert btn is not None, (
        f"Admin menu should have menu_referral_link button. "
        f"Buttons: {button_labels(msg)}"
    )


async def test_03_show_referral_link(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Click menu_referral_link -> shows link with ref_ prefix and counter = 0."""
    menu_msg = await account1.send_command("/menu")
    btn = find_button(menu_msg, "menu_referral_link")
    assert btn is not None, (
        f"menu_referral_link not found. Buttons: {button_labels(menu_msg)}"
    )

    ref_msg = await account1.click_button(menu_msg, text=btn.text)
    text = ref_msg.text or ""

    ref_code = f"ref_{ACCOUNT_1_TG_ID}"
    assert "ref_" in text, f"Expected 'ref_' in referral link text, got: {text[:300]}"
    assert "0" in text, f"Expected counter '0' in referral link text, got: {text[:300]}"

    source = await db.get_lead_source_by_code(ref_code)
    assert source is not None, f"Lead source with code={ref_code} not found in DB"
    assert source["source_type"] == "referral", (
        f"Expected source_type=referral, got {source['source_type']}"
    )

    _state["ref_code"] = ref_code


async def test_04_start_with_referral_deep_link(
    account2: TelegramTestClient,
    db: DBAssertions,
):
    """account2 joins via /start ref_{A1} -> referral welcome, lead_source_id recorded."""
    ref_code = _state["ref_code"]
    responses = await account2.send_command_multi(f"/start {ref_code}", count=2)

    assert len(responses) >= 1, "Bot did not respond to /start with referral deep link"
    welcome_text = responses[0].text or ""

    # Referral welcome should differ from standard (contains referrer mention)
    assert "пригласил" in welcome_text.lower() or "нашли" in welcome_text.lower(), (
        f"Expected referral welcome text, got: {welcome_text[:300]}"
    )

    lead_source_id = await db.get_user_lead_source_id(ACCOUNT_2_TG_ID)
    assert lead_source_id is not None, (
        "Expected lead_source_id to be set for account2 after referral deep link"
    )

    source = await db.get_lead_source_by_code(ref_code)
    assert source is not None
    assert lead_source_id == source["id"], (
        f"User lead_source_id={lead_source_id} != source.id={source['id']}"
    )

    _state["a2_lead_source_id"] = lead_source_id


async def test_05_idempotent_no_overwrite(
    account2: TelegramTestClient,
    db: DBAssertions,
):
    """Repeated /start ref_{A1} does NOT change lead_source_id (not new user)."""
    ref_code = _state["ref_code"]
    before = await db.get_user_lead_source_id(ACCOUNT_2_TG_ID)

    await account2.send_command_multi(f"/start {ref_code}", count=2)

    after = await db.get_user_lead_source_id(ACCOUNT_2_TG_ID)
    assert before == after, (
        f"lead_source_id changed on repeat /start: {before} -> {after}"
    )


async def test_06_referral_counter_updated(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """After account2 joined via referral, counter should be >= 1."""
    menu_msg = await account1.send_command("/menu")
    btn = find_button(menu_msg, "menu_referral_link")
    assert btn is not None

    ref_msg = await account1.click_button(menu_msg, text=btn.text)
    text = ref_msg.text or ""

    # Counter should show at least 1 (not "0")
    ref_code = _state["ref_code"]
    source = await db.get_lead_source_by_code(ref_code)
    count = await db.count_users_by_lead_source(source["id"])
    assert count >= 1, f"Expected referral count >= 1, got {count}"

    # UI should reflect updated counter
    assert "1" in text, f"Expected '1' in referral counter text, got: {text[:300]}"


async def test_07_self_referral_ignored(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Self-referral: /start ref_{A1} by A1 -> standard welcome, no lead_source change."""
    ref_code = _state["ref_code"]
    lead_before = await db.get_user_lead_source_id(ACCOUNT_1_TG_ID)

    responses = await account1.send_command_multi(f"/start {ref_code}", count=2)
    welcome_text = responses[0].text or ""

    # Self-referral returns None from resolve_and_record -> standard welcome
    assert "пригласил" not in welcome_text.lower(), (
        f"Self-referral should show standard welcome, got: {welcome_text[:300]}"
    )

    lead_after = await db.get_user_lead_source_id(ACCOUNT_1_TG_ID)
    assert lead_before == lead_after, (
        f"Self-referral changed lead_source_id: {lead_before} -> {lead_after}"
    )


async def test_08_admin_channel_links_empty(
    account3: TelegramTestClient,
    bot_setup: BotSetup,
):
    """account3 (admin) opens channel links -> empty list with create button."""
    await account3.send_command_multi("/start", count=2)

    msg = await account3.send_command("/menu")
    if msg.reply_markup is None:
        await account3.send_command_multi("/start", count=2)
        msg = await account3.send_command("/menu")

    ch_btn = find_button(msg, "menu_channel_links")
    assert ch_btn is not None, (
        f"Admin menu should have menu_channel_links. Buttons: {button_labels(msg)}"
    )

    ch_msg = await account3.click_button(msg, text=ch_btn.text)

    # Should show empty state with create button
    create_btn = find_button(ch_msg, "ch_create")
    assert create_btn is not None, (
        f"Channel links menu should have ch_create button. "
        f"Buttons: {button_labels(ch_msg)}"
    )


async def test_09_create_channel_link_fsm(
    account3: TelegramTestClient,
    db: DBAssertions,
):
    """Create channel link via FSM: ch_create -> enter label -> link created."""
    menu_msg = await account3.send_command("/menu")
    ch_btn = find_button(menu_msg, "menu_channel_links")
    assert ch_btn is not None
    ch_msg = await account3.click_button(menu_msg, text=ch_btn.text)

    create_btn = find_button(ch_msg, "ch_create")
    assert create_btn is not None
    await account3.click_button(ch_msg, text=create_btn.text)

    # FSM asks for label -> send label
    result_msg = await account3.send_text_in_fsm("E2E Тестовый пост")
    result_text = result_msg.text or ""

    assert "ch_" in result_text or "создан" in result_text.lower(), (
        f"Expected channel link creation confirmation, got: {result_text[:300]}"
    )

    # DB check
    rows = await db._pool.fetch(
        "SELECT * FROM iam.lead_sources WHERE label = $1 AND source_type = 'channel'",
        "E2E Тестовый пост",
    )
    assert len(rows) >= 1, "Channel lead source not found in DB"
    _state["ch_source_id"] = rows[0]["id"]
    _state["ch_code"] = rows[0]["code"]


async def test_10_channel_link_in_list(
    account3: TelegramTestClient,
):
    """Channel links list should contain the created link."""
    menu_msg = await account3.send_command("/menu")
    ch_btn = find_button(menu_msg, "menu_channel_links")
    assert ch_btn is not None

    ch_msg = await account3.click_button(menu_msg, text=ch_btn.text)
    ch_text = ch_msg.text or ""

    # Check that the list contains our label or a button referencing our link
    buttons = _extract_buttons(ch_msg)
    all_text = ch_text + " ".join(b["text"] for b in buttons)

    assert "E2E Тестовый пост" in all_text or _state["ch_code"] in all_text, (
        f"Expected created channel link in list. "
        f"Text: {ch_text[:200]}, Buttons: {[b['text'] for b in buttons]}"
    )

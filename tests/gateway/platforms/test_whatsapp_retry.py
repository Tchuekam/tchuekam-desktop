import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gateway.platforms.whatsapp import WhatsAppAdapter
from gateway.platforms.base import SendResult


@pytest.mark.asyncio
async def test_whatsapp_send_retries_transient_error():
    """Verify WhatsAppAdapter retries transient HTTP 500 errors and succeeds."""
    adapter = WhatsAppAdapter(config=MagicMock())
    adapter._running = True
    adapter._bridge_port = 3000
    adapter._check_managed_bridge_exit = AsyncMock(return_value=None)

    session_mock = MagicMock()
    adapter._http_session = session_mock

    resp_500 = AsyncMock()
    resp_500.status = 500
    resp_500.text = AsyncMock(return_value="Internal Error")

    resp_200 = AsyncMock()
    resp_200.status = 200
    resp_200.json = AsyncMock(return_value={"messageId": "wa_msg_123"})

    cm_500 = AsyncMock()
    cm_500.__aenter__.return_value = resp_500
    cm_500.__aexit__.return_value = None

    cm_200 = AsyncMock()
    cm_200.__aenter__.return_value = resp_200
    cm_200.__aexit__.return_value = None

    session_mock.post.side_effect = [cm_500, cm_200]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        res = await adapter.send("12345@s.whatsapp.net", "hello world")

    assert res.success is True
    assert res.message_id == "wa_msg_123"
    assert session_mock.post.call_count == 2


@pytest.mark.asyncio
async def test_whatsapp_send_fails_permanently_on_400():
    """Verify WhatsAppAdapter does NOT retry client 400 errors."""
    adapter = WhatsAppAdapter(config=MagicMock())
    adapter._running = True
    adapter._bridge_port = 3000
    adapter._check_managed_bridge_exit = AsyncMock(return_value=None)

    session_mock = MagicMock()
    adapter._http_session = session_mock

    resp_400 = AsyncMock()
    resp_400.status = 400
    resp_400.text = AsyncMock(return_value="Invalid JID")

    cm_400 = AsyncMock()
    cm_400.__aenter__.return_value = resp_400
    cm_400.__aexit__.return_value = None

    session_mock.post.side_effect = [cm_400]

    with patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        res = await adapter.send("12345@s.whatsapp.net", "hello world")

    assert res.success is False
    assert "400" in res.error
    assert session_mock.post.call_count == 1
    assert sleep_mock.call_count == 0

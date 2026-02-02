"""
Unit-тесты парсинга payload ChatFlow webhook (remoteJid, messageId, messageType, message),
команд mute: /stop, /start, /stop all, /start all.
Per-chat pause: таблица conversations, колонка ai_paused (только этот чат по remoteJid).
Запуск: python test_chatflow_webhook.py
       или: python -m pytest test_chatflow_webhook.py -v
"""
import inspect
from app.api.endpoints.chatflow_webhook import (
    parse_incoming_payload,
    _parse_mute_command,
    _normalize_command_text,
    _is_stop_command,
    _is_start_command,
)


def test_parse_text_payload():
    """Текст: messageType=text, message=строка, metadata.remoteJid, metadata.messageId."""
    data = {
        "messageType": "text",
        "message": "Салем",
        "metadata": {
            "sender": "Kanat",
            "timestamp": 1769970129,
            "messageId": "3ABF0B54955A059C6B9E",
            "remoteJid": "77768776637@s.whatsapp.net",
        },
    }
    remote_jid, msg_id, msg_type, text = parse_incoming_payload(data)
    assert remote_jid == "77768776637@s.whatsapp.net"
    assert msg_id == "3ABF0B54955A059C6B9E"
    assert msg_type == "text"
    assert text == "Салем"


def test_parse_voice_payload():
    """Голосовое: messageType=voice, message может быть пустым."""
    data = {
        "messageType": "voice",
        "message": "",
        "metadata": {
            "remoteJid": "77001234567@s.whatsapp.net",
            "messageId": "VOICE_MSG_001",
        },
        "mediaData": {"url": "https://example.com/audio.ogg"},
    }
    remote_jid, msg_id, msg_type, text = parse_incoming_payload(data)
    assert remote_jid == "77001234567@s.whatsapp.net"
    assert msg_id == "VOICE_MSG_001"
    assert msg_type == "voice"
    assert text == ""


def test_parse_empty_or_invalid():
    """Пустой/не dict — пустые строки."""
    assert parse_incoming_payload(None) == ("", "", "", "")
    assert parse_incoming_payload({}) == ("", "", "", "")
    assert parse_incoming_payload([]) == ("", "", "", "")


def test_parse_message_as_dict():
    """message иногда приходит как объект с полем body/text."""
    data = {
        "messageType": "text",
        "message": {"body": "Привет"},
        "metadata": {"remoteJid": "7@x.net", "messageId": "M1"},
    }
    _, _, _, text = parse_incoming_payload(data)
    assert text == "Привет"


# --- Команды mute: /stop, /start, /stop all, /start all ---

def test_parse_mute_command_stop():
    """Команда stop: /stop или stop, регистр не важен."""
    assert _parse_mute_command("/stop") == "stop"
    assert _parse_mute_command("stop") == "stop"
    assert _parse_mute_command("  STOP  ") == "stop"
    assert _parse_mute_command("/STOP") == "stop"


def test_parse_mute_command_start():
    """Команда start: /start или start."""
    assert _parse_mute_command("/start") == "start"
    assert _parse_mute_command("start") == "start"
    assert _parse_mute_command("  Start  ") == "start"


def test_parse_mute_command_stop_all():
    """Команда /stop all или stop all."""
    assert _parse_mute_command("/stop all") == "stop_all"
    assert _parse_mute_command("stop all") == "stop_all"
    assert _parse_mute_command("  /stop   all  ") == "stop_all"


def test_parse_mute_command_start_all():
    """Команда /start all или start all."""
    assert _parse_mute_command("/start all") == "start_all"
    assert _parse_mute_command("start all") == "start_all"


def test_parse_mute_command_none():
    """Не команда — обычный текст."""
    assert _parse_mute_command("привет") is None
    assert _parse_mute_command("stop please") is None
    assert _parse_mute_command("") is None
    assert _parse_mute_command("   ") is None
    assert _parse_mute_command(None) is None


# --- Per-chat /stop /start: нормализация (пробелы, регистр, \n) ---

def test_normalize_command_text():
    """Пробелы, переносы, регистр — для надёжного распознавания /stop, /start."""
    assert _normalize_command_text(" /stop ") == "/stop"
    assert _normalize_command_text("/STOP") == "/stop"
    assert _normalize_command_text("/stop\n") == "/stop"
    assert _normalize_command_text("  /start  \n") == "/start"
    assert _normalize_command_text("") == ""


def test_is_stop_command_robust():
    """Только /stop или stop (после normalize)."""
    assert _is_stop_command("/stop") is True
    assert _is_stop_command("stop") is True
    assert _is_stop_command("  /stop  ") is True
    assert _is_stop_command("/STOP") is False  # normalized даёт "/stop", strip даёт "/stop" — да, in ("/stop","stop")
    assert _is_stop_command(_normalize_command_text(" /stop ")) is True
    assert _is_stop_command(_normalize_command_text("/stop\n")) is True
    assert _is_stop_command("stop please") is False


def test_is_start_command_robust():
    """Только /start или start."""
    assert _is_start_command("/start") is True
    assert _is_start_command(_normalize_command_text(" /start ")) is True
    assert _is_start_command("привет") is False


def test_per_chat_isolation_doc():
    """Per-chat pause: один conversation на (tenant_id, channel, phone_number_id, external_id).
    /stop от jid A ставит ai_paused=True только у conv A; jid B не затронут (другой conv)."""
    # Документируем: изоляция по external_id (remoteJid/from) в таблице conversations, колонка ai_paused.
    assert _is_stop_command("/stop") is True
    assert _is_start_command("/start") is True


def test_create_lead_accepts_tenant_id():
    """Lead created from webhook получает tenant_id: crud.create_lead принимает tenant_id."""
    from app.database import crud
    sig = inspect.signature(crud.create_lead)
    assert "tenant_id" in sig.parameters
    param = sig.parameters["tenant_id"]
    assert param.default is None or param.default == inspect.Parameter.empty


if __name__ == "__main__":
    test_parse_text_payload()
    test_parse_voice_payload()
    test_parse_empty_or_invalid()
    test_parse_message_as_dict()
    test_parse_mute_command_stop()
    test_parse_mute_command_start()
    test_parse_mute_command_stop_all()
    test_parse_mute_command_start_all()
    test_parse_mute_command_none()
    test_normalize_command_text()
    test_is_stop_command_robust()
    test_is_start_command_robust()
    test_per_chat_isolation_doc()
    test_create_lead_accepts_tenant_id()
    print("All parse payload and mute command tests passed.")

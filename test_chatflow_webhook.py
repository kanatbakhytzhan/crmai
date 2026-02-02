"""
Unit-тесты парсинга payload ChatFlow webhook (remoteJid, messageId, messageType, message),
команд /stop /start и логики ai_enabled.
Запуск: python test_chatflow_webhook.py
       или: python -m pytest test_chatflow_webhook.py -v
"""
from app.api.endpoints.chatflow_webhook import parse_incoming_payload, _detect_command


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


# --- Команды /stop /start и ai_enabled ---

def test_detect_command_stop():
    """Команда stop: /stop или stop, регистр не важен."""
    assert _detect_command("/stop") == "stop"
    assert _detect_command("stop") == "stop"
    assert _detect_command("  STOP  ") == "stop"
    assert _detect_command("/STOP") == "stop"


def test_detect_command_start():
    """Команда start: /start или start."""
    assert _detect_command("/start") == "start"
    assert _detect_command("start") == "start"
    assert _detect_command("  Start  ") == "start"


def test_detect_command_none():
    """Не команда — обычный текст."""
    assert _detect_command("привет") == "none"
    assert _detect_command("stop please") == "none"
    assert _detect_command("") == "none"
    assert _detect_command("   ") == "none"
    assert _detect_command(None) == "none"


if __name__ == "__main__":
    test_parse_text_payload()
    test_parse_voice_payload()
    test_parse_empty_or_invalid()
    test_parse_message_as_dict()
    test_detect_command_stop()
    test_detect_command_start()
    test_detect_command_none()
    print("All parse payload and command tests passed.")

import httpx

API = "https://api.telegram.org"


def _call(token: str, method: str, **payload):
    r = httpx.post(f"{API}/bot{token}/{method}", json=payload, timeout=20)
    data = r.json()
    if not data.get("ok"):
        raise ValueError(data.get("description", "Telegram error"))
    return data["result"]


def get_me(token: str) -> dict:
    return _call(token, "getMe")


def set_webhook(token: str, url: str, secret: str):
    return _call(token, "setWebhook", url=url, secret_token=secret, allowed_updates=["message"])


def delete_webhook(token: str):
    return _call(token, "deleteWebhook")


def send_message(token: str, chat_id: int, text: str):
    return _call(token, "sendMessage", chat_id=chat_id, text=text)


def typing(token: str, chat_id: int):
    try:
        _call(token, "sendChatAction", chat_id=chat_id, action="typing")
    except Exception:
        pass

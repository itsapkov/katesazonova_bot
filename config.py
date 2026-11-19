"""
Настройки бота. Все секреты берутся из переменных окружения (.env).
Ничего секретного в этом файле быть не должно.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int = 0) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw)
    except ValueError:
        return default


# --- Telegram ---------------------------------------------------------------
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_CHAT_ID = _int("ADMIN_CHAT_ID")
CONTACT_URL = os.getenv("CONTACT_URL", "https://t.me/KateSazonova")

# --- lava.top ---------------------------------------------------------------
LAVA_API_KEY = (os.getenv("LAVA_API_KEY") or "").strip()
LAVA_BASE_URL = os.getenv("LAVA_BASE_URL", "https://gate.lava.top")

LAVA_OFFER_ID = (os.getenv("LAVA_OFFER_ID") or "").strip()
LAVA_OFFER_ID_RUB = (os.getenv("LAVA_OFFER_ID_RUB") or "").strip() or LAVA_OFFER_ID
LAVA_OFFER_ID_EUR = (os.getenv("LAVA_OFFER_ID_EUR") or "").strip() or LAVA_OFFER_ID
LAVA_OFFER_ID_USD = (os.getenv("LAVA_OFFER_ID_USD") or "").strip() or LAVA_OFFER_ID

OFFER_IDS = {
    "RUB": LAVA_OFFER_ID_RUB,
    "EUR": LAVA_OFFER_ID_EUR,
    "USD": LAVA_OFFER_ID_USD,
}

# --- Веб-сервер для вебхуков lava.top --------------------------------------
PORT = _int("PORT", 8080)
LAVA_WEBHOOK_PATH = os.getenv("LAVA_WEBHOOK_PATH", "/lava-webhook")
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").strip().rstrip("/")

# --- Доступ к продукту ------------------------------------------------------
# Ссылка на Shopping List, которая уходит покупателю после оплаты.
ACCESS_URL = os.getenv("ACCESS_URL", "").strip()

# --- Прочее -----------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "bot.sqlite3")
POLL_INTERVAL = _int("POLL_INTERVAL", 30)
INVOICE_TTL_HOURS = _int("INVOICE_TTL_HOURS", 26)

# --- Цены (фолбэк) ---------------------------------------------------------
FALLBACK_PRICES = {
    "RUB": _int("PRICE_RUB", 4900),
    "EUR": _int("PRICE_EUR", 54),
    "USD": _int("PRICE_USD", 60),
}

CURRENCY_SIGNS = {"RUB": "₽", "EUR": "€", "USD": "$"}

# --- Способы оплаты ---------------------------------------------------------
# Значения по спецификации lava.top /api/v3/invoice:
#   ключ -> (валюта, paymentProvider, paymentMethod, подпись)
# Провайдеры: PAY2ME и SMART_GLOCAL для RUB; UNLIMIT и PAYPAL для EUR/USD.
# Методы: CARD, SBP, APPLE_PAY (PAYPAL задаётся через провайдер без метода).
PAYMENT_METHODS = {
    "RUB_SBP":    ("RUB", "PAY2ME",       "SBP",       "СБП"),
    "RUB_CARD":   ("RUB", "SMART_GLOCAL", "CARD",      "картой"),
    "EUR_APPLE":  ("EUR", "UNLIMIT",      "APPLE_PAY", "Apple Pay"),
    "EUR_PAYPAL": ("EUR", "PAYPAL",       None,        "PayPal"),
    "EUR_CARD":   ("EUR", "UNLIMIT",      "CARD",      "картой"),
    "USD_APPLE":  ("USD", "UNLIMIT",      "APPLE_PAY", "Apple Pay"),
    "USD_PAYPAL": ("USD", "PAYPAL",       None,        "PayPal"),
    "USD_CARD":   ("USD", "UNLIMIT",      "CARD",      "картой"),
}

METHODS_BY_CURRENCY = {
    "RUB": ["RUB_SBP", "RUB_CARD"],
    "EUR": ["EUR_APPLE", "EUR_PAYPAL", "EUR_CARD"],
    "USD": ["USD_APPLE", "USD_PAYPAL", "USD_CARD"],
}


def missing_settings() -> list[str]:
    problems = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN")
    if not LAVA_API_KEY:
        problems.append("LAVA_API_KEY")
    if not any(OFFER_IDS.values()):
        problems.append("LAVA_OFFER_ID")
    if not ACCESS_URL:
        problems.append("ACCESS_URL (после оплаты не будет ссылки на материалы)")
    return problems

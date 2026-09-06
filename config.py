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
# Куда присылать уведомления о новых оплатах (Telegram ID Кати).
# Узнать ID: написать боту команду /id
ADMIN_CHAT_ID = _int("ADMIN_CHAT_ID")
# Личный аккаунт для кнопки «Написать Кате»
CONTACT_URL = os.getenv("CONTACT_URL", "https://t.me/KateSazonova")

# --- lava.top ---------------------------------------------------------------
LAVA_API_KEY = (os.getenv("LAVA_API_KEY") or "").strip()
LAVA_BASE_URL = os.getenv("LAVA_BASE_URL", "https://gate.lava.top")

# offerId продукта из lava.top. Обычно один и тот же для всех валют.
# Получить: python tools/list_offers.py
LAVA_OFFER_ID = (os.getenv("LAVA_OFFER_ID") or "").strip()
# Если у Кати в lava.top заведены РАЗНЫЕ продукты под разные валюты —
# заполните эти переменные, они переопределят LAVA_OFFER_ID.
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
# Публичный адрес сервиса, например https://katesazonova-bot.up.railway.app
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").strip().rstrip("/")

# --- Доступ к продукту ------------------------------------------------------
# Ссылка, которая уходит покупателю после успешной оплаты:
# приглашение в закрытый канал, Notion, Google Drive и т.п.
ACCESS_URL = os.getenv("ACCESS_URL", "").strip()

# --- Прочее -----------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "bot.sqlite3")
# Как часто перепроверять неоплаченные счёта, если вебхук не настроен (сек.)
POLL_INTERVAL = _int("POLL_INTERVAL", 30)
# Сколько часов «жизни» даём счёту (после этого перестаём его опрашивать)
INVOICE_TTL_HOURS = _int("INVOICE_TTL_HOURS", 26)

# --- Цены (фолбэк) ---------------------------------------------------------
# Реальные цены бот подтягивает из lava.top при старте.
# Эти значения используются, только если API недоступен.
FALLBACK_PRICES = {
    "RUB": _int("PRICE_RUB", 4900),
    "EUR": _int("PRICE_EUR", 55),
    "USD": _int("PRICE_USD", 59),
}

CURRENCY_SIGNS = {"RUB": "₽", "EUR": "€", "USD": "$"}

# --- Способы оплаты ---------------------------------------------------------
# Ключ кнопки -> (валюта, paymentMethod в API lava.top, подпись для человека)
# Допустимые paymentMethod: BANK131 (RUB), UNLIMINT / PAYPAL / STRIPE (EUR, USD)
PAYMENT_METHODS = {
    "RUB_SBP":    ("RUB", "BANK131", "СБП"),
    "RUB_CARD":   ("RUB", "BANK131", "картой"),
    "EUR_APPLE":  ("EUR", "UNLIMINT", "Apple Pay"),
    "EUR_PAYPAL": ("EUR", "PAYPAL", "PayPal"),
    "EUR_CARD":   ("EUR", "UNLIMINT", "картой"),
    "USD_APPLE":  ("USD", "UNLIMINT", "Apple Pay"),
    "USD_PAYPAL": ("USD", "PAYPAL", "PayPal"),
    "USD_CARD":   ("USD", "UNLIMINT", "картой"),
}

# Кнопки способов оплаты по валютам (порядок = порядок на экране)
METHODS_BY_CURRENCY = {
    "RUB": ["RUB_SBP", "RUB_CARD"],
    "EUR": ["EUR_APPLE", "EUR_PAYPAL", "EUR_CARD"],
    "USD": ["USD_APPLE", "USD_PAYPAL", "USD_CARD"],
}


def missing_settings() -> list[str]:
    """Что не заполнено — печатаем при старте, чтобы не искать вслепую."""
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

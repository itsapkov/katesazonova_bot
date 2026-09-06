"""
Telegram-бот для курса Кати Сазоновой «КАПСУЛА FW 26/27».

Что делает:
  · рассказывает о Кате и курсе (несколько экранов с кнопками)
  · принимает оплату через lava.top: RUB (СБП / карта), EUR и USD (Apple Pay / PayPal / карта)
  · на каждый выбранный способ создаёт отдельную одноразовую ссылку на оплату
  · после оплаты сам присылает доступ в этот же чат (вебхук lava.top + фолбэк-опрос)

Запуск: python bot.py
"""
import asyncio
import logging
import re
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web

import config
import texts
from lava import LavaClient, LavaError, extract_prices
from storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[A-Za-z]{2,}$")

router = Router()
storage = Storage(config.DB_PATH)
lava = LavaClient(config.LAVA_API_KEY, config.LAVA_BASE_URL)
PRICES: dict[str, int] = dict(config.FALLBACK_PRICES)


class PayFlow(StatesGroup):
    email = State()


# --- Вспомогательное --------------------------------------------------------
def fmt_amount(currency: str, amount: float | int) -> str:
    value = int(round(float(amount)))
    sign = config.CURRENCY_SIGNS.get(currency, currency)
    if currency == "RUB":
        return f"{value:,}".replace(",", " ") + f" {sign}"
    return f"{value} {sign}"


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def menu_kb() -> InlineKeyboardMarkup:
    return kb(
        [InlineKeyboardButton(text=texts.BTN_ABOUT, callback_data="about:0")],
        [InlineKeyboardButton(text=texts.BTN_PROGRAM, callback_data="program")],
        [InlineKeyboardButton(text=texts.BTN_FAQ, callback_data="faq")],
        [InlineKeyboardButton(text=texts.BTN_PAY, callback_data="pay")],
        [InlineKeyboardButton(text=texts.BTN_CONTACT, url=config.CONTACT_URL)],
    )


def about_kb(page: int) -> InlineKeyboardMarkup:
    total = len(texts.ABOUT_PAGES)
    rows: list[list[InlineKeyboardButton]] = []
    if page + 1 < total:
        rows.append([
            InlineKeyboardButton(
                text=f"Дальше · {page + 2}/{total}", callback_data=f"about:{page + 1}"
            )
        ])
    rows.append([InlineKeyboardButton(text=texts.BTN_PAY, callback_data="pay")])
    rows.append([InlineKeyboardButton(text=texts.BTN_MENU, callback_data="menu")])
    return kb(*rows)


def currency_kb() -> InlineKeyboardMarkup:
    return kb(
        [InlineKeyboardButton(
            text=f"Оплатить в рублях — {fmt_amount('RUB', PRICES['RUB'])}",
            callback_data="cur:RUB")],
        [InlineKeyboardButton(
            text=f"Оплатить в евро — {fmt_amount('EUR', PRICES['EUR'])}",
            callback_data="cur:EUR")],
        [InlineKeyboardButton(
            text=f"Оплатить в долларах — {fmt_amount('USD', PRICES['USD'])}",
            callback_data="cur:USD")],
        [InlineKeyboardButton(text=texts.BTN_MENU, callback_data="menu")],
    )


def methods_kb(currency: str) -> InlineKeyboardMarkup:
    labels = {
        "RUB_SBP": "СБП",
        "RUB_CARD": "Картой",
        "EUR_APPLE": "Apple Pay",
        "EUR_PAYPAL": "PayPal",
        "EUR_CARD": "Картой",
        "USD_APPLE": "Apple Pay",
        "USD_PAYPAL": "PayPal",
        "USD_CARD": "Картой",
    }
    rows = [
        [InlineKeyboardButton(text=labels[key], callback_data=f"m:{key}")]
        for key in config.METHODS_BY_CURRENCY[currency]
    ]
    rows.append([InlineKeyboardButton(text=texts.BTN_BACK, callback_data="pay")])
    return kb(*rows)


async def show_menu(target: Message | CallbackQuery) -> None:
    message = target.message if isinstance(target, CallbackQuery) else target
    await message.answer(texts.MENU, reply_markup=menu_kb())


async def edit_or_send(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Пытаемся отредактировать сообщение; если нельзя (например, это фото) — отправляем новое."""
    try:
        await call.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest:
        await call.message.answer(text, reply_markup=markup, disable_web_page_preview=True)


# --- Хендлеры ---------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await storage.upsert_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await message.answer(texts.WELCOME, reply_markup=menu_kb(), disable_web_page_preview=True)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_menu(message)


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(texts.my_id(message.from_user.id))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if config.ADMIN_CHAT_ID and message.from_user.id != config.ADMIN_CHAT_ID:
        return
    s = await storage.stats()
    await message.answer(
        f"Пользователей: {s['users']}\nОплатили: {s['paid']}\nСчетов создано: {s['invoices']}"
    )


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(call, texts.MENU, menu_kb())
    await call.answer()


@router.callback_query(F.data.startswith("about:"))
async def cb_about(call: CallbackQuery) -> None:
    page = int(call.data.split(":")[1])
    page = max(0, min(page, len(texts.ABOUT_PAGES) - 1))
    await edit_or_send(call, texts.ABOUT_PAGES[page], about_kb(page))
    await call.answer()


@router.callback_query(F.data == "program")
async def cb_program(call: CallbackQuery) -> None:
    await edit_or_send(
        call,
        texts.PROGRAM,
        kb(
            [InlineKeyboardButton(text=texts.BTN_PAY, callback_data="pay")],
            [InlineKeyboardButton(text=texts.BTN_MENU, callback_data="menu")],
        ),
    )
    await call.answer()


@router.callback_query(F.data == "faq")
async def cb_faq(call: CallbackQuery) -> None:
    await edit_or_send(
        call,
        texts.FAQ,
        kb(
            [InlineKeyboardButton(text=texts.BTN_PAY, callback_data="pay")],
            [InlineKeyboardButton(text=texts.BTN_CONTACT, url=config.CONTACT_URL)],
            [InlineKeyboardButton(text=texts.BTN_MENU, callback_data="menu")],
        ),
    )
    await call.answer()


@router.callback_query(F.data == "pay")
async def cb_pay(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(call, texts.pay_intro(PRICES), currency_kb())
    await call.answer()


@router.callback_query(F.data.startswith("cur:"))
async def cb_currency(call: CallbackQuery) -> None:
    currency = call.data.split(":")[1]
    if currency not in config.METHODS_BY_CURRENCY:
        await call.answer()
        return
    text = texts.METHOD_SCREENS[currency].format(
        amount=f"{PRICES[currency]:,}".replace(",", " ")
    )
    await edit_or_send(call, text, methods_kb(currency))
    await call.answer()


@router.callback_query(F.data.startswith("m:"))
async def cb_method(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    if key not in config.PAYMENT_METHODS:
        await call.answer()
        return
    await state.set_state(PayFlow.email)
    await state.update_data(method_key=key)

    saved_email = await storage.get_email(call.from_user.id)
    rows = []
    if saved_email:
        rows.append([InlineKeyboardButton(
            text=f"Использовать {saved_email}", callback_data="use_saved_email"
        )])
    rows.append([InlineKeyboardButton(text=texts.BTN_BACK, callback_data="pay")])

    await edit_or_send(call, texts.EMAIL_PROMPT, kb(*rows))
    await call.answer()


@router.callback_query(F.data == "use_saved_email", PayFlow.email)
async def cb_saved_email(call: CallbackQuery, state: FSMContext) -> None:
    email = await storage.get_email(call.from_user.id)
    if not email:
        await call.answer("Почта не найдена, напишите её сообщением", show_alert=True)
        return
    await call.answer()
    await create_and_send_invoice(call.message, call.from_user.id, email, state)


@router.message(PayFlow.email, F.text)
async def on_email(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    if not EMAIL_RE.match(email):
        await message.answer(
            texts.EMAIL_INVALID,
            reply_markup=kb([InlineKeyboardButton(text=texts.BTN_BACK, callback_data="pay")]),
        )
        return
    await storage.set_email(message.from_user.id, email)
    await create_and_send_invoice(message, message.from_user.id, email, state)


async def create_and_send_invoice(
    message: Message, tg_id: int, email: str, state: FSMContext
) -> None:
    data = await state.get_data()
    key = data.get("method_key")
    await state.clear()
    if key not in config.PAYMENT_METHODS:
        await show_menu(message)
        return

    currency, payment_method, label = config.PAYMENT_METHODS[key]
    offer_id = config.OFFER_IDS.get(currency, "")
    if not offer_id:
        log.error("Не задан offerId для валюты %s", currency)
        await message.answer(texts.PAYMENT_ERROR, reply_markup=menu_kb())
        return

    notice = await message.answer("Готовлю ссылку…")
    try:
        invoice = await lava.create_invoice(
            email=email,
            offer_id=offer_id,
            currency=currency,
            payment_method=payment_method,
            utm={"utm_source": "telegram_bot", "utm_content": str(tg_id)},
        )
    except LavaError as err:
        log.exception("Не удалось создать счёт: %s", err)
        await notice.edit_text(texts.PAYMENT_ERROR)
        await message.answer(
            texts.MENU,
            reply_markup=kb(
                [InlineKeyboardButton(text=texts.BTN_CONTACT, url=config.CONTACT_URL)],
                [InlineKeyboardButton(text=texts.BTN_MENU, callback_data="menu")],
            ),
        )
        return

    invoice_id = str(invoice.get("id") or "")
    payment_url = invoice["paymentUrl"]
    amount_total = invoice.get("amountTotal") or {}
    amount = amount_total.get("amount", PRICES.get(currency))

    await storage.add_invoice(
        invoice_id, tg_id, email, currency, label, amount, payment_url
    )

    button_text = f"Открыть оплату · {fmt_amount(currency, amount)} · {label}"
    rows = [[InlineKeyboardButton(text=button_text, url=payment_url)]]
    if invoice_id:
        rows.append([InlineKeyboardButton(
            text=texts.BTN_CHECK, callback_data=f"check:{invoice_id}"
        )])
    rows.append([InlineKeyboardButton(text=texts.BTN_OTHER_METHOD, callback_data="pay")])

    await notice.edit_text(
        texts.link_ready(label), reply_markup=kb(*rows), disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith("check:"))
async def cb_check(call: CallbackQuery, bot: Bot) -> None:
    invoice_id = call.data.split(":", 1)[1]
    try:
        data = await lava.get_invoice(invoice_id)
    except LavaError:
        await call.answer(texts.NOT_PAID_YET, show_alert=True)
        return

    status = str(data.get("status") or "").lower()
    if status in ("completed", "paid", "success", "subscription-active"):
        await call.answer("Оплата найдена!")
        await handle_paid_invoice(bot, invoice_id, source="manual")
    else:
        await call.answer(texts.NOT_PAID_YET, show_alert=True)


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer(texts.FALLBACK, reply_markup=menu_kb())


# --- Выдача доступа ---------------------------------------------------------
async def handle_paid_invoice(bot: Bot, invoice_id: str, source: str = "webhook") -> None:
    invoice = await storage.get_invoice(invoice_id)
    if invoice is None:
        log.warning("Оплата по неизвестному счёту %s (%s)", invoice_id, source)
        return
    first_time = await storage.mark_invoice(invoice_id, "completed")
    if not first_time:
        return

    tg_id = invoice["tg_id"]
    await storage.mark_user_paid(tg_id)
    try:
        await bot.send_message(
            tg_id,
            texts.access_granted(config.ACCESS_URL),
            reply_markup=kb(
                [InlineKeyboardButton(text=texts.BTN_CONTACT, url=config.CONTACT_URL)],
            ),
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Не смогла отправить доступ пользователю %s", tg_id)

    if config.ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                "💸 Новая оплата\n"
                f"{fmt_amount(invoice['currency'], invoice['amount'] or 0)} · {invoice['method']}\n"
                f"{invoice['email']}\n"
                f"tg id: {tg_id}\n"
                f"источник: {source}",
            )
        except Exception:
            log.exception("Не смогла уведомить админа")


async def handle_failed_invoice(invoice_id: str) -> None:
    await storage.mark_invoice(invoice_id, "failed")


# --- Вебхук lava.top --------------------------------------------------------
async def lava_webhook(request: web.Request) -> web.Response:
    # Мягкая проверка: если lava.top прислала X-Api-Key, он должен совпадать с нашим.
    header_key = request.headers.get("X-Api-Key")
    if header_key and config.LAVA_API_KEY and header_key != config.LAVA_API_KEY:
        return web.Response(status=403, text="forbidden")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    log.info("Вебхук lava.top: %s", payload)
    event = str(payload.get("eventType") or "")
    contract_id = str(payload.get("contractId") or "")
    status = str(payload.get("status") or "").lower()
    email = ((payload.get("buyer") or {}).get("email") or "").strip()

    invoice_id = contract_id
    if invoice_id and await storage.get_invoice(invoice_id) is None and email:
        # Иногда contractId отличается от id счёта — пробуем найти по почте.
        by_email = await storage.latest_invoice_by_email(email)
        if by_email:
            invoice_id = by_email["id"]

    bot: Bot = request.app["bot"]
    if event.endswith("payment.success") or status in ("completed", "subscription-active"):
        if invoice_id:
            await handle_paid_invoice(bot, invoice_id, source="webhook")
    elif event.endswith("payment.failed"):
        if invoice_id:
            await handle_failed_invoice(invoice_id)

    return web.json_response({"status": "ok"})


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def run_web_app(bot: Bot) -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post(config.LAVA_WEBHOOK_PATH, lava_webhook)
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.PORT)
    await site.start()
    hook = f"{config.PUBLIC_URL}{config.LAVA_WEBHOOK_PATH}" if config.PUBLIC_URL else \
        f"http://0.0.0.0:{config.PORT}{config.LAVA_WEBHOOK_PATH}"
    log.info("Вебхук слушает: %s", hook)
    return runner


# --- Фолбэк: опрос статусов счетов -----------------------------------------
async def poll_invoices(bot: Bot) -> None:
    """Если вебхук не настроен (или не дошёл) — проверяем счёта сами."""
    while True:
        await asyncio.sleep(config.POLL_INTERVAL)
        try:
            pending = await storage.pending_invoices(config.INVOICE_TTL_HOURS)
            for invoice in pending:
                try:
                    data = await lava.get_invoice(invoice["id"])
                except LavaError:
                    continue
                status = str(data.get("status") or "").lower()
                if status in ("completed", "paid", "success", "subscription-active"):
                    await handle_paid_invoice(bot, invoice["id"], source="poller")
                elif status in ("failed", "cancelled", "canceled", "error"):
                    await handle_failed_invoice(invoice["id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Ошибка в опросе счетов")


async def refresh_prices() -> None:
    """Тянем актуальные цены из lava.top, чтобы кнопки не расходились с кассой."""
    global PRICES
    try:
        products = await lava.get_products()
    except LavaError:
        log.warning("Не удалось получить цены из lava.top, использую значения из .env")
        return
    found = extract_prices(products, config.OFFER_IDS.get("RUB") or None)
    if found:
        PRICES = {**PRICES, **found}
        log.info("Цены из lava.top: %s", found)


# --- Точка входа ------------------------------------------------------------
async def main() -> None:
    problems = config.missing_settings()
    if problems:
        log.warning("Не заполнено в .env: %s", ", ".join(problems))
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN обязателен. Заполните .env и запустите снова.")

    await storage.init()

    bot = Bot(
        config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    await refresh_prices()
    runner = await run_web_app(bot)
    poller = asyncio.create_task(poll_invoices(bot))

    await bot.set_my_commands([
        BotCommand(command="start", description="Начать сначала"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="id", description="Мой Telegram ID"),
    ])

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        poller.cancel()
        await runner.cleanup()
        await lava.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

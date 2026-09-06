"""
Минимальный клиент lava.top (gate.lava.top).

Документация: https://gate.lava.top/docs
Авторизация: заголовок X-Api-Key с ключом из личного кабинета lava.top.
"""
import logging
from typing import Any

import aiohttp

log = logging.getLogger("lava")


class LavaError(Exception):
    def __init__(self, message: str, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class LavaClient:
    def __init__(self, api_key: str, base_url: str = "https://gate.lava.top"):
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=25),
                headers={
                    "X-Api-Key": self._api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        session = await self._get_session()
        url = f"{self._base}{path}"
        async with session.request(method, url, **kwargs) as resp:
            text = await resp.text()
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = text
            if resp.status >= 400:
                log.error("lava %s %s -> %s %s", method, path, resp.status, text[:500])
                raise LavaError(f"lava.top {resp.status}", resp.status, data)
            return data

    # --- Продукты -----------------------------------------------------------
    async def get_products(self) -> Any:
        """Список продуктов автора вместе с offers и ценами по валютам."""
        return await self._request("GET", "/api/v2/products")

    # --- Счёта --------------------------------------------------------------
    async def create_invoice(
        self,
        *,
        email: str,
        offer_id: str,
        currency: str,
        payment_method: str | None = None,
        buyer_language: str = "RU",
        utm: dict | None = None,
    ) -> dict:
        """
        Создаёт одноразовый счёт и возвращает словарь с полями
        id / status / amountTotal / paymentUrl.
        """
        body: dict[str, Any] = {
            "email": email,
            "offerId": offer_id,
            "currency": currency,
            "buyerLanguage": buyer_language,
            "periodicity": "ONE_TIME",
        }
        if payment_method:
            body["paymentMethod"] = payment_method
        if utm:
            body["clientUtm"] = utm

        try:
            data = await self._request("POST", "/api/v2/invoice", json=body)
        except LavaError as err:
            # Некоторые аккаунты не принимают поле periodicity для разовых продуктов —
            # пробуем ещё раз без него, чтобы не терять покупателя.
            if err.status == 400 and "periodicity" in body:
                body.pop("periodicity")
                log.warning("Повтор запроса счёта без periodicity")
                data = await self._request("POST", "/api/v2/invoice", json=body)
            else:
                raise

        if not isinstance(data, dict) or not data.get("paymentUrl"):
            raise LavaError("В ответе lava.top нет paymentUrl", payload=data)
        return data

    async def get_invoice(self, invoice_id: str) -> dict:
        data = await self._request("GET", f"/api/v1/invoices/{invoice_id}")
        if not isinstance(data, dict):
            raise LavaError("Неожиданный ответ по счёту", payload=data)
        return data


def extract_prices(products: Any, offer_id: str | None = None) -> dict[str, int]:
    """
    Достаёт цены по валютам из ответа /api/v2/products.
    Если передан offer_id — берёт цены именно этого оффера, иначе первого найденного.
    Возвращает, например, {"RUB": 4900, "EUR": 55, "USD": 59}.
    """
    offers = find_offer_ids(products)
    if not offers:
        return {}
    chosen = None
    if offer_id:
        for _, oid, prices in offers:
            if oid == offer_id:
                chosen = prices
                break
    if chosen is None:
        chosen = offers[0][2]

    result: dict[str, int] = {}
    for currency, amount in chosen.items():
        if isinstance(amount, (int, float)) and currency in ("RUB", "EUR", "USD"):
            result[currency] = int(round(float(amount)))
    return result


def find_offer_ids(products: Any) -> list[tuple[str, str, dict]]:
    """
    Возвращает [(product_title, offer_id, {currency: price}), ...]
    Используется скриптом tools/list_offers.py.
    """
    found: list[tuple[str, str, dict]] = []

    def walk(node: Any, title: str = "") -> None:
        if isinstance(node, dict):
            title = node.get("title") or node.get("name") or title
            offers = node.get("offers")
            if isinstance(offers, list):
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    offer_id = offer.get("id")
                    if not offer_id:
                        continue
                    prices = {}
                    for price in offer.get("prices") or []:
                        if isinstance(price, dict) and price.get("currency"):
                            prices[str(price["currency"]).upper()] = price.get("amount", price.get("price"))
                    found.append((offer.get("name") or title, str(offer_id), prices))
            for value in node.values():
                walk(value, title)
        elif isinstance(node, list):
            for item in node:
                walk(item, title)

    walk(products)
    return found

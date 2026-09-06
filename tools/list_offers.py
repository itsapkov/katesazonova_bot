"""
Показывает продукты Кати в lava.top и их offerId — то, что нужно вписать
в .env как LAVA_OFFER_ID.

Запуск из папки проекта:  python tools/list_offers.py
Нужен только заполненный LAVA_API_KEY в .env
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from lava import LavaClient, find_offer_ids  # noqa: E402


async def main() -> None:
    if not config.LAVA_API_KEY:
        raise SystemExit("Заполните LAVA_API_KEY в .env")

    client = LavaClient(config.LAVA_API_KEY, config.LAVA_BASE_URL)
    try:
        products = await client.get_products()
    finally:
        await client.close()

    offers = find_offer_ids(products)
    if not offers:
        print("Офферы не найдены. Полный ответ API ниже — пришлите его разработчику:\n")
        print(json.dumps(products, ensure_ascii=False, indent=2)[:4000])
        return

    print("Найденные офферы:\n")
    for title, offer_id, prices in offers:
        pretty = ", ".join(f"{cur} {val}" for cur, val in prices.items()) or "цены не указаны"
        print(f"  {title}")
        print(f"    offerId: {offer_id}")
        print(f"    цены:    {pretty}\n")

    print("Скопируйте нужный offerId в .env:  LAVA_OFFER_ID=...")


if __name__ == "__main__":
    asyncio.run(main())

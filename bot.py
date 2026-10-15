"""Telegram-бот с приёмом оплаты: Telegram Stars и USDT (Crypto Bot). Товар выдаётся автоматически."""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
                           Message, PreCheckoutQuery)
from dotenv import load_dotenv

import catalog
import orders
from cryptopay import CryptoPay, CryptoPayError

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CRYPTO_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
crypto = CryptoPay(CRYPTO_TOKEN, testnet=os.getenv("CRYPTO_PAY_TESTNET", "1") == "1") if CRYPTO_TOKEN else None

dp = Dispatcher()
METHOD_NAMES = {"stars": "⭐ Stars", "usdt": "💵 USDT"}


def kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, **({"url": d} if d.startswith("http") else {"callback_data": d})) for t, d in row]
        for row in rows])


def catalog_kb() -> InlineKeyboardMarkup:
    return kb([[(p["title"], f"item:{k}")] for k, p in catalog.PRODUCTS.items()])


async def notify_admin(bot: Bot, text: str):
    if ADMIN_CHAT_ID:
        await bot.send_message(ADMIN_CHAT_ID, text)


async def deliver(bot: Bot, order_id: int, charge_id: str | None = None):
    """Выдаёт товар ровно один раз, даже если уведомление об оплате пришло повторно."""
    if not orders.mark_paid(order_id, charge_id):
        return
    order = orders.get(order_id)
    product = catalog.PRODUCTS[order["product"]]
    await bot.send_message(order["user_id"], f"✅ <b>Оплата получена</b>\n\n{product['delivery']}")
    await notify_admin(bot, f"💰 <b>Оплата #{order_id}</b>\n{product['title']}\n"
                            f"{METHOD_NAMES[order['method']]}: {order['amount']}\n"
                            f"👤 {order['user_id']} @{order['username'] or '—'}")


# ---------- Каталог ----------

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(catalog.WELCOME, reply_markup=catalog_kb())


@dp.message(Command("myid"))
async def my_id(message: Message):
    await message.answer(f"ID этого чата: <code>{message.chat.id}</code>")


@dp.callback_query(F.data.startswith("item:"))
async def item(cb: CallbackQuery):
    key = cb.data[5:]
    p = catalog.PRODUCTS[key]
    rows = [[(f"⭐ Оплатить {p['stars']} Stars", f"stars:{key}")]]
    if crypto:
        rows.append([(f"💵 Оплатить {p['usdt']} USDT", f"usdt:{key}")])
    rows.append([("← Все товары", "catalog")])
    await cb.message.edit_text(f"<b>{p['title']}</b>\n\n{p['description']}", reply_markup=kb(rows))
    await cb.answer()


@dp.callback_query(F.data == "catalog")
async def back(cb: CallbackQuery):
    await cb.message.edit_text(catalog.WELCOME, reply_markup=catalog_kb())
    await cb.answer()


# ---------- Telegram Stars ----------

@dp.callback_query(F.data.startswith("stars:"))
async def pay_stars(cb: CallbackQuery, bot: Bot):
    key = cb.data[6:]
    p = catalog.PRODUCTS[key]
    order_id = orders.create(cb.from_user.id, cb.from_user.username, key, "stars", p["stars"])
    await bot.send_invoice(cb.from_user.id, title=p["title"][:32], description=p["description"],
                           payload=str(order_id), currency="XTR",
                           prices=[LabeledPrice(label=p["title"][:32], amount=p["stars"])])
    await cb.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    order = orders.get(int(query.invoice_payload))
    if order and order["status"] == "created":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Этот счёт уже недействителен. Создайте новый заказ.")


@dp.message(F.successful_payment)
async def stars_paid(message: Message, bot: Bot):
    payment = message.successful_payment
    await deliver(bot, int(payment.invoice_payload), payment.telegram_payment_charge_id)


# ---------- USDT через Crypto Bot ----------

@dp.callback_query(F.data.startswith("usdt:"))
async def pay_usdt(cb: CallbackQuery):
    key = cb.data[5:]
    p = catalog.PRODUCTS[key]
    order_id = orders.create(cb.from_user.id, cb.from_user.username, key, "usdt", p["usdt"])
    try:
        invoice = await crypto.create_invoice(p["usdt"], p["title"], str(order_id), catalog.INVOICE_TTL)
    except (CryptoPayError, asyncio.TimeoutError, OSError) as e:
        logging.error("Crypto Pay: %s", e)
        orders.mark(order_id, "error")
        return await cb.answer("Платёжный сервис временно недоступен, попробуйте позже", show_alert=True)

    orders.set_invoice(order_id, str(invoice["invoice_id"]))
    await cb.message.answer(
        f"💵 Счёт на <b>{p['usdt']} USDT</b> создан.\n\nНажмите кнопку, оплатите в Crypto Bot — "
        f"товар придёт сюда автоматически.\nСчёт действует {catalog.INVOICE_TTL // 60} минут.",
        reply_markup=kb([[("💵 Оплатить в Crypto Bot", CryptoPay.pay_url(invoice))]]))
    await cb.answer()


async def crypto_watcher(bot: Bot):
    """Каждые 15 секунд проверяет открытые крипто-счета: оплачен → выдать товар, истёк → сообщить."""
    while True:
        try:
            pending = orders.pending_crypto()
            statuses = await crypto.get_statuses([o["invoice_id"] for o in pending if o["invoice_id"]])
            for o in pending:
                status = statuses.get(o["invoice_id"])
                if status == "paid":
                    await deliver(bot, o["id"])
                elif status == "expired":
                    orders.mark(o["id"], "expired")
                    await bot.send_message(o["user_id"], "⌛ Время на оплату счёта истекло. "
                                                         "Если всё ещё хотите купить — создайте новый заказ.",
                                           reply_markup=catalog_kb())
        except Exception:
            logging.exception("Ошибка проверки крипто-счетов")
        await asyncio.sleep(15)


# ---------- Для администратора ----------

def is_admin(message: Message) -> bool:
    return str(message.chat.id) == str(ADMIN_CHAT_ID)


@dp.message(Command("orders"))
async def admin_orders(message: Message):
    if not is_admin(message):
        return
    lines = [f"{METHOD_NAMES.get(r['method'], r['method'])} · {r['status']}: {r['n']} шт., {r['total'] or 0:g}"
             for r in orders.stats()]
    last = [f"#{o['id']} {catalog.PRODUCTS[o['product']]['title'][:25]} · {o['amount']} · {o['status']}"
            for o in orders.recent()]
    await message.answer("<b>Сводка</b>\n" + ("\n".join(lines) or "заказов нет") +
                         "\n\n<b>Последние заказы</b>\n" + ("\n".join(last) or "—"))


@dp.message(Command("refund"))
async def admin_refund(message: Message, bot: Bot):
    """/refund 12 — вернуть Stars по заказу #12."""
    if not is_admin(message):
        return
    parts = message.text.split()
    order = orders.get(int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else None
    if not order or order["method"] != "stars" or order["status"] != "paid":
        return await message.answer("Использование: /refund <номер оплаченного заказа в Stars>")
    await bot.refund_star_payment(order["user_id"], order["charge_id"])
    orders.mark(order["id"], "refunded")
    await message.answer(f"↩️ Возврат по заказу #{order['id']} выполнен.")
    await bot.send_message(order["user_id"], f"↩️ Оплата по заказу #{order['id']} возвращена.")


async def main():
    if not BOT_TOKEN:
        raise SystemExit("Не найден BOT_TOKEN. Скопируйте .env.example в .env и вставьте токен.")
    logging.basicConfig(level=logging.INFO)
    orders.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    if crypto:
        asyncio.create_task(crypto_watcher(bot))
    else:
        logging.warning("CRYPTO_PAY_TOKEN не задан — оплата в USDT отключена, работает только Stars")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

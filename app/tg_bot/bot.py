"""Telegram-бот HR-анализатор (aiogram 3)."""
from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    LabeledPrice,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
    Document,
)

from ai import analyze
from db import DB
from parsers import parse_document

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("hr-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
DAILY_FREE_LIMIT = int(os.environ.get("DAILY_FREE_LIMIT", "1"))
UNLIMITED_PRICE_STARS = int(os.environ.get("UNLIMITED_PRICE_STARS", "100"))
DB_PATH = os.environ.get("DB_PATH", "bot.db")

MAX_FILE_MB = 15
MIN_TEXT_LEN = 50

db = DB(DB_PATH)
router = Router()


class Flow(StatesGroup):
    waiting_resume = State()
    waiting_job = State()


def paywall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"⭐ Купить безлимит на 24ч за {UNLIMITED_PRICE_STARS} Stars",
                callback_data="buy_unlimited",
            )
        ]]
    )


async def download_file(bot: Bot, doc: Document) -> bytes:
    file = await bot.get_file(doc.file_id)
    buf = await bot.download_file(file.file_path)
    return buf.read()


def looks_like_job(text: str) -> bool:
    t = text.lower()
    markers = ["требован", "обязанност", "мы предлагаем", "условия", "ищем", "зарплат", "опыт от", "стек", "з/п"]
    return sum(m in t for m in markers) >= 2


def looks_like_resume(text: str) -> bool:
    t = text.lower()
    markers = ["опыт работы", "образование", "навыки", "резюме", "родил", "github", "email", "телефон", "@"]
    return sum(m in t for m in markers) >= 2


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Flow.waiting_resume)
    await msg.answer(
        "👋 Привет! Я помогу разобрать твоё резюме под конкретную вакансию.\n\n"
        "📎 *Пришли мне резюме* (текст или PDF/DOCX файл), потом текст вакансии — "
        "получишь разбор за 30 секунд.\n\n"
        f"Бесплатно: *{DAILY_FREE_LIMIT} разбор в сутки*."
    )


@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(
        "*Как пользоваться:*\n"
        "1. /start\n"
        "2. Пришли резюме (текст / PDF / DOCX)\n"
        "3. Пришли текст вакансии\n"
        "4. Получи разбор ✨\n\n"
        "/reset — начать заново"
    )


@router.message(Command("reset"))
async def cmd_reset(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Flow.waiting_resume)
    await msg.answer("Ок, начнём заново. Пришли резюме (текст или PDF/DOCX).")


@router.message(Flow.waiting_resume, F.document)
async def resume_as_file(msg: Message, state: FSMContext, bot: Bot) -> None:
    doc = msg.document
    if doc.file_size and doc.file_size > MAX_FILE_MB * 1024 * 1024:
        await msg.answer(f"Файл слишком большой (>{MAX_FILE_MB} MB). Пришли текстом или уменьши.")
        return
    name = (doc.file_name or "").lower()
    if not (name.endswith(".pdf") or name.endswith(".docx")):
        await msg.answer("Поддерживаю только *PDF* или *DOCX*. Или пришли резюме обычным текстом.")
        return
    try:
        data = await download_file(bot, doc)
        text = parse_document(doc.file_name, data)
    except Exception as e:
        log.exception("parse fail: %s", e)
        await msg.answer("Не смог распарсить файл 😕 Пришли, пожалуйста, резюме *текстом*.")
        return
    if len(text) < MIN_TEXT_LEN:
        await msg.answer("В файле почти нет текста (возможно, скан). Пришли резюме *текстом*.")
        return
    await state.update_data(resume=text)
    await state.set_state(Flow.waiting_job)
    await msg.answer("✅ Резюме получил. Теперь пришли *текст вакансии*.")


@router.message(Flow.waiting_resume, F.text)
async def resume_as_text(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip()
    if len(text) < MIN_TEXT_LEN:
        await msg.answer("Похоже, это не резюме. Пришли полный текст резюме или файл PDF/DOCX.")
        return
    if looks_like_job(text) and not looks_like_resume(text):
        await msg.answer("Кажется, ты прислал *вакансию*, а не резюме. Сначала пришли резюме 🙂")
        return
    await state.update_data(resume=text)
    await state.set_state(Flow.waiting_job)
    await msg.answer("✅ Резюме получил. Теперь пришли *текст вакансии*.")


@router.message(Flow.waiting_resume)
async def resume_other(msg: Message) -> None:
    await msg.answer("Жду *резюме* — текстом или файлом PDF/DOCX.")


@router.message(Flow.waiting_job, F.text)
async def job_text(msg: Message, state: FSMContext, bot: Bot) -> None:
    job = msg.text.strip()
    if len(job) < MIN_TEXT_LEN:
        await msg.answer("Похоже, это не текст вакансии. Пришли полное описание.")
        return
    data = await state.get_data()
    resume = data.get("resume")
    if not resume:
        await state.set_state(Flow.waiting_resume)
        await msg.answer("Сначала мне нужно *резюме*. Пришли его текстом или файлом.")
        return

    unlimited = await db.is_unlimited(msg.from_user.id)
    if not unlimited and not await db.can_use_free(msg.from_user.id, DAILY_FREE_LIMIT):
        await msg.answer(
            "🚫 Лимит бесплатных разборов на сегодня исчерпан.\n"
            f"Можешь купить *безлимит на 24 часа* за {UNLIMITED_PRICE_STARS} ⭐.",
            reply_markup=paywall_kb(),
        )
        return

    await msg.answer("🔎 Анализирую… (~30 сек)")
    try:
        result = await analyze(resume, job)
    except Exception as e:
        log.exception("AI fail: %s", e)
        await msg.answer("Не получилось сделать разбор 😕 Попробуй ещё раз через минуту.")
        return

    if not unlimited:
        await db.register_use(msg.from_user.id)

    await msg.answer(result, parse_mode=ParseMode.MARKDOWN)
    await msg.answer("Готово! Пришли *новое резюме*, чтобы разобрать ещё одну связку.")
    await state.set_state(Flow.waiting_resume)


@router.message(Flow.waiting_job, F.document)
async def job_as_file(msg: Message) -> None:
    await msg.answer("Пришли *текст вакансии* сообщением (не файлом).")


@router.message(Flow.waiting_job)
async def job_other(msg: Message) -> None:
    await msg.answer("Жду *текст вакансии*.")


@router.message(F.text)
async def fallback(msg: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await state.set_state(Flow.waiting_resume)
        await msg.answer("Начнём! Пришли резюме (текст или PDF/DOCX).")


@router.callback_query(F.data == "buy_unlimited")
async def buy_unlimited(cb, bot: Bot) -> None:
    await cb.answer()
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title="Безлимит на 24 часа",
        description="Неограниченное количество разборов резюме под вакансии в течение 24 часов.",
        payload=f"unlimited_24h:{cb.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Безлимит 24ч", amount=UNLIMITED_PRICE_STARS)],
    )


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery, bot: Bot) -> None:
    await bot.answer_pre_checkout_query(q.id, ok=True)


@router.message(F.successful_payment)
async def on_paid(msg: Message) -> None:
    sp = msg.successful_payment
    user_id = msg.from_user.id
    until = await db.grant_unlimited(user_id, hours=24)
    await db.save_payment(sp.telegram_payment_charge_id, user_id, sp.total_amount)
    await msg.answer(
        f"✅ Оплата получена! Безлимит активен до *{until.strftime('%Y-%m-%d %H:%M UTC')}*.\n"
        "Присылай резюме — разберём!"
    )


async def main() -> None:
    await db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info("Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

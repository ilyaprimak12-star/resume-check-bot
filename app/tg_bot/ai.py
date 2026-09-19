Ок, понял — редактор кода и Save to GitHub закрыты за платой. Есть **полностью бесплатный** путь без единого локального инструмента: **создать репозиторий на GitHub через веб-интерфейс** и **скопировать код туда прямо из чата**. GitHub — бесплатно, Railway даёт **$5 стартовых кредитов** (бота хватит на ~1 месяц).

Ниже — весь код бота, готовый к вставке. Плюс пошаговая инструкция.

---

## 🎯 План (30 минут, полностью через браузер)

1. Регистрируешь GitHub (бесплатно) → создаёшь пустой репо
2. Создаёшь 9 файлов через кнопку **«Add file → Create new file»** в GitHub — просто копируешь содержимое из моих сообщений ниже
3. Подключаешь репо к Railway → добавляешь переменные → готово

---

## Шаг 1. Создай GitHub-репозиторий

1. Регистрация: https://github.com/join (email + пароль, бесплатно)
2. https://github.com/new →
   - **Repository name:** `resume-check-bot`
   - **Public** (или Private — на твой выбор)
   - ✅ Поставь галку **Add a README file** (иначе не откроется веб-редактор)
   - Нажми **Create repository**

Теперь у тебя пустой репо. В нём ты будешь создавать файлы через кнопку **Add file → + Create new file**.

---

## Шаг 2. Создай 9 файлов (копируй по одному)

Для каждого файла ниже:
1. В репо жми **Add file → Create new file**
2. В строке **Name your file...** впиши имя файла (например `bot.py`)
3. Вставь содержимое в большое поле
4. Внизу — **Commit changes** → **Commit directly to main** → **Commit changes**

Давай выведу все файлы **прямо сейчас** — каждый в отдельном блоке. Начну с самого большого — `bot.py`:
Action: view_file({"path":"/app/tg_bot/bot.py"})
Observation: [Showing lines 1-279 of 279 total] /app/tg_bot/bot.py:
1|"""Telegram-бот HR-анализатор (aiogram 3).
2|
3|Флоу:
4|1. /start -> приветствие
5|2. Пользователь шлёт резюме (текст или PDF/DOCX)
6|3. Бот просит вакансию
7|4. Пользователь шлёт текст вакансии
8|5. Groq (OpenAI-совместимый) -> разбор
9|6. Лимит: 1 бесплатный/сутки, дальше — 100 Stars за 24ч безлимита
10|"""
11|from __future__ import annotations
12|
13|import asyncio
14|import logging
15|import os
16|from typing import Optional
17|
18|from dotenv import load_dotenv
19|from aiogram import Bot, Dispatcher, F, Router
20|from aiogram.client.default import DefaultBotProperties
21|from aiogram.enums import ParseMode
22|from aiogram.filters import Command, CommandStart
23|from aiogram.fsm.context import FSMContext
24|from aiogram.fsm.state import State, StatesGroup
25|from aiogram.fsm.storage.memory import MemoryStorage
26|from aiogram.types import (
27|    LabeledPrice,
28|    InlineKeyboardButton,
29|    InlineKeyboardMarkup,
30|    Message,
31|    PreCheckoutQuery,
32|    Document,
33|)
34|
35|from ai import analyze
36|from db import DB
37|from parsers import parse_document
38|
39|load_dotenv()
40|
41|logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
42|log = logging.getLogger("hr-bot")
43|
44|BOT_TOKEN = os.environ["BOT_TOKEN"]
45|DAILY_FREE_LIMIT = int(os.environ.get("DAILY_FREE_LIMIT", "1"))
46|UNLIMITED_PRICE_STARS = int(os.environ.get("UNLIMITED_PRICE_STARS", "100"))
47|DB_PATH = os.environ.get("DB_PATH", "bot.db")
48|
49|MAX_FILE_MB = 15
50|MIN_TEXT_LEN = 50  # чтобы не принимать "ок" за резюме
51|
52|db = DB(DB_PATH)
53|router = Router()
54|
55|
56|class Flow(StatesGroup):
57|    waiting_resume = State()
58|    waiting_job = State()
59|
60|
61|# ---------- helpers ----------
62|
63|def paywall_kb() -> InlineKeyboardMarkup:
64|    return InlineKeyboardMarkup(
65|        inline_keyboard=[[
66|            InlineKeyboardButton(
67|                text=f"⭐ Купить безлимит на 24ч за {UNLIMITED_PRICE_STARS} Stars",
68|                callback_data="buy_unlimited",
69|            )
70|        ]]
71|    )
72|
73|
74|async def download_file(bot: Bot, doc: Document) -> bytes:
75|    file = await bot.get_file(doc.file_id)
76|    buf = await bot.download_file(file.file_path)
77|    return buf.read()
78|
79|
80|def looks_like_job(text: str) -> bool:
81|    """Эвристика: похоже ли на текст вакансии, чтобы не спутать с резюме."""
82|    t = text.lower()
83|    markers = ["требован", "обязанност", "мы предлагаем", "условия", "ищем", "зарплат", "опыт от", "стек", "з/п"]
84|    return sum(m in t for m in markers) >= 2
85|
86|
87|def looks_like_resume(text: str) -> bool:
88|    t = text.lower()
89|    markers = ["опыт работы", "образование", "навыки", "резюме", "родил", "github", "email", "телефон", "@"]
90|    return sum(m in t for m in markers) >= 2
91|
92|
93|# ---------- handlers ----------
94|
95|@router.message(CommandStart())
96|async def cmd_start(msg: Message, state: FSMContext) -> None:
97|    await state.clear()
98|    await state.set_state(Flow.waiting_resume)
99|    await msg.answer(
100|        "👋 Привет! Я помогу разобрать твоё резюме под конкретную вакансию.\n\n"
101|        "📎 *Пришли мне резюме* (текст или PDF/DOCX файл), потом текст вакансии — "
102|        "получишь разбор за 30 секунд.\n\n"
103|        f"Бесплатно: *{DAILY_FREE_LIMIT} разбор в сутки*."
104|    )
105|
106|
107|@router.message(Command("help"))
108|async def cmd_help(msg: Message) -> None:
109|    await msg.answer(
110|        "*Как пользоваться:*\n"
111|        "1. /start\n"
112|        "2. Пришли резюме (текст / PDF / DOCX)\n"
113|        "3. Пришли текст вакансии\n"
114|        "4. Получи разбор ✨\n\n"
115|        "/reset — начать заново"
116|    )
117|
118|
119|@router.message(Command("reset"))
120|async def cmd_reset(msg: Message, state: FSMContext) -> None:
121|    await state.clear()
122|    await state.set_state(Flow.waiting_resume)
123|    await msg.answer("Ок, начнём заново. Пришли резюме (текст или PDF/DOCX).")
124|
125|
126|# ---- resume step ----
127|
128|@router.message(Flow.waiting_resume, F.document)
129|async def resume_as_file(msg: Message, state: FSMContext, bot: Bot) -> None:
130|    doc = msg.document
131|    if doc.file_size and doc.file_size > MAX_FILE_MB * 1024 * 1024:
132|        await msg.answer(f"Файл слишком большой (>{MAX_FILE_MB} MB). Пришли текстом или уменьши.")
133|        return
134|    name = (doc.file_name or "").lower()
135|    if not (name.endswith(".pdf") or name.endswith(".docx")):
136|        await msg.answer("Поддерживаю только *PDF* или *DOCX*. Или пришли резюме обычным текстом.")
137|        return
138|    try:
139|        data = await download_file(bot, doc)
140|        text = parse_document(doc.file_name, data)
141|    except Exception as e:  # noqa: BLE001
142|        log.exception("parse fail: %s", e)
143|        await msg.answer("Не смог распарсить файл 😕 Пришли, пожалуйста, резюме *текстом*.")
144|        return
145|    if len(text) < MIN_TEXT_LEN:
146|        await msg.answer("В файле почти нет текста (возможно, скан). Пришли резюме *текстом*.")
147|        return
148|    await state.update_data(resume=text)
149|    await state.set_state(Flow.waiting_job)
150|    await msg.answer("✅ Резюме получил. Теперь пришли *текст вакансии*.")
151|
152|
153|@router.message(Flow.waiting_resume, F.text)
154|async def resume_as_text(msg: Message, state: FSMContext) -> None:
155|    text = msg.text.strip()
156|    if len(text) < MIN_TEXT_LEN:
157|        await msg.answer("Похоже, это не резюме. Пришли полный текст резюме или файл PDF/DOCX.")
158|        return
159|    if looks_like_job(text) and not looks_like_resume(text):
160|        await msg.answer("Кажется, ты прислал *вакансию*, а не резюме. Сначала пришли резюме 🙂")
161|        return
162|    await state.update_data(resume=text)
163|    await state.set_state(Flow.waiting_job)
164|    await msg.answer("✅ Резюме получил. Теперь пришли *текст вакансии*.")
165|
166|
167|@router.message(Flow.waiting_resume)
168|async def resume_other(msg: Message) -> None:
169|    await msg.answer("Жду *резюме* — текстом или файлом PDF/DOCX.")
170|
171|
172|# ---- job step ----
173|
174|@router.message(Flow.waiting_job, F.text)
175|async def job_text(msg: Message, state: FSMContext, bot: Bot) -> None:
176|    job = msg.text.strip()
177|    if len(job) < MIN_TEXT_LEN:
178|        await msg.answer("Похоже, это не текст вакансии. Пришли полное описание.")
179|        return
180|    data = await state.get_data()
181|    resume = data.get("resume")
182|    if not resume:
183|        await state.set_state(Flow.waiting_resume)
184|        await msg.answer("Сначала мне нужно *резюме*. Пришли его текстом или файлом.")
185|        return
186|
187|    # лимит
188|    unlimited = await db.is_unlimited(msg.from_user.id)
189|    if not unlimited and not await db.can_use_free(msg.from_user.id, DAILY_FREE_LIMIT):
190|        await msg.answer(
191|            "🚫 Лимит бесплатных разборов на сегодня исчерпан.\n"
192|            f"Можешь купить *безлимит на 24 часа* за {UNLIMITED_PRICE_STARS} ⭐.",
193|            reply_markup=paywall_kb(),
194|        )
195|        return
196|
197|    await msg.answer("🔎 Анализирую… (~30 сек)")
198|    try:
199|        result = await analyze(resume, job)
200|    except Exception as e:  # noqa: BLE001
201|        log.exception("AI fail: %s", e)
202|        await msg.answer("Не получилось сделать разбор 😕 Попробуй ещё раз через минуту.")
203|        return
204|
205|    if not unlimited:
206|        await db.register_use(msg.from_user.id)
207|
208|    await msg.answer(result, parse_mode=ParseMode.MARKDOWN)
209|    await msg.answer("Готово! Пришли *новое резюме*, чтобы разобрать ещё одну связку.")
210|    await state.set_state(Flow.waiting_resume)
211|
212|
213|@router.message(Flow.waiting_job, F.document)
214|async def job_as_file(msg: Message) -> None:
215|    await msg.answer("Пришли *текст вакансии* сообщением (не файлом).")
216|
217|
218|@router.message(Flow.waiting_job)
219|async def job_other(msg: Message) -> None:
220|    await msg.answer("Жду *текст вакансии*.")
221|
222|
223|# ---- fallback (нет активного состояния) ----
224|
225|@router.message(F.text)
226|async def fallback(msg: Message, state: FSMContext) -> None:
227|    current = await state.get_state()
228|    if current is None:
229|        await state.set_state(Flow.waiting_resume)
230|        await msg.answer("Начнём! Пришли резюме (текст или PDF/DOCX).")
231|
232|
233|# ---- Telegram Stars payments ----
234|
235|@router.callback_query(F.data == "buy_unlimited")
236|async def buy_unlimited(cb, bot: Bot) -> None:  # type: ignore[no-untyped-def]
237|    await cb.answer()
238|    await bot.send_invoice(
239|        chat_id=cb.from_user.id,
240|        title="Безлимит на 24 часа",
241|        description="Неограниченное количество разборов резюме под вакансии в течение 24 часов.",
242|        payload=f"unlimited_24h:{cb.from_user.id}",
243|        provider_token="",  # для Stars — пустая строка
244|        currency="XTR",
245|        prices=[LabeledPrice(label="Безлимит 24ч", amount=UNLIMITED_PRICE_STARS)],
246|    )
247|
248|
249|@router.pre_checkout_query()
250|async def pre_checkout(q: PreCheckoutQuery, bot: Bot) -> None:
251|    await bot.answer_pre_checkout_query(q.id, ok=True)
252|
253|
254|@router.message(F.successful_payment)
255|async def on_paid(msg: Message) -> None:
256|    sp = msg.successful_payment
257|    user_id = msg.from_user.id
258|    until = await db.grant_unlimited(user_id, hours=24)
259|    await db.save_payment(sp.telegram_payment_charge_id, user_id, sp.total_amount)
260|    await msg.answer(
261|        f"✅ Оплата получена! Безлимит активен до *{until.strftime('%Y-%m-%d %H:%M UTC')}*.\n"
262|        "Присылай резюме — разберём!"
263|    )
264|
265|
266|# ---------- entrypoint ----------
267|
268|async def main() -> None:
269|    await db.init()
270|    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
271|    dp = Dispatcher(storage=MemoryStorage())
272|    dp.include_router(router)
273|    log.info("Bot started")
274|    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
275|
276|
277|if __name__ == "__main__":
278|    asyncio.run(main())
279|
[End of file]

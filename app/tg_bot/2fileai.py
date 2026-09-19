"""Клиент к Groq (OpenAI-совместимый)."""
from __future__ import annotations

import os
from openai import AsyncOpenAI

ANALYSIS_PROMPT = """Ты — опытный HR-рекрутер и карьерный консультант.
Резюме: {resume}
Вакансия: {job}
Отвечай СТРОГО в таком формате:
📊 СКОРИНГ: [число]%
Причина: [1 предложение]
⚠️ НЕСОВПАДЕНИЯ:
1. ...
2. ...
3. ...
✍️ ПЕРЕФОРМУЛИРОВКИ:
Было: "..." → Стало: "..."
(2-3 примера с цифрами/результатами где возможно)
🚩 ГЛАВНЫЙ РИСК: [1 предложение]
Пиши по делу, без воды. Отвечай на языке резюме."""


def _client() -> AsyncOpenAI:
    api_key = os.environ["GROQ_API_KEY"]
    base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


async def analyze(resume_text: str, job_text: str) -> str:
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    prompt = ANALYSIS_PROMPT.format(resume=resume_text.strip(), job=job_text.strip())
    resp = await _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Ты — точный и лаконичный HR-рекрутер. Отвечай строго в заданном формате, без лишних слов."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=1500,
    )
    return (resp.choices[0].message.content or "").strip()

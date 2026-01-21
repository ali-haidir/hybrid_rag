# query_service/app/services/llm.py
import os
from openai import OpenAI


def get_openai_client() -> OpenAI:
    base_url = os.getenv("BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY", "anything")

    if not base_url:
        raise RuntimeError("BASE_URL is not set")

    return OpenAI(api_key=api_key, base_url=base_url)


def generate_answer(question: str, context: str, model_name: str | None = None) -> str:
    client = get_openai_client()

    model = model_name or os.getenv("MODEL_CHAT")
    if not model:
        raise RuntimeError("MODEL_CHAT is not set and model_name not provided")

    system = (
        "You are a helpful assistant. Answer using ONLY the provided context. "
        "If the context is insufficient, say you don't know."
    )

    user = f"""CONTEXT:
{context}

QUESTION:
{question}

INSTRUCTIONS:
- Use the context only
- Be concise
- If not found in context, say: "I don't know based on the provided document(s)."
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )

    return resp.choices[0].message.content or ""

import os
import requests
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("BASE_URL"),  # <--- The URL is used here
)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Call embedding model and return vectors.
    """

    response = client.embeddings.create(
        model=os.getenv("MODEL_EMBED"),
        input=texts,
    )
    return [item.embedding for item in response.data]

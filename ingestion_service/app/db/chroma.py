import chromadb
from chromadb.config import Settings
import os

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "/chroma_data")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "documents")


def get_chroma_client():
    return chromadb.Client(
        Settings(
            persist_directory=CHROMA_PERSIST_DIR,
            anonymized_telemetry=False,
            is_persistent=True,  # 🔴 REQUIRED
        )
    )


def get_collection():
    client = get_chroma_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return client, collection

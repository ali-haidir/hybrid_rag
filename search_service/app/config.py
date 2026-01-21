from pydantic import BaseModel
import os


class OpenSearchSettings(BaseModel):
    host: str
    port: int
    scheme: str
    username: str
    password: str
    index_name: str

    @property
    def use_ssl(self) -> bool:
        return self.scheme.lower() == "https"


def get_opensearch_settings() -> OpenSearchSettings:
    return OpenSearchSettings(
        host=os.getenv("OPENSEARCH_HOST", "opensearch"),
        port=int(os.getenv("OPENSEARCH_PORT", "9200")),
        scheme=os.getenv("OPENSEARCH_SCHEME", "http"),
        username=os.getenv("OPENSEARCH_USER", "admin"),
        password=os.getenv("OPENSEARCH_PASSWORD", "Admin123!"),
        index_name=os.getenv("OPENSEARCH_INDEX", "docs_bm25"),
    )

from opensearchpy import OpenSearch, exceptions as os_exceptions
from .config import get_opensearch_settings


def get_os_client() -> OpenSearch:
    """
    Shared OpenSearch client constructor.
    Used by /health and by ensure_index.
    """
    settings = get_opensearch_settings()

    client = OpenSearch(
        hosts=[{"host": settings.host, "port": settings.port}],
        http_auth=(settings.username, settings.password) if settings.username else None,
        scheme=settings.scheme,
        use_ssl=settings.use_ssl,
        verify_certs=False,  # dev only; turn on in prod with proper certs
    )
    return client


def ensure_index():
    """
    Create the BM25 index if it does not exist yet.
    """
    settings = get_opensearch_settings()
    client = get_os_client()
    index_name = settings.index_name

    exists = client.indices.exists(index=index_name)
    if exists:
        return  # already created

    body = {
        "settings": {
            # default similarity is BM25; you can tweak parameters later
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "integer"},
                "source": {"type": "keyword"},
                "page": {"type": "integer"},
                "text": {
                    "type": "text",
                    # default analyzer is fine; can customise later
                },
                "tags": {"type": "keyword"},
            }
        },
    }

    try:
        client.indices.create(index=index_name, body=body)
        print(f"[search-service] Created index {index_name!r}")
    except os_exceptions.RequestError as e:
        # If there is a race condition & another container created it,
        # ignore 'resource_already_exists_exception'
        if "resource_already_exists_exception" in str(e):
            print(f"[search-service] Index {index_name!r} already exists (race)")
        else:
            raise

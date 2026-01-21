from opensearchpy import OpenSearch
import os


OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "opensearch")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_SCHEME = os.getenv("OPENSEARCH_SCHEME", "http")


# For now we assume security disabled (OPENSEARCH_SECURITY_ENABLED=false)
# If you enable auth later, we’ll plug in user/pass here.
def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_auth=None,
        use_ssl=(OPENSEARCH_SCHEME == "https"),
        verify_certs=False,
        ssl_show_warn=False,
    )

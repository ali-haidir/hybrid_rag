from typing import List


def fixed_chunk_text(
    text: str, *, chunk_size: int = 500, overlap: int = 50
) -> List[str]:
    """
    Split text into fixed-size overlapping chunks.
    Tokenization is whitespace-based.
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    tokens = text.split()
    chunks = []

    start = 0
    total_tokens = len(tokens)

    while start < total_tokens:
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunks.append(" ".join(chunk_tokens))

        start = end - overlap

        if start < 0:
            start = 0

    return chunks

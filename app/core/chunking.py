import tiktoken
from app.config.settings import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS

# tiktoken has no Claude tokenizer; cl100k_base is a close-enough approximation for chunk sizing
_enconding = tiktoken.get_encoding("cl100k_base")

def chunk_text(text: str) -> list[str]:
    tokens = _enconding.encode(text)
    if not tokens:
        return []
 
    start = 0
    chunks = []
    step = CHUNK_SIZE_TOKENS - CHUNK_OVERLAP_TOKENS 
    while start < len(tokens):
        window = tokens[start: start + CHUNK_SIZE_TOKENS]  
        chunks.append(_enconding.decode(window))
        start += step
    return chunks
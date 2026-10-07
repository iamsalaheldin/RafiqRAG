from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from openai import OpenAI
from app.config.settings import CHAT_MODEL, OPENAI_API_KEY, REQUEST_TIMEOUT_SECONDS


client = OpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)

# The AI proxy serves no embedding models, so embeddings run locally (all-MiniLM-L6-v2 via ONNX)
_embedder = DefaultEmbeddingFunction()


def chat_completion(messages:list[dict], temperature: float = 0.2, max_tokens: int = 200) -> dict:
    """
    This function for calling the openai model.

    Args:
        messages: The input messages to the client (OpenAI model).
        temperature: This hyperparameter controls the creativity of the model and diversity of response.
        max_tokens: The max output tokens of the model.
    
    Returns:
    A dictionary that contains th answer, finish_reason, usage.
    """
    completion = client.chat.completions.create(
        model = CHAT_MODEL, 
        messages=messages, 
        temperature=temperature, 
        max_tokens=max_tokens
    )

    choice = completion.choices[0]
    return {
        "answer":choice.message.content or "",
        "finish_reason": choice.finish_reason,
        "usage":
        {
            "prompt_tokens":completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens
        }
    }

def embed_text(text: str) -> list[float]:
    return embed_batch([text])[0]

def embed_batch(texts: list[str]) -> list[list[float]]:
    return [embedding.tolist() for embedding in _embedder(texts)]
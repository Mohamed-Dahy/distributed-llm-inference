import time
import os

USE_REAL_LLM = os.getenv("USE_REAL_LLM", "false").lower() == "true"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

def run_llm(query: str, context: str) -> str:
    if not USE_REAL_LLM:
        return _stub_llm(query, context)
    try:
        return _ollama_llm(query, context)
    except Exception as e:
        print(f"[LLM] Real LLM failed: {e}, falling back to stub")
        return _stub_llm(query, context)

def _stub_llm(query: str, context: str) -> str:
    time.sleep(0.2)
    return f"LLM Answer to '{query}' using [{context}]"

def _ollama_llm(query: str, context: str) -> str:
    import requests
    prompt = (
        f"You are a helpful assistant. Use the context below to answer the question concisely.\n\n"
        f"Context: {context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
        timeout=30
    )
    response.raise_for_status()
    return response.json()["response"].strip()

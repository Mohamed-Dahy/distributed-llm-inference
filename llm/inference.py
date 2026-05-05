import time
import os
import httpx

USE_REAL_LLM = os.getenv("USE_REAL_LLM", "false").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

def run_llm(query: str, context: str) -> str:
    if not USE_REAL_LLM:
        return _stub_llm(query, context)
    
    # Try Groq first if API key is available
    if GROQ_API_KEY:
        try:
            return _groq_llm(query, context)
        except Exception as e:
            print(f"[LLM] Groq failed: {e}, falling back to Ollama")
    
    # Fall back to Ollama
    try:
        return _ollama_llm(query, context)
    except Exception as e:
        print(f"[LLM] Ollama failed: {e}, falling back to stub")
        return _stub_llm(query, context)

def _stub_llm(query: str, context: str) -> str:
    time.sleep(0.2)
    return f"LLM Answer to '{query}' using [{context}]"

def _groq_llm(query: str, context: str) -> str:
    """Call Groq API for LLM inference."""
    prompt = (
        f"Use the context below to answer the question concisely in 2-3 sentences.\n\n"
        f"Context: {context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "mixtral-8x7b-32768",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 150,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

def _ollama_llm(query: str, context: str) -> str:
    prompt = (
        f"Use the context below to answer the question concisely in 2-3 sentences.\n\n"
        f"Context: {context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )
    response = httpx.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 150,
            },
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["response"].strip()

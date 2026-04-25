import time
import os

USE_REAL_LLM = os.getenv("USE_REAL_LLM", "false").lower() == "true"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")

def run_llm(query: str, context: str) -> str:
    if not USE_REAL_LLM:
        return _stub_llm(query, context)
    try:
        return _groq_llm(query, context)
    except Exception as e:
        print(f"[LLM] Groq API failed: {e}, falling back to stub")
        return _stub_llm(query, context)

def _stub_llm(query: str, context: str) -> str:
    time.sleep(0.2)
    return f"LLM Answer to '{query}' using [{context}]"

def _groq_llm(query: str, context: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    prompt = (
        f"Use the context below to answer the question concisely in 2-3 sentences.\n\n"
        f"Context: {context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

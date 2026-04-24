import os
import pypdf

def chunk_text(text: str, chunk_size: int = 3) -> list:
    sentences = text.split(".")
    sentences = [s.strip() for s in sentences]
    sentences = [s for s in sentences if len(s) >= 20]

    chunks = []
    for i in range(0, len(sentences), chunk_size):
        group = sentences[i:i + chunk_size]
        chunks.append(". ".join(group) + ".")
    return chunks

def load_documents() -> list:
    docs_path = os.path.join(os.path.dirname(__file__), "Data")

    if not os.path.exists(docs_path):
        print(f"[Ingest] WARNING — rag/Data/ folder not found.")
        return []

    pdf_files = [f for f in os.listdir(docs_path) if f.endswith(".pdf")]

    if not pdf_files:
        print("[Ingest] WARNING — No PDFs found in rag/Data/.")
        return []

    all_chunks = []
    for filename in pdf_files:
        filepath = os.path.join(docs_path, filename)
        try:
            reader = pypdf.PdfReader(filepath)
            full_text = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text + " "

            chunks = chunk_text(full_text, chunk_size=6)
            for i, chunk in enumerate(chunks):
                all_chunks.append({
                    "id": f"{filename}_chunk_{i}",
                    "text": chunk,
                    "source": filename
                })
            print(f"[Ingest] {filename} — {len(chunks)} chunks extracted")
        except Exception as e:
            print(f"[Ingest] ERROR reading {filename}: {e}")

    return all_chunks

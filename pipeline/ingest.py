"""
pipeline/ingest.py
------------------
Converts master_inventory.csv into vector embeddings
and stores them in a local ChromaDB collection.

Each inventory record → natural language text → local sentence-transformer → ChromaDB
No OpenAI API required for embeddings.
Run once; re-runs automatically if CSV row count changes.
"""

import pandas as pd
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


COLLECTION_NAME = "inventory_assets"
EMBED_MODEL     = "all-MiniLM-L6-v2"   # 384-dim, fast, runs fully offline
BATCH_SIZE      = 100


# ─── Convert one row → human-readable text ───────────────────────────────────
def row_to_text(row: dict) -> str:
    field_labels = {
        "current_user":      "Current user",
        "old_user":          "Previous user",
        "employee_code":     "Employee code",
        "designation":       "Designation",
        "type":              "Device type",
        "make":              "Make",
        "model":             "Model",
        "serial_no":         "Serial number",
        "host_name":         "Host name",
        "ram":               "RAM",
        "os":                "Operating system",
        "os_build":          "OS build",
        "storage":           "Storage",
        "po_number":         "PO number",
        "location":          "Location",
        "source_sheet":      "Office",
        "agreement_verified":"Agreement status",
        "agreement_doc":     "Agreement document",
        "lifecycle":         "Lifecycle",
    }
    parts = []
    for field, label in field_labels.items():
        val = str(row.get(field, "")).strip()
        if val and val.lower() not in ("na", "nan", "none", ""):
            parts.append(f"{label}: {val}")
    return " | ".join(parts)


# ─── Clean metadata for ChromaDB ─────────────────────────────────────────────
def clean_metadata(row: dict) -> dict:
    return {k: str(v).strip() if v is not None else "" for k, v in row.items()}


# ─── Main ingestion function ──────────────────────────────────────────────────
def ingest(
    csv_path:    str,
    chroma_path: str  = "./chroma_db",
    force:       bool = False,
) -> chromadb.Collection:
    """
    Load CSV → embed records locally → store in ChromaDB.
    Uses sentence-transformers (all-MiniLM-L6-v2) — no API key required.

    Args:
        csv_path:    Path to master_inventory.csv
        chroma_path: Directory for ChromaDB persistence
        force:       Re-ingest even if record count matches

    Returns:
        ChromaDB collection ready for querying
    """
    print(f"\n[Ingest] Loading: {csv_path}")
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    ef            = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    chroma_client = chromadb.PersistentClient(path=chroma_path)

    # ── Check if already ingested ──
    try:
        collection     = chroma_client.get_collection(COLLECTION_NAME, embedding_function=ef)
        existing_count = collection.count()
        if not force and existing_count == len(df):
            print(f"[Ingest] Already ingested ({existing_count} records). Skipping.")
            return collection
        print(f"[Ingest] Record count changed ({existing_count} → {len(df)}). Re-ingesting.")
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        print("[Ingest] No existing collection found. Starting fresh.")

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # ── Prepare data ──
    records   = df.to_dict(orient="records")
    texts     = [row_to_text(r) for r in records]
    ids       = [f"rec_{i}" for i in range(len(records))]
    metadatas = [clean_metadata(r) for r in records]

    # ── Embed in batches (ChromaDB calls the local EF automatically) ──
    total = len(texts)
    print(f"[Ingest] Embedding {total} records locally (model: {EMBED_MODEL})...")

    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        collection.add(
            documents=texts[start:end],
            ids=ids[start:end],
            metadatas=metadatas[start:end],
        )
        print(f"[Ingest]   {end}/{total} done")

    print(f"[Ingest] Complete. {total} records stored in ChromaDB.\n")
    return collection

"""
pipeline/retriever.py
---------------------
Hybrid retrieval layer:

  1. SEMANTIC   — vector similarity search via ChromaDB (local sentence-transformers)
  2. METADATA   — exact field filtering via ChromaDB where-clause
  3. PANDAS     — full-scan filtering on the original DataFrame

Uses all-MiniLM-L6-v2 locally — no OpenAI API needed for retrieval.
"""

import re
import pandas as pd
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


EMBED_MODEL     = "all-MiniLM-L6-v2"
COLLECTION_NAME = "inventory_assets"


# ─── Mode 1: Semantic search ──────────────────────────────────────────────────
def semantic_search(
    query:      str,
    collection: chromadb.Collection,
    n_results:  int = 15,
    where:      dict | None = None,
) -> list[dict]:
    """
    ChromaDB embeds the query text automatically using the collection's EF.

    Args:
        where: Optional ChromaDB metadata filter for hybrid search.
               e.g. {"type": {"$eq": "Laptop"}}
    Returns:
        List of metadata dicts sorted by similarity.
    """
    kwargs = {
        "query_texts": [query],
        "n_results":   min(n_results, collection.count()),
        "include":     ["metadatas", "documents", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    records = []
    for meta, doc, dist in zip(
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        record                = dict(meta)
        record["_similarity"] = round(1 - dist, 4)
        record["_text"]       = doc
        records.append(record)

    return records


# ─── Mode 2: Metadata exact filter ───────────────────────────────────────────
def metadata_filter_search(
    collection: chromadb.Collection,
    where:      dict,
    n_results:  int = 10,
) -> list[dict]:
    results = collection.get(
        where=where,
        limit=n_results,
        include=["metadatas", "documents"],
    )
    records = []
    for meta, doc in zip(results["metadatas"], results["documents"]):
        record         = dict(meta)
        record["_text"] = doc
        records.append(record)
    return records


# ─── Mode 3: Pandas filter (aggregate / list queries) ────────────────────────

_SAFE_BUILTINS = {
    "__builtins__": {
        "len": len, "int": int, "float": float, "str": str,
        "list": list, "dict": dict, "range": range,
        "sorted": sorted, "sum": sum, "min": min, "max": max,
        "round": round, "bool": bool, "abs": abs,
        "enumerate": enumerate, "zip": zip,
    }
}

_FORBIDDEN = [
    "import ", "__import__", "exec(", "eval(", "open(",
    "os.", "sys.", "subprocess", "shutil", "globals", "locals",
]


def pandas_filter(df: pd.DataFrame, pandas_code: str) -> pd.DataFrame | pd.Series | str:
    code = pandas_code.strip().strip("`")
    if code.lower().startswith("python"):
        code = code[6:].strip()

    for token in _FORBIDDEN:
        if token in code:
            raise ValueError(f"Unsafe operation blocked: `{token}`")

    local_vars = {"df": df.copy(), "pd": pd}
    try:
        exec(code, _SAFE_BUILTINS, local_vars)  # noqa: S102
    except Exception as exc:
        raise RuntimeError(f"Pandas execution failed: {exc}") from exc

    result = local_vars.get("result")
    if result is None:
        raise RuntimeError("Code did not assign anything to `result`.")
    return result


# ─── SemanticRetriever class (used by LangGraph sql_agent) ───────────────────

class SemanticRetriever:
    """
    Object-oriented wrapper around local ChromaDB semantic search.
    No OpenAI API key required — embeddings run on-device.
    """

    def __init__(self, chroma_path: str = "./chroma_db"):
        ef                 = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.collection    = self.chroma_client.get_collection(
            COLLECTION_NAME, embedding_function=ef
        )

    def search(self, query: str, n_results: int = 12) -> list[dict]:
        return semantic_search(
            query=query,
            collection=self.collection,
            n_results=n_results,
        )

    def search_to_df(self, query: str, n_results: int = 12) -> pd.DataFrame:
        records = self.search(query, n_results)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        return df.drop(columns=["_similarity", "_text"], errors="ignore")

    @property
    def count(self) -> int:
        return self.collection.count()


# ─── Build exact-match where clause from query ────────────────────────────────
def extract_exact_filter(query: str) -> dict | None:
    q_upper = query.upper()

    m = re.search(r"\b(NTZ|C|NIS)\d+\b", q_upper)
    if m:
        return {"employee_code": {"$eq": m.group(0)}}

    m = re.search(r"\b(NTZ|SWJ|NA)-(?:LAP|CPU)-\d+\b", q_upper)
    if m:
        return {"host_name": {"$eq": m.group(0)}}

    tokens   = re.findall(r"\b[A-Z0-9]{6,}\b", q_upper)
    non_words = [t for t in tokens if not t.isalpha()]
    if non_words:
        return {"serial_no": {"$eq": non_words[0]}}

    return None

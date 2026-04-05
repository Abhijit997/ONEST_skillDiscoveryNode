"""
API for embedding a worker from the SQLite worker table into ChromaDB emb_worker collection.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.services.emb_worker_service import insert_worker_embedding_from_sqlite, collection
from app.api.schemas import EmbWorkerOut, EmbWorkerListResponse, EmbWorkerMetadata

router = APIRouter(prefix="/emb_workers", tags=["emb_worker"])

@router.post("/embed/{worker_id}", summary="Embed a worker from SQLite into ChromaDB", response_model=EmbWorkerOut)
def embed_worker(worker_id: str, db: Session = Depends(get_db)):
    result = insert_worker_embedding_from_sqlite(db, worker_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    # Build response using schema
    text = result.get("text", "")
    metadata = result.get("metadata", {})
    return EmbWorkerOut(
        worker_id=result["worker_id"],
        text=text,
        metadata=EmbWorkerMetadata(**metadata),
    )

@router.get("", summary="List/search emb_workers", response_model=EmbWorkerListResponse)
def list_emb_workers(
    query: Optional[str] = Query(None, description="Search by text (fulltext/semantic)"),
    n_results: int = Query(20, ge=1, le=100, description="Number of results to return"),
):
    """
    List or search emb_worker embeddings in ChromaDB.
    If query is provided, does a semantic search; otherwise, returns all (up to n_results).
    """
    results = []
    if query:
        q = collection.query(query_texts=[query], n_results=n_results)
        for wid, doc, meta, dist in zip(
            q["ids"][0], q["documents"][0], q["metadatas"][0], q["distances"][0]
        ):
            results.append(EmbWorkerOut(
                worker_id=wid,
                text=doc,
                metadata=EmbWorkerMetadata(**meta),
                distance=dist,
            ))
    else:
        all_data = collection.get()
        for wid, doc, meta in zip(
            all_data["ids"], all_data["documents"], all_data["metadatas"]
        ):
            results.append(EmbWorkerOut(
                worker_id=wid,
                text=doc,
                metadata=EmbWorkerMetadata(**meta),
            ))
        results = results[:n_results]
    return EmbWorkerListResponse(results=results)

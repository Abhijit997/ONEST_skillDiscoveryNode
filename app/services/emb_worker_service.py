"""
Service for embedding workers from the SQLite worker table into ChromaDB.
"""
from typing import Any
from sqlalchemy.orm import Session
from app.db.models import Worker
import chromadb
from chromadb.utils import embedding_functions

chroma_client = chromadb.Client()
embedding_fn = embedding_functions.DefaultEmbeddingFunction()
EMB_WORKER_COLLECTION = "emb_worker"
collection = chroma_client.get_or_create_collection(
    EMB_WORKER_COLLECTION, embedding_function=embedding_fn
)

def build_worker_embedding_text(worker: Worker) -> str:
    # Concatenate all columns as string for embedding
    fields = [
        worker.worker_id,
        worker.name,
        str(worker.dob) if worker.dob else "",
        worker.gender or "",
        worker.aadhar_hash,
        worker.district,
        worker.taluk or "",
        worker.city_village or "",
        worker.state_name or "",
        worker.state_code or "",
        worker.city_code or "",
        worker.area_code or "",
        worker.door or "",
        worker.building or "",
        worker.street or "",
        worker.locality or "",
        worker.ward or "",
        str(worker.latitude) if worker.latitude else "",
        str(worker.longitude) if worker.longitude else "",
        worker.skill_category.value if hasattr(worker.skill_category, 'value') else str(worker.skill_category),
        str(worker.iti_nsqf_level) if worker.iti_nsqf_level else "",
        worker.highest_qualification or "",
        str(worker.languages) if worker.languages else "",
        str(worker.skills_detailed) if worker.skills_detailed else "",
        worker.availability_status.value if hasattr(worker.availability_status, 'value') else str(worker.availability_status),
        worker.preferred_shift.value if hasattr(worker.preferred_shift, 'value') else str(worker.preferred_shift),
        worker.fulfillment_type.value if hasattr(worker.fulfillment_type, 'value') else str(worker.fulfillment_type),
        str(worker.verification_status) if worker.verification_status else "",
        worker.phone,
        worker.email or "",
        str(worker.experience_years) if worker.experience_years else "",
        worker.source_channel.value if hasattr(worker.source_channel, 'value') else str(worker.source_channel),
        worker.status.value if hasattr(worker.status, 'value') else str(worker.status),
        str(worker.created_ts),
        str(worker.updated_ts),
    ]
    return " | ".join([str(f) for f in fields if f])

def build_worker_metadata(worker: Worker) -> dict[str, Any]:
    return {
        "name": worker.name,
        "gender": worker.gender,
        "district": worker.district,
        "city_village": worker.city_village,
        "state_code": worker.state_code,
        "area_code": worker.area_code,
        "skill_category": worker.skill_category.value if hasattr(worker.skill_category, 'value') else str(worker.skill_category),
        "highest_qualification": worker.highest_qualification,
        "availability_status": worker.availability_status.value if hasattr(worker.availability_status, 'value') else str(worker.availability_status),
        "preferred_shift": worker.preferred_shift.value if hasattr(worker.preferred_shift, 'value') else str(worker.preferred_shift),
        "fulfillment_type": worker.fulfillment_type.value if hasattr(worker.fulfillment_type, 'value') else str(worker.fulfillment_type),
        "experience_years": worker.experience_years,
    }

def insert_worker_embedding_from_sqlite(db: Session, worker_id: str) -> dict:
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        return {"error": "Worker not found"}
    text = build_worker_embedding_text(worker)
    metadata = build_worker_metadata(worker)
    collection.upsert(ids=[worker.worker_id], documents=[text], metadatas=[metadata])
    return {"worker_id": worker.worker_id, "status": "embedded"}

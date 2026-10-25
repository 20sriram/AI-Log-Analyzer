from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_engine.hdfs_detector import predict_hdfs_block

router = APIRouter(prefix="/hdfs", tags=["HDFS"])


class HDFSPredictionRequest(BaseModel):
    features: dict[str, Any]

    class Config:
        extra = "forbid"


@router.post("/predict")
def predict_hdfs(request: HDFSPredictionRequest) -> dict:
    """Predict whether one HDFS event-count pattern is normal or anomalous."""
    try:
        return predict_hdfs_block(request.features)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

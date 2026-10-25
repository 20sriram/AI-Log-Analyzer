from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from . import models
from .routes.hdfs import router as hdfs_router
from .routes.logs import router as logs_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Log Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(logs_router)
app.include_router(hdfs_router)

@app.get("/")
def home():
    return {"message": "AI Log Analyzer Backend Running"}
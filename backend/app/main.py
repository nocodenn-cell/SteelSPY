"""
API de auditoria: NF-e × especificação (aço/concreto).
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth_pwa, conferencia

app = FastAPI(title="stellSPY Auditoria NF-e", version="0.1.0")

_origins = [o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS") or "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

app.include_router(auth_pwa.router)
app.include_router(conferencia.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

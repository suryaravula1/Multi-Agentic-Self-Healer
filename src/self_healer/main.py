from __future__ import annotations

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException

from self_healer import __version__
from self_healer.config import settings
from self_healer.models.schemas import HealRequest, HealResponse
from self_healer.orchestrator import HealingPipeline

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

app = FastAPI(
    title="Multi-Agent Self Healer",
    description="LLM reasoning agents for Linux log diagnosis and sandboxed recovery",
    version=__version__,
)

pipeline = HealingPipeline()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "llm_configured": settings.llm_configured,
        "auto_execute": settings.auto_execute,
        "sandbox_image": settings.sandbox_image,
    }


@app.post("/heal", response_model=HealResponse)
def heal(request: HealRequest) -> HealResponse:
    if not request.logs.strip():
        raise HTTPException(status_code=400, detail="logs cannot be empty")
    return pipeline.run(request)


@app.post("/analyze", response_model=HealResponse)
def analyze(request: HealRequest) -> HealResponse:
    """Parse, diagnose, and plan without executing recovery commands."""
    request.auto_execute = False
    return pipeline.run(request)


def run() -> None:
    uvicorn.run(
        "self_healer.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()

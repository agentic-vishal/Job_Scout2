import asyncio
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import scout


ROOT = Path(__file__).resolve().parents[1]
TRACKER = Path(tempfile.gettempdir()) / "job-scout-applications.json"
app = FastAPI(title="Scout API")


class ScoutRequest(BaseModel):
    job: str = Field(min_length=1, max_length=20_000)


@app.get("/", include_in_schema=False)
async def homepage():
    return FileResponse(ROOT / "index.html", media_type="text/html")


@app.post("/")
@app.post("/api", include_in_schema=False)
async def scout_role(
    payload: ScoutRequest,
    x_scout_password: str | None = Header(default=None),
):
    access_password = os.getenv("SCOUT_ACCESS_PASSWORD", "")
    if not access_password:
        raise HTTPException(status_code=503, detail="SCOUT_ACCESS_PASSWORD is not configured.")
    if not x_scout_password or not secrets.compare_digest(x_scout_password, access_password):
        raise HTTPException(status_code=401, detail="Incorrect access password.")
    if not payload.job.strip():
        raise HTTPException(status_code=422, detail="Paste a job description or URL first.")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured.")

    if not TRACKER.exists():
        shutil.copyfile(ROOT / "applications.json", TRACKER)
    os.environ["SCOUT_TRACKER_PATH"] = str(TRACKER)

    try:
        report = await scout(payload.job.strip(), trace=None)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scout failed: {exc}") from exc

    applications = json.loads(TRACKER.read_text(encoding="utf-8"))
    return {"report": report, "applications": applications}
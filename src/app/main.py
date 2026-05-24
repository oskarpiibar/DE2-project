"""
Star Predictor — FastAPI Backend
Loads the best model from the local models/ directory.
The model file is placed there by a git hook on the dev server.
"""

import os
import socket
import glob
import joblib
import numpy as np
import pandas as pd
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Model directory — git hook copies best_model.pkl here before deploying
# ---------------------------------------------------------------------------
MODELS_DIR = os.getenv("MODELS_DIR", "./models")
MODEL_FILE  = os.path.join(MODELS_DIR, "best_model.pkl")

# ---------------------------------------------------------------------------
# Feature order must match training data (features.csv column order)
# ---------------------------------------------------------------------------
FEATURE_COLUMNS = [
    "forks", "open_issues", "size", "has_wiki", "has_pages", "archived",
    "commits", "contributors", "releases", "open_pull_requests",
    "subscribers_count", "network_count", "repo_age_days", "commits_per_day",
    "fork_ratio", "has_description", "has_homepage", "has_license",
    "topics_count",
    "lang_C", "lang_Csharp", "lang_Cpp", "lang_CSS", "lang_Go", "lang_HTML",
    "lang_Java", "lang_JavaScript", "lang_Jupyter_Notebook", "lang_Kotlin",
    "lang_Other", "lang_Python", "lang_Ruby", "lang_Rust", "lang_Shell",
    "lang_Swift", "lang_TypeScript",
]

ALL_LANG_COLS = [c for c in FEATURE_COLUMNS if c.startswith("lang_")]

# ---------------------------------------------------------------------------
# Global model store (loaded once at startup)
# ---------------------------------------------------------------------------
model_store: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model from disk on startup."""
    if not os.path.exists(MODEL_FILE):
        print(f"[startup] WARNING: No model found at {MODEL_FILE}. Predictions will fail until a model is deployed.")
    else:
        model_store["model"] = joblib.load(MODEL_FILE)
        model_store["model_file"] = MODEL_FILE
        print(f"[startup] Loaded model from {MODEL_FILE}")
    yield
    model_store.clear()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="GitHub Star Predictor",
    description="Predict the star count of GitHub repositories using ML.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
LANG_TO_COL = {
    "C++":              "lang_Cpp",
    "C#":               "lang_Csharp",
    "Jupyter Notebook": "lang_Jupyter_Notebook",
}


class RepoInput(BaseModel):
    repo_name:           str = Field(...,  description="Display name (not used for prediction)")
    forks:               int = Field(...,  ge=0)
    open_issues:         int = Field(...,  ge=0)
    size:                int = Field(...,  ge=0,  description="Repo size in KB")
    has_wiki:            int = Field(0,    ge=0, le=1)
    has_pages:           int = Field(0,    ge=0, le=1)
    archived:            int = Field(0,    ge=0, le=1)
    commits:             int = Field(...,  ge=0)
    contributors:        int = Field(...,  ge=1)
    releases:            int = Field(0,    ge=0)
    open_pull_requests:  int = Field(0,    ge=0)
    subscribers_count:   int = Field(...,  ge=0)
    network_count:       int = Field(...,  ge=0)
    repo_age_days:       int = Field(...,  ge=1)
    has_description:     int = Field(1,    ge=0, le=1)
    has_homepage:        int = Field(0,    ge=0, le=1)
    has_license:         int = Field(1,    ge=0, le=1)
    topics_count:        int = Field(0,    ge=0)
    language:            str = Field("Other")


class RepoPrediction(BaseModel):
    repo_name:       str
    predicted_stars: int
    log_stars:       float


class RankingResponse(BaseModel):
    ranked:     list[RepoPrediction]
    model_file: str


# ---------------------------------------------------------------------------
# Feature engineering (mirrors preprocess.py logic)
# ---------------------------------------------------------------------------
def build_feature_row(repo: RepoInput) -> pd.DataFrame:
    row: dict = {col: 0 for col in FEATURE_COLUMNS}

    for col in FEATURE_COLUMNS:
        if hasattr(repo, col):
            row[col] = getattr(repo, col)

    row["commits_per_day"] = repo.commits / max(repo.repo_age_days, 1)
    row["fork_ratio"]      = repo.forks / (repo.subscribers_count + 1)

    lang     = repo.language
    col_name = LANG_TO_COL.get(lang, f"lang_{lang.replace(' ', '_')}")
    if col_name in ALL_LANG_COLS:
        row[col_name] = 1
    else:
        row["lang_Other"] = 1

    return pd.DataFrame([row])[FEATURE_COLUMNS]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {
        "status":       "ok",
        "model_loaded": "model" in model_store,
        "model_file":   model_store.get("model_file", "not loaded"),
        "server":       socket.gethostname(),
    }


@app.post("/predict", response_model=RankingResponse)
async def predict(repos: list[RepoInput]):
    if "model" not in model_store:
        raise HTTPException(503, "No model loaded. Deploy a model to the models/ directory first.")
    if not repos:
        raise HTTPException(400, "Provide at least one repository.")

    model   = model_store["model"]
    results = []

    for repo in repos:
        X        = build_feature_row(repo)
        log_pred = float(model.predict(X)[0])
        stars    = int(np.expm1(log_pred))
        results.append(RepoPrediction(
            repo_name=repo.repo_name,
            predicted_stars=stars,
            log_stars=round(log_pred, 4),
        ))

    ranked = sorted(results, key=lambda r: r.predicted_stars, reverse=True)
    return RankingResponse(ranked=ranked, model_file=model_store.get("model_file", ""))


@app.get("/predict/demo", response_model=RankingResponse)
async def predict_demo():
    demo_repos = [
        RepoInput(repo_name="torvalds/linux",        forks=47463, open_issues=479,  size=1201,   commits=611,   contributors=140,  subscribers_count=6677,  network_count=47463, repo_age_days=2925, language="C"),
        RepoInput(repo_name="facebook/react",        forks=44515, open_issues=185,  size=572816, commits=41568, contributors=6450, subscribers_count=8550,  network_count=44515, repo_age_days=4157, language="JavaScript",  has_license=1, topics_count=15),
        RepoInput(repo_name="tensorflow/tensorflow", forks=47524, open_issues=1312, size=5349,   commits=4668,  contributors=1437, subscribers_count=4601,  network_count=47525, repo_age_days=3705, language="C++",         has_license=1, topics_count=13),
        RepoInput(repo_name="microsoft/vscode",      forks=34902, open_issues=73,   size=1561,   commits=1201,  contributors=674,  subscribers_count=8183,  network_count=34902, repo_age_days=4323, language="TypeScript",  has_license=1, has_pages=1),
        RepoInput(repo_name="golang/go",             forks=15000, open_issues=5900, size=400000, commits=55000, contributors=2100, subscribers_count=3700,  network_count=15000, repo_age_days=5100, language="Go",          has_license=1, has_pages=1, releases=150, topics_count=10),
    ]
    return await predict(demo_repos)

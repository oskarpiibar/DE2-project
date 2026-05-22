"""
Star Predictor — FastAPI Backend
Loads the best model from MLflow and exposes prediction endpoints.
"""

import os
import numpy as np
import pandas as pd
from contextlib import asynccontextmanager
from typing import Optional

import mlflow
import mlflow.sklearn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration (override via env vars)
# ---------------------------------------------------------------------------
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://dev2:5000")
MLFLOW_MODEL_NAME   = os.getenv("MLFLOW_MODEL_NAME",   "star_predictor")
MLFLOW_MODEL_STAGE  = os.getenv("MLFLOW_MODEL_STAGE",  "Production")

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
    """Load model on startup, release on shutdown."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    model_uri = f"models:/{MLFLOW_MODEL_NAME}/{MLFLOW_MODEL_STAGE}"
    try:
        model_store["model"] = mlflow.sklearn.load_model(model_uri)
        print(f"[startup] Loaded model from {model_uri}")
    except Exception as e:
        print(f"[startup] WARNING: Could not load model from MLflow: {e}")
        print("[startup] Predictions will fail until a model is available.")
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
LANG_CHOICES = [
    "Python", "TypeScript", "JavaScript", "Go", "Rust", "C++", "Java",
    "Shell", "Jupyter Notebook", "C", "HTML", "Ruby", "C#", "Swift",
    "Kotlin", "CSS", "Other",
]

LANG_TO_COL = {
    "C++":              "lang_Cpp",
    "C#":               "lang_Csharp",
    "Jupyter Notebook": "lang_Jupyter_Notebook",
}


class RepoInput(BaseModel):
    """Raw GitHub repository features as a user would provide them."""
    repo_name:           str   = Field(...,  description="Display name (not used for prediction)")
    forks:               int   = Field(...,  ge=0)
    open_issues:         int   = Field(...,  ge=0)
    size:                int   = Field(...,  ge=0,   description="Repo size in KB")
    has_wiki:            int   = Field(0,    ge=0, le=1)
    has_pages:           int   = Field(0,    ge=0, le=1)
    archived:            int   = Field(0,    ge=0, le=1)
    commits:             int   = Field(...,  ge=0)
    contributors:        int   = Field(...,  ge=1)
    releases:            int   = Field(0,    ge=0)
    open_pull_requests:  int   = Field(0,    ge=0)
    subscribers_count:   int   = Field(...,  ge=0)
    network_count:       int   = Field(...,  ge=0)
    repo_age_days:       int   = Field(...,  ge=1)
    has_description:     int   = Field(1,    ge=0, le=1)
    has_homepage:        int   = Field(0,    ge=0, le=1)
    has_license:         int   = Field(1,    ge=0, le=1)
    topics_count:        int   = Field(0,    ge=0)
    language:            str   = Field("Other", description=f"Primary language. One of: {LANG_CHOICES}")


class RepoPrediction(BaseModel):
    repo_name:       str
    predicted_stars: int
    log_stars:       float


class RankingResponse(BaseModel):
    ranked: list[RepoPrediction]
    model_uri: str


# ---------------------------------------------------------------------------
# Feature engineering helper (mirrors preprocess.py logic)
# ---------------------------------------------------------------------------
def build_feature_row(repo: RepoInput) -> pd.DataFrame:
    """Convert a RepoInput into a single-row DataFrame matching FEATURE_COLUMNS."""
    row: dict = {col: 0 for col in FEATURE_COLUMNS}

    # Direct mappings
    for col in FEATURE_COLUMNS:
        if hasattr(repo, col):
            row[col] = getattr(repo, col)

    # Derived features
    row["commits_per_day"] = repo.commits / max(repo.repo_age_days, 1)
    # fork_ratio uses predicted stars proxy; we use subscribers as a proxy
    # (actual stars unknown at inference time — use 0+1 denominator gracefully)
    row["fork_ratio"] = repo.forks / (repo.subscribers_count + 1)

    # One-hot encode language
    lang = repo.language
    col_name = LANG_TO_COL.get(lang, f"lang_{lang.replace(' ', '_')}")
    if col_name in ALL_LANG_COLS:
        row[col_name] = 1
    else:
        row["lang_Other"] = 1

    return pd.DataFrame([row])[FEATURE_COLUMNS]


# ---------------------------------------------------------------------------
# Routes — pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": "model" in model_store,
        "mlflow_uri": MLFLOW_TRACKING_URI,
    }


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------
@app.post("/predict", response_model=RankingResponse)
async def predict(repos: list[RepoInput]):
    """
    Accept a list of repo feature objects.
    Returns them ranked by predicted star count (descending).
    """
    if "model" not in model_store:
        raise HTTPException(503, "Model not loaded. Check MLflow connection.")
    if not repos:
        raise HTTPException(400, "Provide at least one repository.")

    model = model_store["model"]
    results = []

    for repo in repos:
        X = build_feature_row(repo)
        log_pred = float(model.predict(X)[0])
        stars    = int(np.expm1(log_pred))
        results.append(RepoPrediction(
            repo_name=repo.repo_name,
            predicted_stars=stars,
            log_stars=round(log_pred, 4),
        ))

    ranked = sorted(results, key=lambda r: r.predicted_stars, reverse=True)

    model_uri = f"models:/{MLFLOW_MODEL_NAME}/{MLFLOW_MODEL_STAGE}"
    return RankingResponse(ranked=ranked, model_uri=model_uri)


@app.get("/predict/demo", response_model=RankingResponse)
async def predict_demo():
    """Run prediction on 5 hardcoded well-known repos for a quick demo."""
    demo_repos = [
        RepoInput(repo_name="torvalds/linux",       forks=47463, open_issues=479,  size=1201,   has_wiki=0, has_pages=0, archived=0, commits=611,   contributors=140,  releases=0,  open_pull_requests=226,  subscribers_count=6677,  network_count=47463, repo_age_days=2925, has_description=1, has_homepage=1, has_license=0, topics_count=6,  language="C"),
        RepoInput(repo_name="facebook/react",       forks=44515, open_issues=185,  size=572816, has_wiki=0, has_pages=0, archived=0, commits=41568, contributors=6450, releases=0,  open_pull_requests=74,   subscribers_count=8550,  network_count=44515, repo_age_days=4157, has_description=1, has_homepage=1, has_license=1, topics_count=15, language="JavaScript"),
        RepoInput(repo_name="tensorflow/tensorflow", forks=47524, open_issues=1312, size=5349,   has_wiki=0, has_pages=0, archived=0, commits=4668,  contributors=1437, releases=0,  open_pull_requests=1305, subscribers_count=4601,  network_count=47525, repo_age_days=3705, has_description=1, has_homepage=1, has_license=1, topics_count=13, language="C++"),
        RepoInput(repo_name="microsoft/vscode",     forks=34902, open_issues=73,   size=1561,   has_wiki=0, has_pages=1, archived=0, commits=1201,  contributors=674,  releases=0,  open_pull_requests=56,   subscribers_count=8183,  network_count=34902, repo_age_days=4323, has_description=1, has_homepage=0, has_license=1, topics_count=5,  language="TypeScript"),
        RepoInput(repo_name="golang/go",            forks=15000, open_issues=5900, size=400000, has_wiki=0, has_pages=1, archived=0, commits=55000, contributors=2100, releases=150, open_pull_requests=200, subscribers_count=3700, network_count=15000, repo_age_days=5100, has_description=1, has_homepage=1, has_license=1, topics_count=10, language="Go"),
    ]
    return await predict(demo_repos)

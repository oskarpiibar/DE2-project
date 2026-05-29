# ML Model Training

This component handles hyperparameter tuning, model selection, training, and inference for predicting GitHub repository popularity (`log_stars`) from 36 repository features.

---

## Overview

- **Task:** Regression — predict `log_stars` (log-transformed GitHub star count)
- **Features:** 36 repository metadata, activity, and language features
- **Dataset:** 1,000 samples, 80/20 train/test split
- **Tuning:** Bayesian search via Optuna, 50 trials per model, 5-fold CV inside each trial
- **Distributed:** Ray cluster across dev1 (master) and dev2 (worker)

---

## Directory Structure

```
models/
├── best_individual_model_lightgbm.pkl   # Trained best model (LightGBM)
├── best_individual_metadata.json        # Model metrics, hyperparameters, feature list
├── train_models.py                      # Full tuning + training pipeline
├── predict.py                           # Inference script
└── training_log.txt                     # Timestamped log of the training run
```

> The `models/` directory contains only the best individual model. The ensemble was explored as an additional step but not used in production — see Model Selection below.

---

## Setup

```bash
pip install ray[tune] optuna xgboost lightgbm scikit-learn pandas numpy psutil joblib
```

---

## Running the Training Pipeline

Make sure the Ray cluster is running before executing the script.

**On dev1 (master — always running):**
```bash
ray start --head --port=6379
```

**On dev2 (worker):**
```bash
ray start --address='dev1:6379'
```

**Verify the cluster:**
```bash
ray status
# Should show 2 active nodes
```

**Run training:**
```bash
cd /home/ubuntu/DE2-project/models
python3 train_models.py
```

The script will:
1. Tune XGBoost, LightGBM, and Random Forest via Ray Tune + Optuna (50 trials each, 5-fold CV)
2. Train Ridge and ElasticNet as fixed baselines
3. Compare all 5 models on the test set
4. Save the best model and its metadata

---

## Running Inference

```bash
# Run both individual model and ensemble
python3 predict.py --input /path/to/data.csv --mode both

# Individual model only
python3 predict.py --input /path/to/data.csv --mode individual

# Ensemble only
python3 predict.py --input /path/to/data.csv --mode ensemble

# Custom output path
python3 predict.py --input /path/to/data.csv --mode both --output /path/to/results.csv
```

The input CSV must contain the same 36 feature columns used during training. The target column (`log_stars`) does not need to be present. Predictions are saved as a CSV with a `pred_<model>` column appended.

---

## Model Selection

Five models were evaluated:

| Model | RMSE | MAE | R² |
|---|---|---|---|
| **LightGBM** ✓ | **0.0699** | **0.0462** | **0.9750** |
| XGBoost | 0.0749 | 0.0539 | 0.9713 |
| Random Forest | 0.1182 | 0.0725 | 0.9285 |
| Ridge | 0.2685 | 0.2099 | 0.6314 |
| ElasticNet | 0.3258 | 0.2569 | 0.4570 |

**LightGBM** was selected as the best individual model. A stacking ensemble (all 5 base models + Ridge meta-learner, trained with out-of-fold predictions) was also explored and achieved R²=0.9795 — a marginal improvement of Δ0.0045 over LightGBM alone. This gain was not considered significant enough to justify the added inference overhead of running five models in production, so the single LightGBM model was retained.

---

## Best Model — LightGBM

| Parameter | Value |
|---|---|
| `n_estimators` | 1000 |
| `max_depth` | 4 |
| `learning_rate` | 0.056 |
| `num_leaves` | 20 |
| `min_child_samples` | 5 |
| `subsample` | 0.957 |
| `colsample_bytree` | 0.966 |
| `reg_alpha` | 0.00079 |
| `reg_lambda` | 0.547 |

---

## Output Files

| File | Description |
|---|---|
| `best_individual_model_lightgbm.pkl` | Serialised trained LightGBM model, loadable with `joblib.load()` |
| `best_individual_metadata.json` | Model name, type, feature list, hyperparameters, RMSE/MAE/R² for all 5 models |
| `training_log.txt` | Full timestamped terminal output of the training run |
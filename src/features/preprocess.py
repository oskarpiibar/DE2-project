import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Languages with enough repos to get their own column (>= 9 repos in dataset)
TOP_LANGUAGES = [
    "Python", "TypeScript", "JavaScript", "Go", "Rust",
    "C++", "Java", "Shell", "Jupyter Notebook", "C",
    "HTML", "Ruby", "C#", "Swift", "Kotlin", "CSS"
]


def preprocess(input_path: str, output_path: str) -> pd.DataFrame:

    df = pd.read_csv(input_path)
    print(f"      Shape: {df.shape}")

    # log1p transform to normalize heavily right-skewed star distribution
    # Models will predict log_stars; reverse with np.expm1() to get real stars
    df["log_stars"] = np.log1p(df["stars"])

    cols_to_drop = [
        "name",         # identifier only
        "full_name",    # identifier only
        "watchers",     # identical to stars across all 1000 repos (data leakage)
        "created_at",   # will derive repo_age_days instead
        "updated_at",   # not used: days_since_last_update has no variation (max=2 days)
        "description",  # raw text: will convert to has_description binary
        "homepage",     # raw text: will convert to has_homepage binary
        "license",      # raw text: will convert to has_license binary
        "topics",       # raw text: will convert to topics_count numeric
        "language",     # raw string: will one-hot encode language_grouped
        "stars",        # replaced by log_stars as target
        "is_fork",       # all 0s
    ]

    # Only drop columns that actually exist
    cols_to_drop = [c for c in cols_to_drop if c in df.columns]
    df_raw = df.copy()  # keep original for reference
    df = df.drop(columns=cols_to_drop)

    now = datetime.now(timezone.utc)
    created = pd.to_datetime(df_raw["created_at"], utc=True)

    df["repo_age_days"] = (now - created).dt.days

    # Avoid division by zero for very new repos
    df["commits_per_day"] = df_raw["commits"] / df["repo_age_days"].replace(0, 1)
    df["fork_ratio"] = df_raw["forks"] / (df_raw["stars"] + 1)

    df["has_description"] = df_raw["description"].notnull().astype(int)
    df["has_homepage"]    = df_raw["homepage"].notnull().astype(int)
    df["has_license"]     = df_raw["license"].notnull().astype(int)

    # Topics: count how many tags a repo has (null is now 0)
    def count_topics(val):
        if pd.isnull(val) or val == "":
            return 0
        # Topics come as a comma-separated string or list-like string
        return len([t for t in str(val).split(",") if t.strip()])

    df["topics_count"] = df_raw["topics"].apply(count_topics)

    # Convert boolean columns from True/False strings to 0/1 integers
    for col in ["has_wiki", "has_pages", "archived"]:
        if col in df_raw.columns:
            df[col] = df_raw[col].map(
                {True: 1, False: 0, "TRUE": 1, "FALSE": 0, 1: 1, 0: 0}
            ).fillna(0).astype(int)

    # Fill single missing contributors/open_pull_requests with median
    for col in ["contributors", "open_pull_requests"]:
        if col in df.columns:
            median_val = df[col].median()
            missing = df[col].isnull().sum()
            if missing > 0:
                print(f"      Filling {missing} missing '{col}' with median ({median_val:.0f})")
                df[col] = df[col].fillna(median_val).astype(int)


    lang = df_raw["language"].fillna("Unknown")
    lang_grouped = lang.apply(lambda x: x if x in TOP_LANGUAGES else "Other")
    lang_dummies = pd.get_dummies(lang_grouped, prefix="lang").astype(int)
 
    # Rename special character columns so CSV handles them cleanly
    lang_dummies = lang_dummies.rename(columns={
        "lang_C++":              "lang_Cpp",
        "lang_C#":               "lang_Csharp",
        "lang_Jupyter Notebook": "lang_Jupyter_Notebook"
    })
 
    df = pd.concat([df, lang_dummies], axis=1)
 

    # Move log_stars to the last column (convention: target at end)
    target = df.pop("log_stars")
    df["log_stars"] = target

    # Drop any remaining rows with nulls (should be none at this point)
    before = len(df)
    df = df.dropna()
    after = len(df)
    if before != after:
        print(f"      Dropped {before - after} rows with remaining nulls")

    df.to_csv(output_path, index=False)
    print(f"\n Done! features.csv saved to {output_path}")
    print(f"   Final shape: {df.shape}")
    print(f"   Features ({df.shape[1] - 1}): {[c for c in df.columns if c != 'log_stars']}")
    print(f"   Target: log_stars")

    return df

# This block only runs when the script is executed directly
# It is skipped when the file is imported by another script (like by a pipeline)
if __name__ == "__main__":

    # Create a parser that accepts command-line arguments
    parser = argparse.ArgumentParser(description="GitHub repo feature engineering pipeline")

    # --input: path to raw CSV (uses default if not specified)
    parser.add_argument("--input",  default="data/raw/github_repositories.csv",
                        help="Path to raw CSV from Eric")

    # --output: where to save the processed features CSV (uses default if not specified)
    parser.add_argument("--output", default="data/processed/features.csv",
                        help="Path to save processed features CSV")

    # Read whatever was typed in the terminal and store it in args
    args = parser.parse_args()

    # Call the main preprocessing function with the provided (or default) paths
    preprocess(args.input, args.output)
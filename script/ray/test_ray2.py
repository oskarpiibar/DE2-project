import ray
from ray import tune

from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score


# Connect to Ray cluster
ray.init(address="auto")


def train_model(config):
    # Load dataset
    X, y = load_iris(return_X_y=True)

    # Create model
    model = RandomForestClassifier(
        n_estimators=config["n_estimators"],
        max_depth=config["max_depth"],
        min_samples_split=config["min_samples_split"],
        random_state=42,
        n_jobs=1
    )

    # Cross validation
    scores = cross_val_score(
        model,
        X,
        y,
        cv=3,
        scoring="accuracy"
    )

    # Report metric to Ray Tune
    tune.report({
        "mean_accuracy": scores.mean(), "done": True
    })


# Hyperparameter search space
search_space = {
    "n_estimators": tune.choice([10, 50, 100]),
    "max_depth": tune.choice([2, 5, 10]),
    "min_samples_split": tune.choice([2, 5, 10]),
}


# Run tuning
tuner = tune.Tuner(
    tune.with_resources(train_model, {"cpu": 1}),
    param_space=search_space,
    tune_config=tune.TuneConfig(
        metric="mean_accuracy",
        mode="max",
        num_samples=10
    )
)

results = tuner.fit()

# Best result
best_result = results.get_best_result()

print("\nBest Hyperparameters:")
print(best_result.config)

print("\nBest Accuracy:")
print(best_result.metrics["mean_accuracy"])
"""
Star Predictor — Locust Load Test
===================================
Tests two scenarios:
  1. Single VM  — target prod1 directly (bypass NGINX)
  2. Two VMs    — target NGINX load balancer

Run with:
  locust -f locustfile.py --host http://<target> --users 50 --spawn-rate 5 --run-time 60s --headless --csv results/single_vm
  locust -f locustfile.py --host http://<target> --users 50 --spawn-rate 5 --run-time 60s --headless --csv results/two_vm
"""

import json
import random
from locust import HttpUser, task, between


# ---------------------------------------------------------------------------
# Sample payloads — realistic GitHub repo feature sets
# ---------------------------------------------------------------------------
SAMPLE_REPOS = [
    {
        "repo_name": "sample/python-web-app",
        "forks": 1200, "open_issues": 45, "size": 8500,
        "commits": 3200, "contributors": 28, "releases": 12,
        "open_pull_requests": 8, "subscribers_count": 400,
        "network_count": 1200, "repo_age_days": 1200,
        "has_wiki": 1, "has_pages": 0, "archived": 0,
        "has_description": 1, "has_homepage": 1, "has_license": 1,
        "topics_count": 6, "language": "Python"
    },
    {
        "repo_name": "sample/js-framework",
        "forks": 8500, "open_issues": 210, "size": 45000,
        "commits": 12000, "contributors": 180, "releases": 40,
        "open_pull_requests": 35, "subscribers_count": 2100,
        "network_count": 8500, "repo_age_days": 2800,
        "has_wiki": 0, "has_pages": 1, "archived": 0,
        "has_description": 1, "has_homepage": 1, "has_license": 1,
        "topics_count": 10, "language": "JavaScript"
    },
    {
        "repo_name": "sample/go-cli-tool",
        "forks": 340, "open_issues": 12, "size": 1200,
        "commits": 890, "contributors": 9, "releases": 8,
        "open_pull_requests": 2, "subscribers_count": 120,
        "network_count": 340, "repo_age_days": 600,
        "has_wiki": 0, "has_pages": 0, "archived": 0,
        "has_description": 1, "has_homepage": 0, "has_license": 1,
        "topics_count": 3, "language": "Go"
    },
    {
        "repo_name": "sample/ml-library",
        "forks": 5200, "open_issues": 88, "size": 22000,
        "commits": 7800, "contributors": 95, "releases": 25,
        "open_pull_requests": 20, "subscribers_count": 1400,
        "network_count": 5200, "repo_age_days": 1800,
        "has_wiki": 1, "has_pages": 1, "archived": 0,
        "has_description": 1, "has_homepage": 1, "has_license": 1,
        "topics_count": 8, "language": "Python"
    },
    {
        "repo_name": "sample/rust-systems",
        "forks": 680, "open_issues": 30, "size": 3400,
        "commits": 2100, "contributors": 15, "releases": 6,
        "open_pull_requests": 5, "subscribers_count": 230,
        "network_count": 680, "repo_age_days": 900,
        "has_wiki": 0, "has_pages": 0, "archived": 0,
        "has_description": 1, "has_homepage": 0, "has_license": 1,
        "topics_count": 4, "language": "Rust"
    },
]


class StarPredictorUser(HttpUser):
    # Simulated wait between requests (seconds) — mimics real user behaviour
    wait_time = between(1, 3)

    @task(5)
    def predict(self):
        """Main prediction endpoint — weighted higher as it is the core task."""
        # Pick a random subset of 1-3 repos to simulate varied payload sizes
        repos = random.sample(SAMPLE_REPOS, k=random.randint(1, 3))
        self.client.post(
            "/predict",
            json=repos,
            name="/predict",
        )

    @task(2)
    def load_homepage(self):
        """Frontend homepage load."""
        self.client.get("/", name="/")

    @task(1)
    def health_check(self):
        """Health endpoint — also used to verify load balancer distribution."""
        self.client.get("/health", name="/health")

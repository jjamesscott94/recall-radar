"""Cloud Function: trigger the Recall Radar nightly GitHub workflow.

Invoked by Cloud Scheduler (OIDC-authenticated). Reads the GitHub token from
Secret Manager (never from code or env), then POSTs a workflow_dispatch to the
recall-radar repo. Returns 2xx on success so Cloud Scheduler doesn't retry.
"""

import json
import os

import functions_framework
import requests
from google.cloud import secretmanager

GITHUB_REPO = "jjamesscott94/recall-radar"
WORKFLOW_FILE = "nightly.yml"
SECRET_NAME = "recall-radar-github-token"


def _get_github_token() -> str:
    client = secretmanager.SecretManagerServiceClient()
    project = os.environ.get("GCP_PROJECT", "ai-healthcare-492907")
    name = f"projects/{project}/secrets/{SECRET_NAME}/versions/latest"
    resp = client.access_secret_version(request={"name": name})
    return resp.payload.data.decode("UTF-8").strip()


@functions_framework.http
def trigger(request):
    token = _get_github_token()
    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/"
        f"{WORKFLOW_FILE}/dispatches"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.post(url, headers=headers, json={"ref": "main"}, timeout=30)

    ok = resp.status_code == 204
    body = {"ok": ok, "github_status": resp.status_code}
    # 204 = accepted; anything else is an error (Cloud Scheduler will retry).
    return (json.dumps(body), 200 if ok else 500)

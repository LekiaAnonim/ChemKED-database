#!/usr/bin/env python
"""
Dispatch PyTeCK simulation for contributed ChemKED files.

Fires a ``pyteck-simulate`` repository_dispatch to kineticmodelssite.
The self-hosted runner there runs ``ci_simulate`` and posts results back
to this PR as a check-run and a comment.  No Cantera/PyTeCK needed here.

Environment variables:
  DISPATCH_TOKEN    GitHub token with repo scope on kineticmodelssite
  PYTECK_REPO_OWNER Owner of the kineticmodelssite repo (default: PR repo owner)
  PYTECK_REPO_NAME  Name of the kineticmodelssite repo (default: kineticmodelssite)
  PR_REPO           owner/repo of this PR (default: GITHUB_REPOSITORY)
  PR_NUMBER         Pull request number
  PR_HEAD_SHA       Commit SHA for check-run attribution
  CHANGED_FILES     JSON array of repo-relative file paths
"""

import base64
import json
import os
import sys
import urllib.request

GITHUB_API = "https://api.github.com"
SUPPORTED_EXPERIMENT_TYPES = {"ignition delay"}


def check_experiment_type(filepath):
    """Extract experiment-type by scanning lines — no yaml dependency needed."""
    with open(filepath, "r") as f:
        for line in f:
            if line.startswith("experiment-type:"):
                return line.split(":", 1)[1].strip().strip("'\"").lower()
    return ""


def collect_files_from_env():
    raw = os.environ.get("CHANGED_FILES", "[]")
    try:
        files = json.loads(raw)
    except json.JSONDecodeError:
        files = []
    return [f for f in files if f.endswith((".yaml", ".yml")) and os.path.isfile(f)]


def dispatch_to_pyteck(files, pr_repo, pr_number, commit_sha,
                       dispatch_token, pyteck_owner, pyteck_repo):
    encoded_files = []
    for path in files:
        with open(path, "rb") as f:
            content = f.read()
        encoded_files.append({
            "filename": os.path.basename(path),
            "repo_path": path,
            "content_base64": base64.b64encode(content).decode("ascii"),
        })

    payload = {
        "files": encoded_files,
        "pr_repo": pr_repo,
        "pr_number": int(pr_number),
        "commit_sha": commit_sha,
    }

    url = f"{GITHUB_API}/repos/{pyteck_owner}/{pyteck_repo}/dispatches"
    body = json.dumps({"event_type": "pyteck-simulate", "client_payload": payload}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"token {dispatch_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 204):
                print(f"::error::repository_dispatch failed ({resp.status})")
                sys.exit(1)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except Exception:
            pass
        print(f"::error::repository_dispatch failed ({e.code}): {detail}")
        sys.exit(1)

    print(f"Dispatched pyteck-simulate to {pyteck_owner}/{pyteck_repo} "
          f"for {len(files)} file(s) on PR #{pr_number}.")
    print("Results will be posted back to this PR as a check-run.")


def main():
    files = collect_files_from_env()
    if not files:
        print("No YAML files to dispatch to PyTeCK.")
        return

    dispatch_token = os.environ.get("DISPATCH_TOKEN", "")
    if not dispatch_token:
        print("::warning::DISPATCH_TOKEN not set — skipping PyTeCK dispatch.")
        return

    pr_repo = os.environ.get("PR_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    pr_number = os.environ.get("PR_NUMBER", "0")
    commit_sha = os.environ.get("PR_HEAD_SHA", "")

    if not pr_repo or not commit_sha:
        print("::warning::PR_REPO or PR_HEAD_SHA not set — skipping PyTeCK dispatch.")
        return

    default_owner = pr_repo.split("/")[0] if pr_repo else ""
    pyteck_owner = os.environ.get("PYTECK_REPO_OWNER", default_owner)
    pyteck_repo = os.environ.get("PYTECK_REPO_NAME", "kineticmodelssite")

    ig_files = []
    for f in files:
        exp_type = check_experiment_type(f)
        if exp_type in SUPPORTED_EXPERIMENT_TYPES:
            ig_files.append(f)
        else:
            print(f"  Skipped {f} — experiment type '{exp_type}' not supported by PyTeCK")

    if not ig_files:
        print("No ignition delay files to dispatch — skipping.")
        return

    dispatch_to_pyteck(ig_files, pr_repo, pr_number, commit_sha,
                       dispatch_token, pyteck_owner, pyteck_repo)


if __name__ == "__main__":
    main()

"""Apply the committed What-If selection rule (results/p4/whatif_selection.md; DL-037 §1).

For each estimator language (Go, Java, Python, Ruby): GitHub repository search
`language:L stars:>=1000 archived:false fork:false`, sorted by stars, first 30
results in order; a candidate qualifies when an active `.github/workflows/`
workflow has >= 200 completed runs created in the 90 days before today (UTC).
The first qualifying candidate is selected. Every candidate checked is recorded.

Read-only GitHub REST. The token comes from GITHUB_TOKEN or, with
--token-from-git-credential, from git's stored credential; it is never printed
or written.

    python scripts/select_whatif_repos.py --token-from-git-credential \
        --out ../results/p4/whatif/selection_result.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CODE = Path(__file__).resolve().parents[1]
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from advisor.github import GitHubClient  # noqa: E402
from advisor.history import HistoryError  # noqa: E402

LANGUAGES = ("Go", "Java", "Python", "Ruby")
QUERY = "language:{lang} stars:>=1000 archived:false fork:false"
MAX_CANDIDATES = 30
MIN_RUNS = 200
WINDOW_DAYS = 90
EXCLUDED = {"senith02/carbon-advisor-demo"}


def workflow_counts(client: GitHubClient, repo: str, cutoff: str) -> list[dict[str, Any]]:
    workflows, page = [], 1
    while True:
        body = client.get_json(f"/repos/{repo}/actions/workflows", {"per_page": 100, "page": page})
        batch = body.get("workflows") or []
        workflows += batch
        if len(batch) < 100:
            break
        page += 1
    out = []
    for wf in sorted(workflows, key=lambda w: w["id"]):
        path = str(wf.get("path") or "")
        if wf.get("state") != "active" or not path.startswith(".github/workflows/"):
            continue
        body = client.get_json(f"/repos/{repo}/actions/workflows/{wf['id']}/runs",
                               {"status": "completed", "created": f">={cutoff}", "per_page": 1})
        out.append({"id": wf["id"], "file": path.rsplit("/", 1)[-1], "completed_runs_in_window": body.get("total_count")})
        time.sleep(0.2)
    return out


def select(client: GitHubClient, today: datetime) -> dict[str, Any]:
    cutoff = (today - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    result: dict[str, Any] = {
        "rule": "results/p4/whatif_selection.md (DL-037 §1)", "selection_date_utc": today.strftime("%Y-%m-%d"),
        "created_cutoff": cutoff, "min_completed_runs": MIN_RUNS, "max_candidates": MAX_CANDIDATES,
        "languages": {},
    }
    for lang in LANGUAGES:
        query = QUERY.format(lang=lang)
        found = client.get_json("/search/repositories", {"q": query, "sort": "stars", "order": "desc",
                                                         "per_page": MAX_CANDIDATES})
        checked, selected = [], None
        for rank, item in enumerate(found.get("items") or [], start=1):
            repo = item["full_name"]
            if repo in EXCLUDED:
                continue
            entry: dict[str, Any] = {"rank": rank, "repository": repo, "stars": item.get("stargazers_count")}
            try:
                counts = workflow_counts(client, repo, cutoff)
            except HistoryError as exc:
                entry.update(qualifies=False, note=f"workflows unavailable: {exc}")
                checked.append(entry)
                continue
            best = max(counts, key=lambda w: (w["completed_runs_in_window"] or 0, -w["id"]), default=None)
            entry.update(workflows_checked=len(counts), best_workflow=best,
                         qualifies=bool(best and (best["completed_runs_in_window"] or 0) >= MIN_RUNS))
            checked.append(entry)
            if entry["qualifies"]:
                selected = {"repository": repo, "workflow": best["file"],
                            "completed_runs_in_window": best["completed_runs_in_window"]}
                break
        result["languages"][lang] = {"query": query, "candidates_checked": checked,
                                     "selected": selected or "no qualifying repository"}
        time.sleep(2.0)  # the search API allows 30 requests a minute
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--token-from-git-credential", action="store_true")
    args = parser.parse_args(argv)
    if args.token_from_git_credential:
        from scripts.collect_demo_runs import _git_credential_token
        token = _git_credential_token()
    else:
        token = os.environ.get("GITHUB_TOKEN")
    result = select(GitHubClient(token), datetime.now(timezone.utc))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    for lang, block in result["languages"].items():
        print(f"{lang}: {block['selected']} ({len(block['candidates_checked'])} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

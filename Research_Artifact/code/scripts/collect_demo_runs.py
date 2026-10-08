"""Collect the P4-T2 demo-repository runs into results/p4/demo_runs/ (DL-033 R3-E; DL-036 §7).

For each run it records the run and job metadata, downloads the advisor's
workflow artifacts (request, response, Step Summary copy, audit record), then
assembles:

- ``runs.json``            run links, events, branches, and every job's and step's conclusion;
- ``combined_audit.jsonl`` every advisor audit record, in run order;
- ``validator_result.json`` ``replay/validate_invariants.py`` over the combined audit log;
- ``decisions.md``         one row per advisory job, generated from the files above.

Demonstration evidence, never research evidence (R3-B10). Network access is read-only GitHub REST.
Artifact downloads need a token even on a public repository: ``GITHUB_TOKEN`` from the environment,
or ``--token-from-git-credential``. The token is never printed or written.

    python scripts/collect_demo_runs.py --repo senith02/carbon-advisor-demo \
        --out ../results/p4/demo_runs --token-from-git-credential RUN_ID [RUN_ID ...]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

CODE = Path(__file__).resolve().parents[1]
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

API = "https://api.github.com"


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Artifact zips redirect to blob storage; the token is never forwarded there."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


def _git_credential_token() -> str:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("no github.com credential available from git")


def _get(url: str, token: str | None) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "p4-collect-demo-runs",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    opener = urllib.request.build_opener(_DropAuthOnRedirect)
    with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def fetch(repo: str, run_ids: list[str], out: Path, token: str) -> list[dict[str, Any]]:
    """Download run metadata and artifacts. Returns the runs.json payload."""
    runs = []
    for run_id in run_ids:
        run = json.loads(_get(f"{API}/repos/{repo}/actions/runs/{run_id}", token))
        jobs = json.loads(_get(f"{API}/repos/{repo}/actions/runs/{run_id}/jobs", token))["jobs"]
        listing = json.loads(_get(f"{API}/repos/{repo}/actions/runs/{run_id}/artifacts", token))
        for artifact in listing["artifacts"]:
            dest = out / str(run_id) / artifact["name"]
            dest.mkdir(parents=True, exist_ok=True)
            zipfile.ZipFile(io.BytesIO(_get(artifact["archive_download_url"], token))).extractall(dest)
        runs.append({
            "run_id": run["id"], "workflow": run["path"].rsplit("/", 1)[-1], "event": run["event"],
            "head_branch": run["head_branch"], "head_sha": run["head_sha"], "html_url": run["html_url"],
            "created_at": run["created_at"], "run_started_at": run["run_started_at"],
            "updated_at": run["updated_at"], "status": run["status"], "conclusion": run["conclusion"],
            "jobs": [{"name": j["name"], "conclusion": j["conclusion"], "html_url": j["html_url"],
                      "steps": [{"name": s["name"], "conclusion": s["conclusion"]} for s in j["steps"]]}
                     for j in jobs],
            "artifacts": [a["name"] for a in listing["artifacts"]],
        })
    return runs


def assemble(out: Path, runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Offline: combined audit log, validator result and the decisions table."""
    import pandas as pd

    from replay import validate_invariants

    records, rows = [], []
    for run in runs:
        for artifact_dir in sorted((out / str(run["run_id"])).glob("*")):
            response = json.loads((artifact_dir / "response.json").read_text(encoding="utf-8"))
            request = json.loads((artifact_dir / "request.json").read_text(encoding="utf-8"))
            audit = artifact_dir / "audit.jsonl"
            if audit.is_file():
                records += [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()]
            job_name = artifact_dir.name
            advisor_steps = [s for j in run["jobs"] for s in j["steps"] if "github-action@" in s["name"]
                             and not s["name"].startswith("Post ")]
            defer = response.get("defer_until") or {}
            rows.append({
                "run_id": run["run_id"], "html_url": run["html_url"], "event": run["event"],
                "branch": request.get("branch"), "artifact": job_name,
                "compute_region": request.get("compute_region"), "scenario": bool(response.get("scenario")),
                "display": response.get("display"), "outcome_kind": response.get("outcome_kind"),
                "policy_action": response.get("policy_action"), "stage1_rule": response.get("stage1_rule"),
                "vetoes": response.get("vetoes") or [], "fail_safe_code": response.get("fail_safe_code"),
                "d_hat_seconds": response.get("d_hat_seconds"), "d_hat_rung": response.get("d_hat_rung"),
                "n_history": response.get("n_history"), "defer_until_utc": defer.get("utc"),
                "advisor_steps_success": bool(advisor_steps) and all(s["conclusion"] == "success" for s in advisor_steps),
            })

    (out / "combined_audit.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
    result = validate_invariants.audit_frame(pd.DataFrame(records), path="combined_audit.jsonl")
    validator = {**result.as_dict(), "records": len(records),
                 "command": "replay.validate_invariants.audit_frame over combined_audit.jsonl"}
    (out / "validator_result.json").write_text(json.dumps(validator, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "decisions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    def cell(value: Any) -> str:
        if value is None or value == [] or value == "":
            return "—"
        if isinstance(value, float):
            return f"{value:.0f}"
        return ", ".join(value) if isinstance(value, list) else str(value)

    lines = [
        "# P4-T2 demo runs — decisions",
        "",
        "> **Demonstration — not research evidence.** Generated by `scripts/collect_demo_runs.py` from the",
        "> downloaded workflow artifacts; every cell is a field of `decisions.json`.",
        "",
        "| run | event | branch | job | region | display | kind | policy | stage-1 rule | vetoes | fail-safe | d̂ (s) | rung | n | defer until (UTC) | step exit 0 |",
        "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: | :-- | --: | :-- | :-: |",
    ]
    for r in rows:
        lines.append(
            f"| [{r['run_id']}]({r['html_url']}) | {r['event']} | `{r['branch']}` | {r['artifact']} | "
            f"{cell(r['compute_region'])} | {r['display']} | {r['outcome_kind']} | {cell(r['policy_action'])} | "
            f"{cell(r['stage1_rule'])} | {cell(r['vetoes'])} | {cell(r['fail_safe_code'])} | "
            f"{cell(r['d_hat_seconds'])} | {cell(r['d_hat_rung'])} | {cell(r['n_history'])} | "
            f"{cell(r['defer_until_utc'])} | {'✓' if r['advisor_steps_success'] else '✗'} |")
    lines += ["", f"Validator: {validator['violations']} violations over {validator['records']} audit records "
                  f"({validator['deferred']} deferred); passed = {validator['passed']}.", ""]
    (out / "decisions.md").write_text("\n".join(lines), encoding="utf-8")
    return validator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--token-from-git-credential", action="store_true")
    parser.add_argument("run_ids", nargs="+")
    args = parser.parse_args(argv)
    token = _git_credential_token() if args.token_from_git_credential else os.environ.get("GITHUB_TOKEN")
    if not token:
        print("error: artifact downloads need GITHUB_TOKEN or --token-from-git-credential", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runs = fetch(args.repo, args.run_ids, out, token)
    (out / "runs.json").write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
    validator = assemble(out, runs)
    print(f"{len(runs)} runs; validator: {validator['violations']} violations over {validator['records']} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())

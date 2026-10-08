# Repo What-If Report — public-repository selection rule (P4-T3 S1)

> **Demonstration — not research evidence.** This file fixes *which* public repositories receive a
> What-If report. It was written and committed **before any report was generated** (DL-033 R3-D;
> DL-037 §1). The rule is an author decision of 2026-10-08, and nothing in it depends on any report
> outcome.

## The rule

1. **Languages.** Go, Java, Python and Ruby: the languages the frozen duration estimator was fitted on
   (`lang_levels` of fit `1088d5546f47ff12`). One repository is selected per language.
2. **Candidates.** For each language `L`, the GitHub repository search query

   ```
   language:L stars:>=1000 archived:false fork:false
   ```

   sorted by stars, descending. At most the first **30** results are scanned, in that order.
   `senith02/carbon-advisor-demo` is excluded from the search, because it is reported anyway.
3. **Qualifying** (DL-033 R3-D). A candidate qualifies if it is public and has an **active** workflow
   under `.github/workflows/` with **≥ 200 completed runs created in the 90 days before the selection
   date**.
   - Each workflow is counted with
     `GET /repos/{o}/{r}/actions/workflows/{id}/runs?status=completed&created=>=<cut-off>&per_page=1`,
     reading `total_count`. GitHub caps this at 1,000, which does not affect a ≥ 200 test.
   - **The workflow analysed** is the one with the most such runs. Ties go to the lowest workflow id.
4. **Selected.** The first qualifying candidate per language. If none of the 30 qualifies, the
   language is reported as "no qualifying repository". It is not replaced by a looser search.
5. **Reported.** Every selected repository is reported, **whatever the outcome**, plus the demo
   repository. Nothing is dropped after its report is seen.

## What each report reads

- The last ≤ 500 completed runs of the analysed workflow (`history_cap` default, DL-033 R3-C6), read
  only.
- The repository's primary language.
- The selection run's own output — candidates checked, counts, cut-off date and the selection — is
  written to `results/p4/whatif/selection_result.json` by `code/scripts/select_whatif_repos.py`.

## What is published

Aggregates only (DL-033 R3-C8 item 6; DL-037 §6). The per-run history snapshot stays local and is
pinned by its sha256 in each report. No login, actor or personal field is stored.

"""The predeclared §A1.7 family-admission rule (P1-T7).

`results/p0/eval_protocol.md` §A1.7 fixes, **before any result was inspected**,
the condition an SE feature family must meet to enter `policy_spec.yaml`:

| Altitude | Condition | Floor |
| :-- | :-- | :-- |
| **Model** (§A1.4) | ΔPR-AUC vs `{d̂}` — 95% CI excludes 0 | **and** point estimate ≥ **0.01** absolute |

This module implements the **model** altitude only; the decision altitude
(§A1.5, frontier dominance) is P3-T3's and is not modelled here.

Three properties this module exists to guarantee:

* **The rule is a function, not a judgement.** It reads a ΔPR-AUC record and
  returns a verdict plus the number that decided it. There is no branch that
  depends on which family is being judged.
* **"≥ 0.01 absolute" means an improvement of at least 0.01 in absolute
  units — not `|Δ| ≥ 0.01`.** A family that is *worse* than the control by
  more than the floor is rejected, not admitted. This reading was fixed in
  **DL-019 §2** (written before the P1-T6 deltas existed), so it is not a
  post-hoc disambiguation.
* **The floor sweep is part of the rule, not a robustness afterthought.**
  §A1.7 requires every admission decision to be re-run at ×0.5 and ×2 of the
  floor and the differences reported.

The same functions are re-used, unchanged, on test-split deltas at P3-T1 —
which is the point of implementing the rule once, here, before those numbers
exist.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: §A1.7's model-altitude floor: ΔPR-AUC point estimate, absolute units.
MODEL_FLOOR_ABS: float = 0.01

#: §A1.7: "every admission decision is re-run at ×0.5 and ×2" of the floor.
FLOOR_SWEEP_MULTIPLIERS: tuple[float, ...] = (0.5, 1.0, 2.0)


def ci_direction(ci_lo: float, ci_hi: float) -> str:
    """Where the 95% CI sits relative to 0: above, below, or spanning it."""
    if ci_lo > 0:
        return "positive"
    if ci_hi < 0:
        return "negative"
    return "spans_zero"


def apply_model_floor(pr_auc_delta: Mapping[str, Any], *,
                      floor: float = MODEL_FLOOR_ABS) -> dict[str, Any]:
    """Judge one family's ΔPR-AUC record against the §A1.7 model condition.

    ``pr_auc_delta`` is one family's ``delta_vs_control["pr_auc"]`` record from
    ``results/p1/ablation/deltas.json`` (``delta``, ``ci_lo``, ``ci_hi``).

    Returns the verdict **and** the number that decided it, so every admission
    line in the report traces to a P1-T6 figure rather than to prose.
    """
    delta = float(pr_auc_delta["delta"])
    ci_lo = float(pr_auc_delta["ci_lo"])
    ci_hi = float(pr_auc_delta["ci_hi"])

    direction = ci_direction(ci_lo, ci_hi)
    excludes_zero = direction != "spans_zero"
    # DL-019 §2: an *improvement* of at least `floor`, not |Δ| ≥ floor.
    meets_floor = delta >= floor
    beneficial = direction == "positive"
    admitted = bool(excludes_zero and meets_floor and beneficial)

    if admitted:
        decided_by = (f"ΔPR-AUC {delta:+.6f} ≥ floor {floor:+.6f} and its 95% CI "
                      f"[{ci_lo:+.6f}, {ci_hi:+.6f}] excludes 0 above it")
        reason_short = "clears floor, CI above 0"
    elif direction == "negative":
        decided_by = (f"ΔPR-AUC {delta:+.6f} is below the {floor:+.6f} floor, and its "
                      f"95% CI [{ci_lo:+.6f}, {ci_hi:+.6f}] lies entirely below 0 — "
                      f"the family is significantly *worse* than the control, not "
                      f"merely short of the floor")
        reason_short = "below floor; CI entirely below 0 (significantly worse)"
    elif not meets_floor:
        decided_by = (f"ΔPR-AUC {delta:+.6f} is below the {floor:+.6f} floor "
                      f"(95% CI [{ci_lo:+.6f}, {ci_hi:+.6f}])")
        reason_short = "below floor"
    else:
        decided_by = (f"ΔPR-AUC {delta:+.6f} clears the {floor:+.6f} floor but its "
                      f"95% CI [{ci_lo:+.6f}, {ci_hi:+.6f}] includes 0")
        reason_short = "clears floor, but CI includes 0"

    return {
        "admitted": admitted,
        "delta_pr_auc": delta,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "floor": float(floor),
        "ci_excludes_zero": excludes_zero,
        "ci_direction": direction,
        "meets_floor": meets_floor,
        "decided_by": decided_by,
        "reason_short": reason_short,
    }


def admission_set(families: Mapping[str, Mapping[str, Any]], *,
                  floor: float = MODEL_FLOOR_ABS) -> dict[str, Any]:
    """Apply :func:`apply_model_floor` to every family at one floor.

    ``families`` maps family id -> that family's ``delta_vs_control["pr_auc"]``
    record. Returns per-family verdicts plus the sorted admitted set.
    """
    verdicts = {fam: apply_model_floor(rec, floor=floor)
                for fam, rec in families.items()}
    return {
        "floor": float(floor),
        "verdicts": verdicts,
        "admitted": sorted(f for f, v in verdicts.items() if v["admitted"]),
        "rejected": sorted(f for f, v in verdicts.items() if not v["admitted"]),
    }


def floor_sweep(families: Mapping[str, Mapping[str, Any]], *,
                base_floor: float = MODEL_FLOOR_ABS,
                multipliers: Sequence[float] = FLOOR_SWEEP_MULTIPLIERS) -> dict[str, Any]:
    """Re-run the rule at each ×multiplier of the floor (§A1.7).

    Only the **floor** scales; the CI-excludes-0 condition is not a floor and
    is held fixed across the sweep. ``stable`` is true when the admitted set is
    identical at every swept floor — §A1.7 treats a stable set as the stronger
    finding.
    """
    by_floor: dict[str, Any] = {}
    for m in multipliers:
        floor = base_floor * m
        result = admission_set(families, floor=floor)
        by_floor[f"x{m:g}"] = {
            "multiplier": float(m),
            "floor": floor,
            "admitted": result["admitted"],
            "rejected": result["rejected"],
        }
    sets = [tuple(v["admitted"]) for v in by_floor.values()]
    return {
        "base_floor": float(base_floor),
        "multipliers": [float(m) for m in multipliers],
        "by_floor": by_floor,
        "stable": bool(len(set(sets)) == 1),
        "note": "Only the floor scales across the sweep; the CI-excludes-0 "
                "condition is not a floor and is held fixed (§A1.7).",
    }

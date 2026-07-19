# Decision engine

The function [`app/engine/decision.py:decide`](../apps/api/app/engine/decision.py)
implements the 7-stage pipeline from `claude reccomendation.txt` §12
verbatim. It is a **pure** function: given lists of `GateEvaluation`
and `ModelOpinionData` (or any duck-typed equivalent) plus a
`StrategyConfigSpec`, it returns a `DecisionResult`. No I/O.

## Inputs

| Argument | Type | Notes |
|---|---|---|
| `gates` | `list[GateEvaluation]` | Each is `{name, status, score, confidence, reason, evidence}`. |
| `opinions` | `list[ModelOpinionData]` | Duck-typed: any object with `.role`, `.status`, `.direction`, `.confidence`, `.role_weight`, `.confidence_cap`, `.risk_flags`, `.evidence_ids`, `.is_valid` (bool property or zero-arg method). |
| `spec` | `StrategyConfigSpec` | The pydantic-validated config being used for this run. |
| `total_configured_gates` | `int` | Defaults to 6. Used in `Data Completeness = quorum_count / total_configured_gates`. |
| `total_directional_roles` | `int` | Defaults to 4. Used in `Model Completeness = valid_roles / total_directional_roles`. |

## Steps 1–7

1. **Gate score.** For every gate with status not `UNAVAILABLE`:
   ```
   contribution[g] = gate_score[g] * gate_weight[g] * gate_confidence[g]
   Gate Score = sum(contribution) / sum(gate_weight[g])       # in [-100, 100]
   ```
   `quorum_count = count(gates with status)`; `Gate F` (risk_tradeability)
   contributes even when status is `VETO`.

2. **Model score & agreement.** For every valid directional opinion:
   ```
   sign = LONG: +1, SHORT: -1, WAIT/AVOID: 0
   cap  = spec.directional_roles[role].confidence_cap
   eff_conf = min(confidence, cap) if sign > 0 else min(confidence, 1.0)
   contribution = sign * role_weight * eff_conf
   Model Score = 100 * sum(contribution) / sum(role_weight)
   ```
   Agreement is the weighted share of valid roles that agree with the
   majority direction; `WAIT/AVOID` votes always reduce agreement.

3. **Composite direction score.**
   ```
   Composite = gate_s * composite_gate_weight
             + model_s * composite_model_weight
   ```

4. **Quorum & completeness.** If `quorum_count < minimum_quorum_gate_count`
   the run terminates at `WAIT` with `INSUFFICIENT_QUORUM`. Otherwise
   `Data Completeness = quorum_count / total_configured_gates` and
   `Model Completeness = valid_roles / total_directional_roles`.

5. **Vetoes** (any one forces `AVOID`):
   - Any gate with `status == VETO` (deterministic gate veto).
   - Any AI role lists a `risk_flag` in `spec.hard_veto_risk_flags`.
   - `Model Agreement < spec.minimum_model_agreement`.
   - `Data Completeness < spec.minimum_data_quality`.

6. **Final state.**
   | Condition | State |
   |---|---|
   | No viable data → engine fails before analysis | `DATA_INVALID` |
   | Any Step 5 veto | `AVOID` |
   | `abs(Composite) < spec.minimum_direction_score` | `WAIT` |
   | `Composite ≥ +minimum_direction_score` | `LONG_CANDIDATE` |
   | `Composite ≤ -minimum_direction_score` | `SHORT_CANDIDATE` |

7. **Trade plan.** Only on `LONG/SHORT_CANDIDATE`. Uses 1.5×ATR stop and
   3×ATR (or `spec.minimum_risk_reward`) take-profit. Synthesizes a
   human-readable summary.

## Confidence cap (subtle but critical)

`risk_reviewer` and `skeptical_reviewer` have `confidence_cap = 0.35`
in the default config. The cap applies **only** to positive-contribution
direction. If a risk/skeptic role votes `SHORT` on a bullish setup,
its vote is *uncapped* on the negative side — otherwise the cap would
silently suppress the very skeptical signal it's meant to amplify.

## Test surface

`tests/test_decision.py` covers quorum gating, veto paths, agreement
floor, composite score math, cap asymmetry, and the LONG/SHORT
final-state transitions.

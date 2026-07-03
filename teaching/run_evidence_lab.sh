#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/bin:/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$ROOT/teaching/fixtures/evidence-review"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${1:-$ROOT/.validation-tmp/evidence-lab-$STAMP}"

if [[ -e "$TARGET" ]]; then
  echo "Target already exists; choose a new path: $TARGET" >&2
  exit 1
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Python 3.10+ was not found. Set PYTHON_BIN." >&2
  exit 1
fi

mkdir -p "$TARGET/research/artifacts" "$TARGET/research/results"
cp "$FIXTURE/contract.json" "$TARGET/contract.json"
cp "$FIXTURE/environment.json" "$TARGET/environment.json"
cp "$FIXTURE/run_experiment.sh" "$TARGET/run_experiment.sh"
cp "$FIXTURE/experiment.md" "$TARGET/research/artifacts/experiment-demo.md"
cp "$FIXTURE/review.md" "$TARGET/research/artifacts/review-demo.md"
cp "$FIXTURE/analysis.md" "$TARGET/research/artifacts/analysis-demo.md"

STATE="$ROOT/plugins/deepscientist-lite/scripts/ds_lite_state.py"
EVIDENCE="$ROOT/plugins/deepscientist-lite/scripts/ds_lite_evidence.py"

"$PYTHON" "$STATE" init --root "$TARGET" --title "Evidence Review Lab" --question "Can a claim survive a deterministic review gate?"
"$PYTHON" "$EVIDENCE" init --root "$TARGET" --run-id demo-run --contract "$TARGET/contract.json"

(
  cd "$TARGET"
  bash run_experiment.sh > stdout.raw.log 2> stderr.raw.log
)

"$PYTHON" "$EVIDENCE" finalize \
  --root "$TARGET" \
  --run-id demo-run \
  --exit-code 0 \
  --stdout "$TARGET/stdout.raw.log" \
  --stderr "$TARGET/stderr.raw.log" \
  --metrics "$TARGET/research/results/metrics.json" \
  --environment "$TARGET/environment.json" \
  --output research/results/result.json
"$PYTHON" "$EVIDENCE" verify --root "$TARGET" --run-id demo-run --strict

"$PYTHON" "$STATE" add-node \
  --root "$TARGET" --id experiment-demo --kind experiment --parent intake-root --relation next \
  --title "Evidence-bearing experiment" \
  --artifact-path research/artifacts/experiment-demo.md \
  --evidence-path research/evidence/demo-run/manifest.json --active
"$PYTHON" "$STATE" add-node \
  --root "$TARGET" --id review-demo --kind review --parent experiment-demo --relation next \
  --title "Independent review pass" \
  --artifact-path research/artifacts/review-demo.md \
  --evidence-path research/evidence/demo-run/manifest.json --active
"$PYTHON" "$STATE" add-node \
  --root "$TARGET" --id analysis-demo --kind analysis --parent review-demo --relation next \
  --title "Reviewed analysis" \
  --artifact-path research/artifacts/analysis-demo.md --active
"$PYTHON" "$STATE" validate --root "$TARGET" --strict
"$PYTHON" "$STATE" trace --root "$TARGET" --node analysis-demo --format markdown

echo "Evidence lab project retained at: $TARGET"

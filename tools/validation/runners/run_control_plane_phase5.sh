#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$repo_root"
codex_version="0.146.0"
evidence_root=""
dbos_root=""
codex_bin=""
codex_sha256=""
schema_root=""
python_bin="/opt/anaconda3/bin/python"
python_version=""
windows_package_root=""
linux_package_root=""
legacy_complete=""
phase4_decision=""
phase4_decision_sha256=""
regressions=""
publication_actions=""
declare -A receipts=()
required_receipts=(
  runtime-windows runtime-linux resource-windows resource-linux stable-hook
  stable-v2-action dbos-upgrade supervisor-windows supervisor-wsl real-host-chaos
  network-matrix synthetic-provider fresh-desktop openscience matched-effect backup-restore
)

usage() {
  echo "usage: run_control_plane_phase5.sh --evidence-root PATH --dbos-root PATH --codex-bin PATH --codex-sha256 SHA256 --schema-root PATH --python-bin PATH --python-version VERSION --windows-package-root PATH --linux-package-root PATH --receipt NAME=PATH... --phase4-decision PATH --phase4-decision-sha256 SHA256 --legacy-complete PATH --regressions PATH --publication-actions PATH" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --evidence-root) evidence_root="${2:-}"; shift 2 ;;
    --dbos-root) dbos_root="${2:-}"; shift 2 ;;
    --codex-bin) codex_bin="${2:-}"; shift 2 ;;
    --codex-sha256) codex_sha256="${2:-}"; shift 2 ;;
    --schema-root) schema_root="${2:-}"; shift 2 ;;
    --python-bin) python_bin="${2:-}"; shift 2 ;;
    --python-version) python_version="${2:-}"; shift 2 ;;
    --windows-package-root) windows_package_root="${2:-}"; shift 2 ;;
    --linux-package-root) linux_package_root="${2:-}"; shift 2 ;;
    --legacy-complete) legacy_complete="${2:-}"; shift 2 ;;
    --phase4-decision) phase4_decision="${2:-}"; shift 2 ;;
    --phase4-decision-sha256) phase4_decision_sha256="${2:-}"; shift 2 ;;
    --regressions) regressions="${2:-}"; shift 2 ;;
    --publication-actions) publication_actions="${2:-}"; shift 2 ;;
    --receipt)
      [[ "${2:-}" == *=* ]] || usage
      receipt_name="${2%%=*}"
      receipt_path="${2#*=}"
      [[ -z "${receipts[$receipt_name]+x}" ]] || { echo "duplicate receipt: $receipt_name" >&2; exit 2; }
      receipts[$receipt_name]="$receipt_path"
      shift 2
      ;;
    *) usage ;;
  esac
done

[[ -n "$evidence_root" && -n "$dbos_root" && -n "$codex_bin" && -n "$codex_sha256" ]] || usage
[[ -n "$schema_root" && -n "$python_bin" && -n "$python_version" ]] || usage
[[ -n "$windows_package_root" && -n "$linux_package_root" ]] || usage
[[ -n "$phase4_decision" && -n "$phase4_decision_sha256" && -n "$legacy_complete" ]] || usage
[[ -n "$regressions" && -n "$publication_actions" ]] || usage

evidence_root="$($python_bin -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$evidence_root")"
case "$evidence_root" in "$repo_root/research"/*) ;; *) echo "evidence root must stay inside repository research directory" >&2; exit 2 ;; esac
[[ ! -e "$evidence_root" ]] || { echo "evidence root already exists" >&2; exit 2; }
[[ -d "$(dirname -- "$evidence_root")" ]] || { echo "evidence root parent is missing" >&2; exit 2; }
[[ -f "$codex_bin" && -d "$schema_root" && -d "$dbos_root" ]] || { echo "runtime inputs are missing" >&2; exit 2; }
[[ -d "$windows_package_root" && -d "$linux_package_root" ]] || { echo "package roots are missing" >&2; exit 2; }
[[ -d "$dbos_root/dbos-2.29.0.dist-info" ]] || { echo "DBOS 2.29.0 required" >&2; exit 2; }
[[ "$($python_bin -c 'import platform; print(platform.python_version())')" == "$python_version" ]] || { echo "pinned Python version required" >&2; exit 2; }
[[ "$($codex_bin --version)" == "codex-cli $codex_version" ]] || { echo "Codex stable 0.146.0 required" >&2; exit 2; }
observed_sha="$($python_bin -c 'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$codex_bin")"
[[ "${observed_sha,,}" == "${codex_sha256,,}" ]] || { echo "Codex binary SHA-256 mismatch" >&2; exit 2; }

for name in "${required_receipts[@]}"; do
  [[ -n "${receipts[$name]+x}" ]] || { echo "missing receipt: $name" >&2; exit 2; }
  [[ -f "${receipts[$name]}" ]] || { echo "receipt file is missing: $name" >&2; exit 2; }
done
[[ "${#receipts[@]}" -eq "${#required_receipts[@]}" ]] || { echo "unsupported receipt name supplied" >&2; exit 2; }
for path in "$phase4_decision" "$legacy_complete" "$regressions" "$publication_actions"; do
  [[ -f "$path" ]] || { echo "final assembly input is missing" >&2; exit 2; }
done
observed_phase4_sha="$($python_bin -c 'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$phase4_decision")"
[[ "${observed_phase4_sha,,}" == "${phase4_decision_sha256,,}" ]] || { echo "authoritative Phase4 decision SHA-256 mismatch" >&2; exit 2; }
observed_phase4_sha="$($python_bin -c 'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$phase4_decision")"
[[ "${observed_phase4_sha,,}" == "${phase4_decision_sha256,,}" ]] || { echo "authoritative Phase4 decision SHA-256 mismatch" >&2; exit 2; }

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$dbos_root:$repo_root/plugins/deepscientist-lite-core/controller:$repo_root${PYTHONPATH:+:$PYTHONPATH}"
"$python_bin" -c 'import sys; from pathlib import Path; from ds_lite_control.runtime_pin import verify_runtime_selection; result=verify_runtime_selection(Path(sys.argv[1]),Path(sys.argv[2]),expected_version=sys.argv[3]); raise SystemExit(0 if result["valid"] else 2)' "$codex_bin" "$schema_root" "$codex_version"

mkdir "$evidence_root"
phase5=("$python_bin" "$repo_root/teaching/control_plane_phase5_final.py")
"${phase5[@]}" package-manifest --package-root "$windows_package_root" --output "$evidence_root/package-windows.json"
"${phase5[@]}" package-manifest --package-root "$linux_package_root" --output "$evidence_root/package-linux.json"
"${phase5[@]}" candidate --repository "$repo_root" --windows-package "$evidence_root/package-windows.json" --linux-package "$evidence_root/package-linux.json" --output "$evidence_root/release-candidate.json"

gate_args=()
for name in "${required_receipts[@]}"; do
  original="$evidence_root/$name-original.json"
  wrapper="$evidence_root/$name-candidate-evidence.json"
  cp -- "${receipts[$name]}" "$original"
  "${phase5[@]}" evidence --input-name "$name" --candidate "$evidence_root/release-candidate.json" --original-receipt "$original" --output "$wrapper"
  gate_args+=(--input "$name=$wrapper")
done
"${phase5[@]}" gate --gate-id phase5-real-host --candidate "$evidence_root/release-candidate.json" "${gate_args[@]}" --output "$evidence_root/phase5-real-host-gate.json"
cp -- "$phase4_decision" "$evidence_root/phase4-decision-original.json"
"${phase5[@]}" gate --gate-id phase4-real-gate --candidate "$evidence_root/release-candidate.json" --input "phase4-decision=$evidence_root/phase4-decision-original.json" --phase4-decision-sha256 "$phase4_decision_sha256" --output "$evidence_root/phase4-real-gate.json"
"${phase5[@]}" aggregate --candidate "$evidence_root/release-candidate.json" --input "phase4-real-gate=$evidence_root/phase4-real-gate.json" --input "phase5-real-host=$evidence_root/phase5-real-host-gate.json" --output "$evidence_root/control-aggregate.json"
"${phase5[@]}" decision --candidate "$evidence_root/release-candidate.json" --input "legacy-complete=$legacy_complete" --input "control-aggregate=$evidence_root/control-aggregate.json" --input "regressions=$regressions" --input "publication-actions=$publication_actions" --input "phase4-real-gate=$evidence_root/phase4-real-gate.json" --input "phase5-real-host-gate=$evidence_root/phase5-real-host-gate.json" --output "$evidence_root/phase5-decision.json"

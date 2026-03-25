#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/create_pyside_roadmap_issues.sh [--repo OWNER/REPO]

Description:
  Creates/updates the GitHub planning structure for teczka:
  - Labels
  - Milestones
  - Epic issues
  - Task issues

Notes:
  - Idempotent by issue ID prefix (e.g., RPY-M1-01).
  - Existing issues are not modified; they are detected and reused.
  - Requires: gh CLI authenticated with repo access.
EOF
}

REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required but not found." >&2
  exit 1
fi

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi

if [[ -z "$REPO" ]]; then
  echo "Unable to resolve repository. Pass --repo OWNER/REPO." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run: gh auth login" >&2
  exit 1
fi

echo "Target repository: $REPO"

declare -A ISSUE_NUMBERS=()

ensure_label() {
  local name="$1"
  local color="$2"
  local description="$3"

  if gh label create "$name" --repo "$REPO" --color "$color" --description "$description" >/dev/null 2>&1; then
    echo "label created: $name"
    return
  fi

  gh label edit "$name" --repo "$REPO" --color "$color" --description "$description" >/dev/null
  echo "label updated: $name"
}

find_milestone_number() {
  local title="$1"
  gh api "repos/$REPO/milestones?state=all&per_page=100" --paginate \
    --template '{{range .}}{{printf "%v\t%s\n" .number .title}}{{end}}' \
    | awk -F $'\t' -v t="$title" '$2 == t {print $1; exit}'
}

ensure_milestone() {
  local title="$1"
  local due_on="$2"
  local description="$3"

  local num
  num="$(find_milestone_number "$title" || true)"
  if [[ -n "$num" ]]; then
    echo "milestone exists: $title (#$num)"
    return
  fi

  gh api "repos/$REPO/milestones" -X POST \
    -f title="$title" \
    -f description="$description" \
    -f due_on="$due_on" >/dev/null

  num="$(find_milestone_number "$title" || true)"
  if [[ -z "$num" ]]; then
    echo "Failed creating milestone: $title" >&2
    exit 1
  fi
  echo "milestone created: $title (#$num)"
}

find_issue_number_by_id() {
  local id="$1"
  gh issue list --repo "$REPO" --state all --limit 1000 --search "$id in:title" \
    --json number,title \
    --template '{{range .}}{{printf "%v\t%s\n" .number .title}}{{end}}' \
    | awk -F $'\t' -v id="$id" '$2 ~ ("^" id " ") {print $1; exit}'
}

resolve_issue_ref() {
  local id="$1"
  local num="${ISSUE_NUMBERS[$id]:-}"
  if [[ -z "$num" ]]; then
    num="$(find_issue_number_by_id "$id" || true)"
  fi
  if [[ -n "$num" ]]; then
    echo "#$num ($id)"
  else
    echo "$id"
  fi
}

build_issue_body() {
  local id="$1"
  local milestone="$2"
  local labels_csv="$3"
  local depends_csv="$4"
  local objective="$5"
  local is_epic="$6"

  local phase epic_id epic_ref
  phase="$(echo "$id" | cut -d '-' -f 2)"
  epic_id="RPY-${phase}-E1"

  if [[ "$is_epic" == "true" ]]; then
    epic_ref="This issue is the epic container."
  else
    epic_ref="$(resolve_issue_ref "$epic_id")"
  fi

  local dep_lines
  dep_lines="- None"
  if [[ -n "$depends_csv" ]]; then
    dep_lines=""
    IFS=',' read -r -a dep_ids <<< "$depends_csv"
    for dep_id in "${dep_ids[@]}"; do
      dep_id="${dep_id// /}"
      [[ -z "$dep_id" ]] && continue
      dep_lines+="- $(resolve_issue_ref "$dep_id")"$'\n'
    done
    dep_lines="${dep_lines%$'\n'}"
  fi

  cat <<EOF
Roadmap source: \`docs/RCOMPARE_PYSIDE_GITHUB_PLAN.md\`

## Metadata
- Roadmap ID: \`$id\`
- Milestone: \`$milestone\`
- Labels: \`$labels_csv\`
- Epic: $epic_ref

## Objective
$objective

## Dependencies
$dep_lines

## Definition of Done
1. Implementation merged with tests (or rationale for no tests).
2. No regressions in compare/filters/tabs/profiles/options/sync flows.
3. User-visible behavior documented in release notes or changelog.
EOF
}

ensure_issue() {
  local id="$1"
  local title="$2"
  local milestone="$3"
  local labels_csv="$4"
  local depends_csv="$5"
  local objective="$6"
  local is_epic="$7"

  local existing
  existing="$(find_issue_number_by_id "$id" || true)"
  if [[ -n "$existing" ]]; then
    ISSUE_NUMBERS["$id"]="$existing"
    echo "issue exists: $id (#$existing)"
    return
  fi

  local body
  body="$(build_issue_body "$id" "$milestone" "$labels_csv" "$depends_csv" "$objective" "$is_epic")"

  IFS=',' read -r -a labels_arr <<< "$labels_csv"
  local label_args=()
  for label in "${labels_arr[@]}"; do
    label="${label// /}"
    [[ -z "$label" ]] && continue
    label_args+=(--label "$label")
  done

  local full_title url num
  full_title="$id $title"
  url="$(gh issue create --repo "$REPO" --title "$full_title" --body "$body" --milestone "$milestone" "${label_args[@]}")"
  num="${url##*/}"
  ISSUE_NUMBERS["$id"]="$num"
  echo "issue created: $id (#$num)"
}

echo
echo "== Ensuring labels =="
ensure_label "area:pyside" "1D76DB" "General teczka area"
ensure_label "area:sync" "0E8A16" "Synchronization logic and UI"
ensure_label "area:folder-view" "2D7FF9" "Folder compare tree and interactions"
ensure_label "area:profiles" "5319E7" "Session profiles and persistence"
ensure_label "area:settings" "B60205" "Options/settings dialog and config"
ensure_label "area:viewer-text" "0052CC" "Text comparison viewer"
ensure_label "area:viewer-hex" "0366D6" "Hex comparison viewer"
ensure_label "area:viewer-image" "1B4F72" "Image comparison viewer"
ensure_label "area:performance" "FBCA04" "Performance and scalability"
ensure_label "area:qa" "C2E0C6" "Testing and quality assurance"
ensure_label "type:epic" "5319E7" "Large multi-issue body of work"
ensure_label "type:feature" "0E8A16" "New capability"
ensure_label "type:bug" "D73A4A" "Defect fix"
ensure_label "type:test" "E4E669" "Tests and validation work"
ensure_label "type:docs" "0075CA" "Documentation work"
ensure_label "priority:P0" "B60205" "Highest priority"
ensure_label "priority:P1" "D93F0B" "Important priority"
ensure_label "priority:P2" "FBCA04" "Normal priority"
ensure_label "size:S" "C5DEF5" "Small effort"
ensure_label "size:M" "BFDADC" "Medium effort"
ensure_label "size:L" "BFD4F2" "Large effort"
ensure_label "blocked" "000000" "Blocked by external dependency"

echo
echo "== Ensuring milestones =="
ensure_milestone \
  "M1 - Stabilize Core UX" \
  "2026-02-27T23:59:59Z" \
  "Remove regressions and lock down current teczka feature set."
ensure_milestone \
  "M2 - Sync Engine Execution" \
  "2026-03-20T23:59:59Z" \
  "Move from sync preview to reliable executable synchronization."
ensure_milestone \
  "M3 - Folder UX Productivity" \
  "2026-04-03T23:59:59Z" \
  "Improve high-frequency folder compare workflows."
ensure_milestone \
  "M4 - Viewer Improvements" \
  "2026-04-17T23:59:59Z" \
  "Enhance text, hex, and image compare viewer usability."
ensure_milestone \
  "M5 - Performance and Scale" \
  "2026-05-01T23:59:59Z" \
  "Keep UI responsive on large datasets."
ensure_milestone \
  "M6 - Release Readiness" \
  "2026-05-15T23:59:59Z" \
  "Finalize CI, packaging, and release process."

echo
echo "== Ensuring epic issues =="
ensure_issue \
  "RPY-M1-E1" \
  "Regression hardening for recent UI features" \
  "M1 - Stabilize Core UX" \
  "type:epic,area:pyside,priority:P0,size:L" \
  "" \
  "Harden tabs, profiles, options, and sync-preview workflows and close all critical regressions." \
  "true"

ensure_issue \
  "RPY-M2-E1" \
  "Implement executable folder synchronization" \
  "M2 - Sync Engine Execution" \
  "type:epic,area:sync,priority:P0,size:L" \
  "" \
  "Implement full sync execution with dry-run parity, delete policy, and conflict handling." \
  "true"

ensure_issue \
  "RPY-M3-E1" \
  "High-frequency folder operations usability" \
  "M3 - Folder UX Productivity" \
  "type:epic,area:folder-view,priority:P1,size:L" \
  "" \
  "Improve speed and safety of frequent folder-view operations." \
  "true"

ensure_issue \
  "RPY-M4-E1" \
  "Improve compare viewers for text, hex, and image" \
  "M4 - Viewer Improvements" \
  "type:epic,area:pyside,priority:P1,size:L" \
  "" \
  "Improve navigation and usability across all compare viewers." \
  "true"

ensure_issue \
  "RPY-M5-E1" \
  "Handle large trees with responsive UI" \
  "M5 - Performance and Scale" \
  "type:epic,area:performance,priority:P1,size:L" \
  "" \
  "Improve filtering, searching, and rendering responsiveness for very large comparisons." \
  "true"

ensure_issue \
  "RPY-M6-E1" \
  "Ship-quality release process" \
  "M6 - Release Readiness" \
  "type:epic,area:qa,priority:P0,size:L" \
  "" \
  "Define and enforce release gates for testing, CI, packaging, and docs." \
  "true"

echo
echo "== Ensuring task issues =="

# M1
ensure_issue "RPY-M1-01" "Add smoke test matrix for tabs/profiles/options/sync-preview" \
  "M1 - Stabilize Core UX" \
  "type:test,area:qa,priority:P0,size:M" \
  "" \
  "Add a smoke test matrix covering critical pyside workflows and failure states." \
  "false"
ensure_issue "RPY-M1-02" "Fix profile dialog load/save contract mismatches" \
  "M1 - Stabilize Core UX" \
  "type:bug,area:profiles,priority:P0,size:S" \
  "RPY-M1-01" \
  "Resolve profile dialog API/behavior mismatches and ensure reliable load/save paths." \
  "false"
ensure_issue "RPY-M1-03" "Ensure session switching cancels running comparison safely" \
  "M1 - Stabilize Core UX" \
  "type:bug,area:pyside,priority:P0,size:S" \
  "RPY-M1-01" \
  "Guarantee safe cancellation and state reset when changing active session during compare." \
  "false"
ensure_issue "RPY-M1-04" "Add end-user error messages for invalid path/config states" \
  "M1 - Stabilize Core UX" \
  "type:feature,area:settings,priority:P1,size:S" \
  "" \
  "Improve user-facing diagnostics for invalid path and configuration scenarios." \
  "false"
ensure_issue "RPY-M1-05" "Add QA checklist doc for manual pre-release verification" \
  "M1 - Stabilize Core UX" \
  "type:docs,area:qa,priority:P1,size:S" \
  "RPY-M1-01" \
  "Create a concise manual QA checklist used before milestone closure and release." \
  "false"

# M2
ensure_issue "RPY-M2-01" "Implement sync planner service from ScanReport + options" \
  "M2 - Sync Engine Execution" \
  "type:feature,area:sync,priority:P0,size:M" \
  "" \
  "Create a deterministic sync planning layer from compare results and selected options." \
  "false"
ensure_issue "RPY-M2-02" "Implement sync executor for copy/update actions" \
  "M2 - Sync Engine Execution" \
  "type:feature,area:sync,priority:P0,size:L" \
  "RPY-M2-01" \
  "Execute planned copy/update sync operations safely and with clear progress reporting." \
  "false"
ensure_issue "RPY-M2-03" "Implement delete strategy abstraction (trash/permanent)" \
  "M2 - Sync Engine Execution" \
  "type:feature,area:sync,priority:P0,size:M" \
  "RPY-M2-01" \
  "Implement configurable deletion strategy with trash and permanent-delete modes." \
  "false"
ensure_issue "RPY-M2-04" "Conflict handling policy UI for bidirectional mode" \
  "M2 - Sync Engine Execution" \
  "type:feature,area:sync,priority:P1,size:M" \
  "RPY-M2-01" \
  "Expose clear conflict policy controls for bidirectional synchronization." \
  "false"
ensure_issue "RPY-M2-05" "Wire SyncDialog Execute to planner+executor with progress/cancel" \
  "M2 - Sync Engine Execution" \
  "type:feature,area:sync,priority:P0,size:L" \
  "RPY-M2-02,RPY-M2-03" \
  "Integrate sync planning and execution into SyncDialog with robust progress and cancel behavior." \
  "false"
ensure_issue "RPY-M2-06" "Add sync unit tests for all DiffStatus combinations" \
  "M2 - Sync Engine Execution" \
  "type:test,area:qa,priority:P0,size:M" \
  "RPY-M2-02,RPY-M2-03" \
  "Add unit coverage for sync planning and execution across all diff status permutations." \
  "false"
ensure_issue "RPY-M2-07" "Add sync integration tests validating preview vs execution parity" \
  "M2 - Sync Engine Execution" \
  "type:test,area:qa,priority:P0,size:M" \
  "RPY-M2-05" \
  "Validate that sync preview matches actual executed operations under all supported modes." \
  "false"

# M3
ensure_issue "RPY-M3-01" "Persist LH/RH column widths per user" \
  "M3 - Folder UX Productivity" \
  "type:feature,area:folder-view,priority:P1,size:M" \
  "" \
  "Persist and restore per-user folder view column widths for both LH and RH trees." \
  "false"
ensure_issue "RPY-M3-02" "Add keyboard shortcuts for expand/collapse/copy/open actions" \
  "M3 - Folder UX Productivity" \
  "type:feature,area:folder-view,priority:P1,size:S" \
  "" \
  "Add and document keyboard shortcuts for common folder view actions." \
  "false"
ensure_issue "RPY-M3-03" "Add context menu actions: reveal in file manager, copy path" \
  "M3 - Folder UX Productivity" \
  "type:feature,area:folder-view,priority:P1,size:S" \
  "" \
  "Extend folder view context menu with path and file-manager convenience actions." \
  "false"
ensure_issue "RPY-M3-04" "Add non-blocking progress UI for long copy operations" \
  "M3 - Folder UX Productivity" \
  "type:feature,area:folder-view,priority:P1,size:M" \
  "" \
  "Provide non-blocking progress and cancellation UX for long-running copy operations." \
  "false"
ensure_issue "RPY-M3-05" "Add undo-friendly safeguards for destructive actions" \
  "M3 - Folder UX Productivity" \
  "type:feature,area:folder-view,priority:P1,size:M" \
  "RPY-M3-04" \
  "Add user safeguards that reduce accidental destructive operations." \
  "false"

# M4
ensure_issue "RPY-M4-01" "Text view: add next/previous diff navigation and markers" \
  "M4 - Viewer Improvements" \
  "type:feature,area:viewer-text,priority:P1,size:M" \
  "" \
  "Add explicit diff navigation and visual markers in text compare view." \
  "false"
ensure_issue "RPY-M4-02" "Text view: improve synced scrolling and cursor lock options" \
  "M4 - Viewer Improvements" \
  "type:feature,area:viewer-text,priority:P1,size:S" \
  "" \
  "Improve synchronized scrolling behavior and provide cursor lock options." \
  "false"
ensure_issue "RPY-M4-03" "Hex view: jump to first mismatch and mismatch count" \
  "M4 - Viewer Improvements" \
  "type:feature,area:viewer-hex,priority:P1,size:M" \
  "" \
  "Add mismatch summary and quick jump helpers to hex compare view." \
  "false"
ensure_issue "RPY-M4-04" "Image view: add fit/original/linked zoom modes" \
  "M4 - Viewer Improvements" \
  "type:feature,area:viewer-image,priority:P1,size:M" \
  "" \
  "Add explicit fit/original/linked zoom modes for image compare workflows." \
  "false"
ensure_issue "RPY-M4-05" "Viewer QA tests and keyboard shortcut consistency pass" \
  "M4 - Viewer Improvements" \
  "type:test,area:qa,priority:P1,size:S" \
  "" \
  "Add QA and consistency checks across text/hex/image viewers and shortcuts." \
  "false"

# M5
ensure_issue "RPY-M5-01" "Add benchmark harness for 10k/50k/100k entry trees" \
  "M5 - Performance and Scale" \
  "type:test,area:performance,priority:P1,size:M" \
  "" \
  "Create reproducible benchmark scenarios for large comparison trees." \
  "false"
ensure_issue "RPY-M5-02" "Optimize filter/search path for large datasets" \
  "M5 - Performance and Scale" \
  "type:feature,area:performance,priority:P1,size:L" \
  "RPY-M5-01" \
  "Optimize filtering and search logic for very large datasets." \
  "false"
ensure_issue "RPY-M5-03" "Lazy node expansion and deferred population strategy" \
  "M5 - Performance and Scale" \
  "type:feature,area:performance,priority:P1,size:L" \
  "" \
  "Implement lazy/deferred tree loading to reduce UI overhead on large scans." \
  "false"
ensure_issue "RPY-M5-04" "Add cancellation checkpoints in expensive UI operations" \
  "M5 - Performance and Scale" \
  "type:feature,area:performance,priority:P1,size:M" \
  "" \
  "Add cancellation checkpoints in expensive UI and model operations." \
  "false"
ensure_issue "RPY-M5-05" "Publish performance report in docs" \
  "M5 - Performance and Scale" \
  "type:docs,area:performance,priority:P2,size:S" \
  "RPY-M5-02,RPY-M5-03" \
  "Document benchmark outcomes and tuning decisions for large-scale comparisons." \
  "false"

# M6
ensure_issue "RPY-M6-01" "Add/expand CI jobs for teczka test gates" \
  "M6 - Release Readiness" \
  "type:feature,area:qa,priority:P0,size:M" \
  "" \
  "Add or expand CI jobs that gate pyside quality and regressions." \
  "false"
ensure_issue "RPY-M6-02" "Add UI smoke tests for startup/compare/sync/profile/options" \
  "M6 - Release Readiness" \
  "type:test,area:qa,priority:P0,size:M" \
  "" \
  "Add UI smoke tests for critical startup and primary user flows." \
  "false"
ensure_issue "RPY-M6-03" "Add packaging scripts and artifact naming conventions" \
  "M6 - Release Readiness" \
  "type:feature,area:qa,priority:P1,size:M" \
  "" \
  "Standardize packaging scripts and artifact naming for supported platforms." \
  "false"
ensure_issue "RPY-M6-04" "Create release checklist and changelog workflow doc" \
  "M6 - Release Readiness" \
  "type:docs,area:qa,priority:P1,size:S" \
  "" \
  "Create release checklist and changelog workflow documentation." \
  "false"
ensure_issue "RPY-M6-05" "Release candidate bug bash and closure criteria" \
  "M6 - Release Readiness" \
  "type:test,area:qa,priority:P0,size:S" \
  "" \
  "Run RC bug-bash process and enforce closure criteria before release." \
  "false"

echo
echo "Done."
echo "Created or reused roadmap issues for teczka in $REPO."

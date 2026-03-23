"""
Evaluation report generation.

Console summary, CSV export, HTML export, and comparison reporting.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import SignEvaluation


# ---------------------------------------------------------------------------
# Standard evaluation reports
# ---------------------------------------------------------------------------

def print_console_summary(evaluations: list[SignEvaluation]) -> None:
    """Print a compact evaluation summary to stdout.

    Shows total/pass/fail counts, then a table of failed signs with their errors.

    Args:
        evaluations: List of SignEvaluation results.
    """
    total = len(evaluations)
    passed = sum(1 for e in evaluations if e.passed)
    failed = total - passed
    warned = sum(1 for e in evaluations if e.warnings)

    print(f"\n{'=' * 60}")
    print(f"  FK Evaluation Summary")
    print(f"{'=' * 60}")
    print(f"  Total signs:  {total}")
    print(f"  Passed:       {passed}")
    print(f"  Failed:       {failed}")
    print(f"  With warnings:{warned}")
    print(f"{'=' * 60}")

    failed_evaluations = [e for e in evaluations if not e.passed]
    if not failed_evaluations:
        print("  All signs passed!")
        print()
        return

    print(f"\n  Failed signs:")
    print(f"  {'-' * 56}")
    for evaluation in failed_evaluations:
        error_summary = "; ".join(issue.message for issue in evaluation.errors[:3])
        if len(evaluation.errors) > 3:
            error_summary += f" (+{len(evaluation.errors) - 3} more)"
        print(f"  {evaluation.token:<20} {error_summary}")
    print()


def export_csv(evaluations: list[SignEvaluation], filepath: str) -> None:
    """Export evaluation results to a CSV file.

    One row per sign with columns: token, passed, num_errors, num_warnings,
    max_angular_velocity, duration, num_keyframes, arms_used, error_summary.

    Args:
        evaluations: List of SignEvaluation results.
        filepath: Output CSV file path.
    """
    fieldnames = [
        "token", "passed", "num_errors", "num_warnings",
        "max_angular_velocity", "duration", "num_keyframes",
        "arms_used", "error_summary",
    ]

    path = Path(filepath)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for evaluation in evaluations:
            error_messages = "; ".join(issue.message for issue in evaluation.errors)
            arms_label = _arms_value_to_label(evaluation.metrics.get("arms_used", 0.0))

            writer.writerow({
                "token": evaluation.token,
                "passed": evaluation.passed,
                "num_errors": int(evaluation.metrics.get("num_errors", 0)),
                "num_warnings": int(evaluation.metrics.get("num_warnings", 0)),
                "max_angular_velocity": f"{evaluation.metrics.get('max_angular_velocity', 0):.1f}",
                "duration": evaluation.metrics.get("duration", 0),
                "num_keyframes": int(evaluation.metrics.get("num_keyframes", 0)),
                "arms_used": arms_label,
                "error_summary": error_messages,
            })

    print(f"  CSV report saved to: {filepath}")


def export_html(evaluations: list[SignEvaluation], filepath: str) -> None:
    """Export evaluation results to a self-contained HTML report.

    Professional layout with sortable table, color-coded rows, summary stats,
    and common failure mode breakdown. No external dependencies.

    Args:
        evaluations: List of SignEvaluation results.
        filepath: Output HTML file path.
    """
    total = len(evaluations)
    passed = sum(1 for e in evaluations if e.passed)
    failed = total - passed
    warned = sum(1 for e in evaluations if e.warnings and e.passed)

    failure_modes = _count_failure_modes(evaluations)
    table_rows = _build_html_table_rows(evaluations)
    failure_mode_html = _build_failure_mode_html(failure_modes)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = _HTML_TEMPLATE.format(
        timestamp=timestamp,
        total=total,
        passed=passed,
        failed=failed,
        warned=warned,
        table_rows=table_rows,
        failure_modes=failure_mode_html,
    )

    path = Path(filepath)
    path.write_text(html, encoding="utf-8")
    print(f"  HTML report saved to: {filepath}")


def export_report(evaluations: list[SignEvaluation], filepath: str) -> None:
    """Export evaluation results, auto-detecting format from file extension.

    Args:
        evaluations: List of SignEvaluation results.
        filepath: Output file path (.csv or .html).
    """
    if filepath.endswith(".html"):
        export_html(evaluations, filepath)
    else:
        export_csv(evaluations, filepath)


# ---------------------------------------------------------------------------
# Comparison reports (Phase 6)
# ---------------------------------------------------------------------------

def print_comparison_summary(comparisons: list[dict]) -> None:
    """Print a comparison summary between AI and reference signs.

    Shows match counts, mean MAE, pass rates, and worst-accuracy signs.

    Args:
        comparisons: List of comparison dicts from compare_batch().
    """
    total = len(comparisons)
    if total == 0:
        print("\n  No matched signs to compare.")
        return

    mean_mae = sum(c["joint_angle_mae"] for c in comparisons) / total
    ai_passed = sum(1 for c in comparisons if c["ai_evaluation"].passed)
    ref_passed = sum(1 for c in comparisons if c["ref_evaluation"].passed)
    both_passed = sum(1 for c in comparisons if c["both_passed"])
    arm_agreed = sum(1 for c in comparisons if c["arm_agreement"])

    print(f"\n{'=' * 60}")
    print(f"  AI vs Reference Comparison Summary")
    print(f"{'=' * 60}")
    print(f"  Matched signs:      {total}")
    print(f"  Mean joint MAE:     {mean_mae:.4f} rad ({mean_mae * 57.2958:.2f} deg)")
    print(f"  AI passed:          {ai_passed}/{total}")
    print(f"  Reference passed:   {ref_passed}/{total}")
    print(f"  Both passed:        {both_passed}/{total}")
    print(f"  Arm agreement:      {arm_agreed}/{total}")
    print(f"{'=' * 60}")

    worst = sorted(comparisons, key=lambda c: c["joint_angle_mae"], reverse=True)[:5]
    if worst:
        print(f"\n  Highest MAE (worst accuracy):")
        print(f"  {'-' * 56}")
        for comparison in worst:
            mae = comparison["joint_angle_mae"]
            print(f"  {comparison['token']:<20} MAE={mae:.4f} rad ({mae * 57.2958:.2f} deg)")
    print()


def export_comparison_csv(comparisons: list[dict], filepath: str) -> None:
    """Export comparison results to a CSV file.

    One row per matched token with all comparison metrics.

    Args:
        comparisons: List of comparison dicts from compare_batch().
        filepath: Output CSV file path.
    """
    fieldnames = [
        "token", "ai_passed", "ref_passed", "both_passed",
        "joint_angle_mae", "duration_diff", "keyframe_count_diff",
        "arm_agreement", "ai_errors", "ref_errors",
    ]

    path = Path(filepath)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for comparison in comparisons:
            ai_error_summary = "; ".join(
                i.message for i in comparison["ai_evaluation"].errors[:3]
            )
            ref_error_summary = "; ".join(
                i.message for i in comparison["ref_evaluation"].errors[:3]
            )

            writer.writerow({
                "token": comparison["token"],
                "ai_passed": comparison["ai_evaluation"].passed,
                "ref_passed": comparison["ref_evaluation"].passed,
                "both_passed": comparison["both_passed"],
                "joint_angle_mae": f"{comparison['joint_angle_mae']:.4f}",
                "duration_diff": f"{comparison['duration_diff']:.2f}",
                "keyframe_count_diff": comparison["keyframe_count_diff"],
                "arm_agreement": comparison["arm_agreement"],
                "ai_errors": ai_error_summary,
                "ref_errors": ref_error_summary,
            })

    print(f"  Comparison CSV saved to: {filepath}")


def export_comparison_report(comparisons: list[dict], filepath: str) -> None:
    """Export comparison results, auto-detecting format from extension.

    Args:
        comparisons: List of comparison dicts.
        filepath: Output file path (.csv or .html).
    """
    if filepath.endswith(".html"):
        _export_comparison_html(comparisons, filepath)
    else:
        export_comparison_csv(comparisons, filepath)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _arms_value_to_label(arms_value: float) -> str:
    """Convert numeric arms_used metric back to a human-readable label.

    Args:
        arms_value: 1.0 = left, 2.0 = right, 3.0 = both.

    Returns:
        String label.
    """
    mapping = {1.0: "left", 2.0: "right", 3.0: "both"}
    return mapping.get(arms_value, "unknown")


def _count_failure_modes(evaluations: list[SignEvaluation]) -> dict[str, int]:
    """Count occurrences of each failure metric across all evaluations.

    Args:
        evaluations: List of evaluation results.

    Returns:
        Dict mapping metric name to count, sorted descending.
    """
    counts: dict[str, int] = {}
    for evaluation in evaluations:
        for issue in evaluation.errors:
            counts[issue.metric] = counts.get(issue.metric, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def _build_html_table_rows(evaluations: list[SignEvaluation]) -> str:
    """Build HTML table row markup for all evaluations.

    Args:
        evaluations: List of evaluation results.

    Returns:
        Concatenated HTML <tr> elements.
    """
    rows: list[str] = []
    for evaluation in evaluations:
        row_class = _html_row_class(evaluation)
        badge = _html_badge(evaluation)
        errors = len(evaluation.errors)
        warnings = len(evaluation.warnings)
        velocity = evaluation.metrics.get("max_angular_velocity", 0)
        duration = evaluation.metrics.get("duration", 0)
        keyframes = int(evaluation.metrics.get("num_keyframes", 0))
        arms = _arms_value_to_label(evaluation.metrics.get("arms_used", 0.0))
        error_text = "; ".join(i.message for i in evaluation.errors[:3])
        if len(evaluation.errors) > 3:
            error_text += f" (+{len(evaluation.errors) - 3} more)"

        rows.append(
            f'<tr class="{row_class}">'
            f"<td>{evaluation.token}</td>"
            f"<td>{badge}</td>"
            f"<td>{errors}</td>"
            f"<td>{warnings}</td>"
            f"<td>{velocity:.1f}</td>"
            f"<td>{duration}</td>"
            f"<td>{keyframes}</td>"
            f"<td>{arms}</td>"
            f"<td>{error_text}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _html_row_class(evaluation: SignEvaluation) -> str:
    """Determine CSS class for an evaluation row.

    Args:
        evaluation: The evaluation result.

    Returns:
        CSS class name string.
    """
    if not evaluation.passed:
        return "row-fail"
    if evaluation.warnings:
        return "row-warn"
    return "row-pass"


def _html_badge(evaluation: SignEvaluation) -> str:
    """Generate a colored pass/fail badge.

    Args:
        evaluation: The evaluation result.

    Returns:
        HTML span element.
    """
    if not evaluation.passed:
        return '<span class="badge badge-fail">FAIL</span>'
    if evaluation.warnings:
        return '<span class="badge badge-warn">WARN</span>'
    return '<span class="badge badge-pass">PASS</span>'


def _build_failure_mode_html(failure_modes: dict[str, int]) -> str:
    """Build HTML list of most common failure modes.

    Args:
        failure_modes: Dict mapping metric name to count.

    Returns:
        HTML markup string.
    """
    if not failure_modes:
        return "<p>No failures detected.</p>"
    items = "".join(
        f"<li><strong>{metric}</strong>: {count} occurrence(s)</li>"
        for metric, count in failure_modes.items()
    )
    return f"<ul>{items}</ul>"


def _export_comparison_html(comparisons: list[dict], filepath: str) -> None:
    """Export comparison results as a self-contained HTML report.

    Args:
        comparisons: List of comparison dicts.
        filepath: Output HTML file path.
    """
    total = len(comparisons)
    mean_mae = sum(c["joint_angle_mae"] for c in comparisons) / total if total else 0
    both_passed = sum(1 for c in comparisons if c["both_passed"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    comp_rows = _build_comparison_table_rows(comparisons)

    html = _COMPARISON_HTML_TEMPLATE.format(
        timestamp=timestamp,
        total=total,
        mean_mae=f"{mean_mae:.4f}",
        mean_mae_deg=f"{mean_mae * 57.2958:.2f}",
        both_passed=both_passed,
        table_rows=comp_rows,
    )

    Path(filepath).write_text(html, encoding="utf-8")
    print(f"  Comparison HTML report saved to: {filepath}")


def _build_comparison_table_rows(comparisons: list[dict]) -> str:
    """Build HTML table rows for comparison report.

    Args:
        comparisons: List of comparison dicts.

    Returns:
        Concatenated HTML <tr> elements.
    """
    rows: list[str] = []
    for comp in comparisons:
        row_class = "row-pass" if comp["both_passed"] else "row-fail"
        ai_badge = "PASS" if comp["ai_evaluation"].passed else "FAIL"
        ref_badge = "PASS" if comp["ref_evaluation"].passed else "FAIL"
        mae = comp["joint_angle_mae"]

        rows.append(
            f'<tr class="{row_class}">'
            f"<td>{comp['token']}</td>"
            f"<td>{ai_badge}</td>"
            f"<td>{ref_badge}</td>"
            f"<td>{mae:.4f}</td>"
            f"<td>{mae * 57.2958:.2f}</td>"
            f"<td>{comp['duration_diff']:.2f}</td>"
            f"<td>{comp['keyframe_count_diff']}</td>"
            f"<td>{'Yes' if comp['arm_agreement'] else 'No'}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# HTML Templates
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FK Evaluation Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 2rem; color: #333; }}
  h1 {{ color: #1a1a2e; }}
  .meta {{ color: #666; margin-bottom: 1.5rem; }}
  .summary {{ display: flex; gap: 1rem; margin-bottom: 2rem; }}
  .summary-card {{ padding: 1rem 1.5rem; border-radius: 8px; font-size: 1.1rem; font-weight: 600; }}
  .card-pass {{ background: #d4edda; color: #155724; }}
  .card-fail {{ background: #f8d7da; color: #721c24; }}
  .card-warn {{ background: #fff3cd; color: #856404; }}
  .card-total {{ background: #d1ecf1; color: #0c5460; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
  th, td {{ padding: 0.5rem 0.75rem; border: 1px solid #dee2e6; text-align: left; font-size: 0.9rem; }}
  th {{ background: #343a40; color: white; cursor: pointer; user-select: none; }}
  th:hover {{ background: #495057; }}
  .row-pass {{ background: #f0fff0; }}
  .row-fail {{ background: #fff0f0; }}
  .row-warn {{ background: #fffff0; }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700; }}
  .badge-pass {{ background: #28a745; color: white; }}
  .badge-fail {{ background: #dc3545; color: white; }}
  .badge-warn {{ background: #ffc107; color: #333; }}
  h2 {{ margin-top: 2rem; color: #1a1a2e; }}
</style>
</head>
<body>
<h1>FK Evaluation Report</h1>
<p class="meta">Generated: {timestamp} &mdash; {total} sign(s) evaluated</p>
<div class="summary">
  <div class="summary-card card-total">Total: {total}</div>
  <div class="summary-card card-pass">Passed: {passed}</div>
  <div class="summary-card card-fail">Failed: {failed}</div>
  <div class="summary-card card-warn">Warnings: {warned}</div>
</div>
<table id="results">
<thead>
<tr>
  <th onclick="sortTable(0)">Token</th>
  <th onclick="sortTable(1)">Status</th>
  <th onclick="sortTable(2)">Errors</th>
  <th onclick="sortTable(3)">Warnings</th>
  <th onclick="sortTable(4)">Max Vel (deg/s)</th>
  <th onclick="sortTable(5)">Duration (s)</th>
  <th onclick="sortTable(6)">Keyframes</th>
  <th onclick="sortTable(7)">Arms</th>
  <th>Error Summary</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>
<h2>Common Failure Modes</h2>
{failure_modes}
<script>
let sortDir = {{}};
function sortTable(col) {{
  const table = document.getElementById("results");
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const dir = sortDir[col] = !(sortDir[col] || false);
  rows.sort((a, b) => {{
    let va = a.cells[col].textContent.trim();
    let vb = b.cells[col].textContent.trim();
    let na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return dir ? na - nb : nb - na;
    return dir ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</body>
</html>"""

_COMPARISON_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AI vs Reference Comparison Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 2rem; color: #333; }}
  h1 {{ color: #1a1a2e; }}
  .meta {{ color: #666; margin-bottom: 1.5rem; }}
  .summary {{ display: flex; gap: 1rem; margin-bottom: 2rem; }}
  .summary-card {{ padding: 1rem 1.5rem; border-radius: 8px; font-size: 1.1rem; font-weight: 600; }}
  .card-total {{ background: #d1ecf1; color: #0c5460; }}
  .card-pass {{ background: #d4edda; color: #155724; }}
  .card-mae {{ background: #e2e3f1; color: #383d6e; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: 0.5rem 0.75rem; border: 1px solid #dee2e6; text-align: left; font-size: 0.9rem; }}
  th {{ background: #343a40; color: white; cursor: pointer; user-select: none; }}
  th:hover {{ background: #495057; }}
  .row-pass {{ background: #f0fff0; }}
  .row-fail {{ background: #fff0f0; }}
</style>
</head>
<body>
<h1>AI vs Reference Comparison Report</h1>
<p class="meta">Generated: {timestamp} &mdash; {total} sign(s) compared</p>
<div class="summary">
  <div class="summary-card card-total">Matched: {total}</div>
  <div class="summary-card card-pass">Both Passed: {both_passed}</div>
  <div class="summary-card card-mae">Mean MAE: {mean_mae} rad ({mean_mae_deg} deg)</div>
</div>
<table id="results">
<thead>
<tr>
  <th onclick="sortTable(0)">Token</th>
  <th onclick="sortTable(1)">AI Status</th>
  <th onclick="sortTable(2)">Ref Status</th>
  <th onclick="sortTable(3)">MAE (rad)</th>
  <th onclick="sortTable(4)">MAE (deg)</th>
  <th onclick="sortTable(5)">Duration Diff</th>
  <th onclick="sortTable(6)">KF Count Diff</th>
  <th onclick="sortTable(7)">Arm Agreement</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>
<script>
let sortDir = {{}};
function sortTable(col) {{
  const table = document.getElementById("results");
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const dir = sortDir[col] = !(sortDir[col] || false);
  rows.sort((a, b) => {{
    let va = a.cells[col].textContent.trim();
    let vb = b.cells[col].textContent.trim();
    let na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return dir ? na - nb : nb - na;
    return dir ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</body>
</html>"""

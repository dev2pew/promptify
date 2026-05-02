from __future__ import annotations

import json
import sys
from collections import defaultdict
from json import JSONDecodeError
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlparse


def _summary_from_report(report: dict[str, Any]) -> dict[str, int | float]:
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        return {
            "filesAnalyzed": 0,
            "errorCount": 0,
            "warningCount": 0,
            "informationCount": 0,
            "timeInSec": 0.0,
        }
    return {
        "filesAnalyzed": int(summary.get("filesAnalyzed", 0)),
        "errorCount": int(summary.get("errorCount", 0)),
        "warningCount": int(summary.get("warningCount", 0)),
        "informationCount": int(summary.get("informationCount", 0)),
        "timeInSec": float(summary.get("timeInSec", 0.0)),
    }


def _diagnostic_issue_type(diagnostic: dict[str, Any]) -> str:
    rule = diagnostic.get("rule")
    if isinstance(rule, str) and rule:
        return rule
    severity = diagnostic.get("severity")
    if isinstance(severity, str) and severity:
        return severity
    return "unknown"


def _diagnostic_severity(diagnostic: dict[str, Any]) -> str:
    severity = diagnostic.get("severity")
    if isinstance(severity, str) and severity:
        return severity
    return "unknown"


def _file_uri_to_path(path_value: str) -> str:
    if not path_value.startswith("file:"):
        return path_value

    parsed = urlparse(path_value)
    path = unquote(parsed.path)

    if parsed.netloc:
        return f"//{parsed.netloc}{path}"

    if len(path) >= 4 and path[0] == "/" and path[2] == ":":
        return path[1:]

    return path


def _normalize_compare_path(path_value: str) -> str:
    normalized = _file_uri_to_path(path_value).replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        return normalized.lower()
    return normalized


def _is_repo_root(path: Path) -> bool:
    return (path / "src").is_dir() and (path / "tests").is_dir()


def _resolve_repo_root(repo_root_value: str) -> str:
    requested = Path(repo_root_value).expanduser()

    candidates = [
        requested,
        requested.parent,
        Path.cwd(),
        Path.cwd().parent,
    ]

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if _is_repo_root(resolved):
            return str(resolved)

    try:
        return str(requested.resolve())
    except OSError:
        return str(requested)


def _repo_root_compare_prefixes(repo_root: str) -> tuple[str, ...]:
    prefixes = {_normalize_compare_path(repo_root)}
    normalized = _normalize_compare_path(repo_root)
    parts = normalized.split("/")
    if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1:
        drive = parts[2].lower()
        prefixes.add(f"{drive}:/" + "/".join(parts[3:]))
    elif len(normalized) >= 3 and normalized[1:3] == ":/":
        drive = normalized[0].lower()
        tail = normalized[3:]
        prefixes.add(f"/mnt/{drive}/{tail}" if tail else f"/mnt/{drive}")
    return tuple(sorted(prefixes, key=len, reverse=True))


def _diagnostic_file(diagnostic: dict[str, Any], repo_root: str) -> str | None:
    file_value = diagnostic.get("file")
    if not isinstance(file_value, str) or not file_value:
        return None

    decoded_file_value = _file_uri_to_path(file_value)
    file_path = Path(decoded_file_value)

    try:
        return file_path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except (OSError, ValueError):
        pass

    normalized_file = _normalize_compare_path(decoded_file_value)
    for prefix in _repo_root_compare_prefixes(repo_root):
        if normalized_file == prefix:
            return "."
        if normalized_file.startswith(prefix + "/"):
            return normalized_file[len(prefix) + 1 :]

    if len(decoded_file_value) >= 2 and decoded_file_value[1] == ":":
        return PureWindowsPath(decoded_file_value).as_posix()
    return file_path.as_posix()


def _build_issues(
    diagnostics: list[dict[str, Any]],
    repo_root: str,
) -> list[dict[str, Any]]:
    files_by_issue: dict[tuple[str, str], set[str]] = defaultdict(set)
    counts_by_issue: dict[tuple[str, str], int] = defaultdict(int)

    for diagnostic in diagnostics:
        issue_type = _diagnostic_issue_type(diagnostic)
        severity = _diagnostic_severity(diagnostic)
        issue_key = (issue_type, severity)

        counts_by_issue[issue_key] += 1

        file_path = _diagnostic_file(diagnostic, repo_root)
        if file_path is not None:
            files_by_issue[issue_key].add(file_path)

    return [
        {
            "type": issue_type,
            "severity": severity,
            "diagnosticCount": counts_by_issue[(issue_type, severity)],
            "files": sorted(files_by_issue[(issue_type, severity)]),
        }
        for issue_type, severity in sorted(
            counts_by_issue,
            key=lambda key: (-counts_by_issue[key], key[0], key[1]),
        )
    ]


def _load_report(raw_path: Path) -> dict[str, Any]:
    try:
        raw_text = raw_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"could not read basedpyright JSON report: {raw_path}"
        ) from exc

    if not raw_text.strip():
        raise ValueError(
            "basedpyright did not produce JSON output. "
            "This usually means basedpyright failed before writing --outputjson. "
            "Check that the wrapper script runs from the project root containing src/ and tests/."
        )

    try:
        report = json.loads(raw_text)
    except JSONDecodeError as exc:
        preview = raw_text[:500].replace("\r", "\\r").replace("\n", "\\n")
        raise ValueError(
            "basedpyright produced invalid JSON output "
            f"at line {exc.lineno}, column {exc.colno}: {exc.msg}. "
            f"Output preview: {preview!r}"
        ) from exc

    if not isinstance(report, dict):
        raise ValueError("basedpyright JSON output must be an object.")

    return report


def _write_compact_report(
    output_path: Path,
    summary: dict[str, int | float],
    issues: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    compact_report = {"summary": summary, "issues": issues}
    output_path.write_text(
        json.dumps(compact_report, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _print_console_summary(
    summary: dict[str, int | float],
    issues: list[dict[str, Any]],
) -> None:
    print(
        "summary:"
        f" files={summary['filesAnalyzed']}"
        f" errors={summary['errorCount']}"
        f" warnings={summary['warningCount']}"
        f" info={summary['informationCount']}"
        f" time={summary['timeInSec']:.3f}s"
    )

    if not issues:
        print("no issues.")
        return

    for index, issue in enumerate(issues, start=1):
        file_count = len(issue["files"])
        print(
            f"{index}. `{issue['type']}`"
            f" ({issue['severity']}, {issue['diagnosticCount']} diagnostics, {file_count} files)"
        )

        if file_count == 0:
            print("- <no-file-diagnostic>.")
            continue

        for file_index, file_path in enumerate(issue["files"], start=1):
            suffix = "." if file_index == file_count else ";"
            print(f"- {file_path}{suffix}")


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        print(
            f"usage: {Path(sys.argv[0]).name} <raw-report-path> <output-path> [repo-root]",
            file=sys.stderr,
        )
        return 2

    raw_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    repo_root = _resolve_repo_root(
        sys.argv[3] if len(sys.argv) >= 4 else str(Path.cwd())
    )

    try:
        report = _load_report(raw_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summary = _summary_from_report(report)

    diagnostics = report.get("generalDiagnostics", [])
    if not isinstance(diagnostics, list):
        diagnostics = []

    issues = _build_issues(
        [diagnostic for diagnostic in diagnostics if isinstance(diagnostic, dict)],
        repo_root,
    )

    try:
        _write_compact_report(output_path, summary, issues)
    except OSError as exc:
        print(
            f"error: could not write compact report: {output_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    _print_console_summary(summary, issues)
    return int(summary["errorCount"])


if __name__ == "__main__":
    raise SystemExit(main())

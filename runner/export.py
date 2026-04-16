import pandas as pd
from pathlib import Path

def export_results(states, file_path="outputs/results.xlsx"):
    rows = []

    for state in states:
        for tc in (state.test_cases or []):
            evidence = " | ".join(
                [
                    f"{ref.filename}::{(ref.section or '').strip()}::{ref.line_snippet}"
                    for ref in tc.evidence_refs
                ]
            )
            steps_text = " | ".join([f"{step.index}. {step.action} => {step.expected_result}" for step in tc.steps])
            rows.append({
                "feature_id": state.feature_id,
                "module": state.module,
                "test_case_id": tc.id,
                "description": tc.description,
                "pre_action": tc.pre_action,
                "post_action": tc.post_action,
                "steps": steps_text,
                "expected_observables": " | ".join(tc.expected_observables),
                "tool_commands": " | ".join(tc.tool_commands),
                "log_assertions": " | ".join(tc.log_assertions),
                "evidence_refs": evidence,
            })

    df = pd.DataFrame(rows)
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(file_path, index=False)


def export_markdown_report(states, file_path="test/qa_test_report.md"):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# EV Charge Publisher (ECPU) - Test Case Document",
        "",
        "**Project:** SDLC Auto-Generated",
        "**Service:** Requirement-grounded QA Pipeline",
        "**Test Suite:** Generated from `data/` + `doc/` only",
        "",
        "---",
        "",
    ]

    section_index = 1

    for state in states:
        test_cases = state.test_cases or []
        if not test_cases:
            lines.append(f"## Feature {state.feature_id} - Clarification Required")
            lines.append("")
            lines.append(f"**Requirement ID:** {state.feature_id}")
            if state.review_feedback:
                lines.append("")
                lines.append(f"**Review Feedback**  ")
                lines.append(f"{state.review_feedback}")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        for tc in test_cases:
            lines.append(f"## 4.5.1.1.8.2.{section_index} {tc.id}")
            lines.append("")
            lines.append(f"**Requirement ID:** {state.feature_id}")
            lines.append("")
            lines.append("**Pre Action**")
            lines.append(f"{tc.pre_action}")
            lines.append("")
            lines.append("**Post Action**")
            lines.append(f"{tc.post_action}")
            lines.append("")
            lines.append(f"**Number of Test Steps:** {len(tc.steps)}")
            lines.append("")
            lines.append("| # | Action | Expected Result |")
            lines.append("|---|--------|-----------------|")
            for step in tc.steps:
                action = str(step.action).replace("|", "\\|")
                expected = str(step.expected_result).replace("|", "\\|")
                lines.append(f"| {step.index}. | {action} | {expected} |")
            lines.append("")
            lines.append("**Description**")
            lines.append(f"{state.requirement}")
            lines.append("")
            lines.append("**Expected Observables**")
            for observable in tc.expected_observables:
                lines.append(f"- {observable}")
            lines.append("")
            lines.append("**Tool Commands**")
            for command in tc.tool_commands:
                lines.append(f"- `{command}`")
            lines.append("")
            lines.append("**Log Assertions**")
            for assertion in tc.log_assertions:
                lines.append(f"- `{assertion}`")
            lines.append("")
            lines.append("**Evidence References**")
            for ref in tc.evidence_refs:
                section = ref.section or ""
                lines.append(f"- {ref.filename} | {section} | {ref.line_snippet}")
            lines.append("")
            lines.append("---")
            lines.append("")
            section_index += 1

    Path(file_path).write_text("\n".join(lines), encoding="utf-8")
from agents.po_agent import run_po_agent
from agents.qa_agents import run_qa_agent
from agents.qa_agents import is_valid_for_qa    
from models.sdlc_states import SDLCState, Source, Processing, Output, Metadata
import sys
import json
from pathlib import Path
import os

def normalize_requirement_type(value):
    if value is None:
        return "SYSTEM"

    value = str(value).strip().upper()

    if value in ["API", "UI", "SYSTEM"]:
        return value

    return "SYSTEM"


def _is_blank(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null", "n/a", "na", "tbd", "..."}


def _can_prompt_user() -> bool:
    # BMAD default: file-based Q/A. Enable interactive prompts explicitly.
    interactive_enabled = os.getenv("SDLC_INTERACTIVE_CLARIFICATION", "0") == "1"
    return interactive_enabled and sys.stdin is not None and sys.stdin.isatty()


def _prompt_if_missing(label: str, current_value) -> str:
    if not _is_blank(current_value):
        return str(current_value).strip()

    if not _can_prompt_user():
        return ""

    answer = input(f"[CLARIFICATION] {label} (leave blank if unknown): ").strip()
    return answer


def _collect_clarifications(state: SDLCState) -> SDLCState:
    # Ensure nested objects exist so missing fields can be populated interactively.
    state.source = state.source or Source()
    state.processing = state.processing or Processing()
    state.output = state.output or Output()

    state.module = _prompt_if_missing("Module name", state.module)
    state.source.input_signal = _prompt_if_missing("Source input signal", state.source.input_signal)
    state.source.source_component = _prompt_if_missing("Source component", state.source.source_component)
    state.processing.logic = _prompt_if_missing("Processing logic", state.processing.logic)
    state.processing.target_component = _prompt_if_missing("Processing target component", state.processing.target_component)
    state.processing.transformation = _prompt_if_missing("Processing transformation", state.processing.transformation)
    state.output.output_signal = _prompt_if_missing("Output signal", state.output.output_signal)
    state.output.ui_element = _prompt_if_missing("Output UI element", state.output.ui_element)
    state.output.expected_behavior = _prompt_if_missing("Expected behavior", state.output.expected_behavior)

    if not state.acceptance_criteria or not any(not _is_blank(v) for v in state.acceptance_criteria):
        if _can_prompt_user():
            raw = input("[CLARIFICATION] Acceptance criteria (separate multiple entries with ';', leave blank if unknown): ").strip()
            if raw:
                state.acceptance_criteria = [item.strip() for item in raw.split(";") if item.strip()]
            else:
                state.acceptance_criteria = []
        else:
            state.acceptance_criteria = []

    return state


def _get_clarification_file(feature_id: str) -> Path:
    return Path("test") / "clarifications" / f"{feature_id}_questions.json"


def _get_clarification_answers_file(feature_id: str) -> Path:
    return Path("test") / "clarifications" / f"{feature_id}_answers.json"


def _build_clarification_questions(state: SDLCState):
    return {
        "feature_id": state.feature_id,
        "requirement": state.requirement,
        "instructions": "Fill answers. Keep empty if unknown. Do not guess.",
        "questions": {
            "module": state.module or "",
            "source_input_signal": state.source.input_signal if state.source else "",
            "source_component": state.source.source_component if state.source else "",
            "processing_logic": state.processing.logic if state.processing else "",
            "processing_target_component": state.processing.target_component if state.processing else "",
            "processing_transformation": state.processing.transformation if state.processing else "",
            "output_signal": state.output.output_signal if state.output else "",
            "output_ui_element": state.output.ui_element if state.output else "",
            "output_expected_behavior": state.output.expected_behavior if state.output else "",
            "acceptance_criteria": state.acceptance_criteria or [],
            "pre_action": "",
            "post_action": "--",
            "expected_observables": [],
            "tool_commands": [],
            "log_assertions": [],
            "evidence_hints": [
                "Example format: filename|section|exact line snippet"
            ],
        },
    }


def _merge_existing_answers(payload, answers):
    existing_q = (answers or {}).get("questions", {}) if isinstance(answers, dict) else {}
    if not isinstance(existing_q, dict):
        return payload

    merged = dict(payload)
    merged_q = dict(payload.get("questions", {}))
    for key, value in existing_q.items():
        # Preserve existing non-empty answers.
        if isinstance(value, list):
            if value:
                merged_q[key] = value
        elif isinstance(value, str):
            if value.strip():
                merged_q[key] = value
        elif value is not None:
            merged_q[key] = value

    merged["questions"] = merged_q
    return merged


def _load_clarification_answers(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _listify(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [v.strip() for v in value.split(";") if v.strip()]
    return []


def _apply_clarification_answers(state: SDLCState, answers) -> SDLCState:
    q = (answers or {}).get("questions", {})
    if not q:
        return state

    state.module = _prompt_if_missing("Module name", q.get("module") or state.module)
    state.source = state.source or Source()
    state.processing = state.processing or Processing()
    state.output = state.output or Output()

    state.source.input_signal = _prompt_if_missing("Source input signal", q.get("source_input_signal") or state.source.input_signal)
    state.source.source_component = _prompt_if_missing("Source component", q.get("source_component") or state.source.source_component)
    state.processing.logic = _prompt_if_missing("Processing logic", q.get("processing_logic") or state.processing.logic)
    state.processing.target_component = _prompt_if_missing("Processing target component", q.get("processing_target_component") or state.processing.target_component)
    state.processing.transformation = _prompt_if_missing("Processing transformation", q.get("processing_transformation") or state.processing.transformation)
    state.output.output_signal = _prompt_if_missing("Output signal", q.get("output_signal") or state.output.output_signal)
    state.output.ui_element = _prompt_if_missing("Output UI element", q.get("output_ui_element") or state.output.ui_element)
    state.output.expected_behavior = _prompt_if_missing("Expected behavior", q.get("output_expected_behavior") or state.output.expected_behavior)

    if _listify(q.get("acceptance_criteria")):
        state.acceptance_criteria = _listify(q.get("acceptance_criteria"))

    state.metadata = state.metadata or Metadata()
    state.metadata.clarification_pre_action = str(q.get("pre_action") or "").strip()
    state.metadata.clarification_post_action = str(q.get("post_action") or "--").strip()
    state.metadata.clarification_expected_observables = _listify(q.get("expected_observables"))
    state.metadata.clarification_tool_commands = _listify(q.get("tool_commands"))
    state.metadata.clarification_log_assertions = _listify(q.get("log_assertions"))
    state.metadata.clarification_evidence_hints = _listify(q.get("evidence_hints"))
    return state


def _ensure_bmad_clarification(state: SDLCState) -> tuple[SDLCState, bool]:
    path = _get_clarification_file(state.feature_id)
    answers_path = _get_clarification_answers_file(state.feature_id)
    answers = _load_clarification_answers(answers_path) or _load_clarification_answers(path)

    if answers:
        state = _apply_clarification_answers(state, answers)

    # If required context is still incomplete, produce questionnaire and block QA.
    if not is_valid_for_qa(state):
        payload = _build_clarification_questions(state)
        payload = _merge_existing_answers(payload, answers)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        state.test_cases = []
        state.review_feedback = f"Clarification required before QA: {path}"
        return state, False

    # Ensure QA-specific required hints are present; otherwise ask first.
    state.metadata = state.metadata or Metadata()
    if not state.metadata.clarification_tool_commands or not state.metadata.clarification_log_assertions or not state.metadata.clarification_evidence_hints:
        payload = _build_clarification_questions(state)
        payload = _merge_existing_answers(payload, answers)
        payload["instructions"] = (
            "Fill all base fields plus tool_commands, log_assertions, and evidence_hints. "
            "Pipeline will skip QA until these are provided."
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        state.test_cases = []
        state.review_feedback = f"Clarification required (QA hints missing): {path}"
        return state, False

    return state, True

def run_batch(requirements):
    results = []

    for req in requirements:
        print(f"\n🚀 Processing: {req['feature_id']}")

        raw_type = req.get("requirement_type")

        # 🔥 FIX NaN
        if raw_type is None or str(raw_type).lower() == "nan":
            raw_type = ""

        requirement_type = normalize_requirement_type(raw_type)

        state = SDLCState(
            feature_id=str(req.get("feature_id", "")),
            module=str(req.get("module", "")),
            requirement=str(req.get("requirement", "")),
            requirement_type=requirement_type
        )

        # Normalize worksheet placeholders to empty values.
        if _is_blank(state.module):
            state.module = ""
        if _is_blank(state.requirement):
            state.requirement = ""

        # Step 1: Enrichment
        state = run_po_agent(state)

        # Step 2: Human-in-the-loop clarification for unknown context.
        state = _collect_clarifications(state)

        # Step 3: BMAD-style clarification gate (file-based Q/A with resume).
        state, ready_for_qa = _ensure_bmad_clarification(state)
        if not ready_for_qa:
            print(f"⚠️ {state.review_feedback}")
            results.append(state)
            continue

        # Step 4: Validation (do not hallucinate if still incomplete)
        if not is_valid_for_qa(state):
            print("⚠️ Skipping QA - insufficient context")
            state.test_cases = []
            if not state.review_feedback:
                state.review_feedback = "Skipped QA due to insufficient context after clarification"

            # Optional: still store state for traceability
            results.append(state)
            continue

        # Step 5: QA Agent
        state = run_qa_agent(state)

        results.append(state)

    return results
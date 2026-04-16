from models.sdlc_states import SDLCState, TestCase
from langchain_ollama import OllamaLLM
import json
import re
from pathlib import Path
from jsonschema import Draft202012Validator
import os

llm = OllamaLLM(model="llama3.2", temperature=0, format="json")
ENABLE_QA_REVIEW_PASS = os.getenv("SDLC_ENABLE_QA_REVIEW", "0") == "1"
USE_RULE_BASED_QA = os.getenv("SDLC_USE_RULE_BASED_QA", "1") == "1"

PLACEHOLDER_VALUES = {"", "...", "tbd", "na", "n/a", "nan", "none", "null"}
GENERIC_WEB_TERMS = {"login", "password", "username", "signup", "web", "browser", "form"}

QA_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["test_cases"],
    "properties": {
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "type",
                    "description",
                    "pre_action",
                    "post_action",
                    "steps",
                    "expected_observables",
                    "tool_commands",
                    "log_assertions",
                    "evidence_refs",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "type": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                    "pre_action": {"type": "string", "minLength": 1},
                    "post_action": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["index", "action", "expected_result"],
                            "properties": {
                                "index": {"type": "integer", "minimum": 1},
                                "action": {"type": "string", "minLength": 1},
                                "expected_result": {"type": "string", "minLength": 1},
                            },
                        },
                        "minItems": 1,
                    },
                    "expected_observables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "tool_commands": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "log_assertions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "evidence_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["filename", "line_snippet"],
                            "properties": {
                                "filename": {"type": "string", "minLength": 1},
                                "section": {"type": "string"},
                                "line_snippet": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        }
    },
}

qa_output_validator = Draft202012Validator(QA_OUTPUT_SCHEMA)


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_VALUES


def _has_meaningful_text(value) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if len(text) < 8:
        return False
    return not _is_placeholder(text)


def _has_meaningful_list(values) -> bool:
    if not isinstance(values, list):
        return False
    meaningful_items = [item for item in values if _has_meaningful_text(item)]
    return len(meaningful_items) >= 2


def _load_ground_truth_documents(doc_dirs=None) -> dict:
    if doc_dirs is None:
        doc_dirs = ["doc", "data"]

    documents = {}
    for root in doc_dirs:
        base = Path(root)
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in {".md", ".txt", ".json", ".csv"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if text:
                    documents[str(path.relative_to(Path(".")))] = text
            except Exception as exc:
                print(f"⚠️ Unable to read {path}: {exc}")

    return documents


def _build_ground_truth_context(documents: dict, max_chars: int = 12000) -> str:
    joined = []
    for filename, text in documents.items():
        joined.append(f"# {filename}\n{text}")
    context = "\n\n".join(joined)
    return context[:max_chars]


def _tokenize(text: str):
    return {t for t in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower()) if not t.isdigit()}


def _normalize_qa_payload(data):
    if isinstance(data, list):
        return {"test_cases": data}
    if isinstance(data, dict):
        if "testCases" in data and "test_cases" not in data:
            data = {"test_cases": data.get("testCases")}
        return data
    return {"test_cases": []}


def _default_evidence_ref(documents: dict):
    for filename, text in documents.items():
        for line in text.splitlines():
            snippet = line.strip()
            if len(snippet) >= 12:
                return {
                    "filename": filename,
                    "section": "",
                    "line_snippet": snippet[:160],
                }
    return {"filename": "doc/agent_contracts.md", "section": "", "line_snippet": "Ground Truth Source Policy"}


def _evidence_from_hints(hints, documents: dict):
    refs = []
    for hint in hints or []:
        raw = str(hint).strip()
        if not raw or raw.lower().startswith("example format"):
            continue
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) == 3:
            candidate = {"filename": parts[0], "section": parts[1], "line_snippet": parts[2]}
            if candidate["filename"] in documents and candidate["line_snippet"].lower() in documents[candidate["filename"]].lower():
                refs.append(candidate)
    if not refs:
        refs.append(_default_evidence_ref(documents))
    return refs


def _build_rule_based_test_cases(state: SDLCState, documents: dict):
    meta = state.metadata
    if not meta:
        return []

    tool_commands = (meta.clarification_tool_commands or [])
    log_assertions = (meta.clarification_log_assertions or [])
    expected_observables = (meta.clarification_expected_observables or [])
    pre_action = (meta.clarification_pre_action or "").strip()
    post_action = (meta.clarification_post_action or "--").strip() or "--"
    evidence_refs = _evidence_from_hints(meta.clarification_evidence_hints or [], documents)

    if not pre_action or not tool_commands or not log_assertions:
        return []

    # Deterministic, requirement-anchored flow: use only user-provided hints.
    steps = []
    for idx, cmd in enumerate(tool_commands, start=1):
        expected = "Command executes successfully"
        if idx == 1 and expected_observables:
            expected = expected_observables[0]
        steps.append(
            {
                "index": idx,
                "action": cmd,
                "expected_result": expected,
            }
        )

    verify_step_index = len(steps) + 1
    verification_target = log_assertions[0] if log_assertions else (expected_observables[0] if expected_observables else "Expected behavior observed")
    steps.append(
        {
            "index": verify_step_index,
            "action": "Verify log/assertion markers for requirement behavior",
            "expected_result": verification_target,
        }
    )

    case_id = f"test_tc_{state.feature_id}_requirement_verification"
    description = state.requirement.strip() if state.requirement else f"Requirement verification for feature {state.feature_id}"

    return [
        {
            "id": case_id,
            "type": "manual",
            "description": description,
            "pre_action": pre_action,
            "post_action": post_action,
            "steps": steps,
            "expected_observables": expected_observables or log_assertions,
            "tool_commands": tool_commands,
            "log_assertions": log_assertions,
            "evidence_refs": evidence_refs,
        }
    ]


def _repair_qa_payload(data, state: SDLCState, documents: dict):
    meta = state.metadata
    tool_hints = (meta.clarification_tool_commands if meta else []) or []
    log_hints = (meta.clarification_log_assertions if meta else []) or []
    evidence_hints = (meta.clarification_evidence_hints if meta else []) or []
    pre_action_hint = (meta.clarification_pre_action if meta else "") or "DUT should be powered ON and service should be running."
    post_action_hint = (meta.clarification_post_action if meta else "--") or "--"
    observable_hints = (meta.clarification_expected_observables if meta else []) or []

    cases = data.get("test_cases") or []
    repaired = []
    for idx, case in enumerate(cases, start=1):
        item = dict(case)
        item["id"] = str(item.get("id") or f"TC_{idx:03d}")
        item["type"] = str(item.get("type") or "manual")
        item["description"] = str(item.get("description") or "Derived QA testcase")
        item["pre_action"] = str(item.get("pre_action") or pre_action_hint)
        item["post_action"] = str(item.get("post_action") or post_action_hint)

        raw_steps = item.get("steps") or []
        fixed_steps = []
        if isinstance(raw_steps, list):
            for s_idx, step in enumerate(raw_steps, start=1):
                if isinstance(step, dict):
                    fixed_steps.append(
                        {
                            "index": int(step.get("index") or s_idx),
                            "action": str(step.get("action") or "Execute step"),
                            "expected_result": str(step.get("expected_result") or "Expected behavior observed"),
                        }
                    )
                elif isinstance(step, str) and step.strip():
                    fixed_steps.append(
                        {
                            "index": s_idx,
                            "action": step.strip(),
                            "expected_result": "Expected behavior observed",
                        }
                    )

        if not fixed_steps:
            if tool_hints:
                fixed_steps.append({"index": 1, "action": tool_hints[0], "expected_result": "Command executes successfully"})
            else:
                fixed_steps.append({"index": 1, "action": "Execute validation step", "expected_result": "Behavior verified"})
        item["steps"] = fixed_steps

        item["tool_commands"] = [str(v) for v in (item.get("tool_commands") or tool_hints) if str(v).strip()]
        if not item["tool_commands"]:
            item["tool_commands"] = ["No tool command provided"]

        item["log_assertions"] = [str(v) for v in (item.get("log_assertions") or log_hints) if str(v).strip()]
        if not item["log_assertions"]:
            item["log_assertions"] = ["No log assertion provided"]

        item["expected_observables"] = [str(v) for v in (item.get("expected_observables") or observable_hints) if str(v).strip()]
        if not item["expected_observables"]:
            item["expected_observables"] = item["log_assertions"]

        refs = item.get("evidence_refs") or _evidence_from_hints(evidence_hints, documents)
        normalized_refs = []
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict):
                    filename = str(ref.get("filename") or "").strip()
                    section = str(ref.get("section") or "").strip()
                    line_snippet = str(ref.get("line_snippet") or "").strip()
                    if filename and line_snippet and filename in documents and line_snippet.lower() in documents[filename].lower():
                        normalized_refs.append(
                            {
                                "filename": filename,
                                "section": section,
                                "line_snippet": line_snippet,
                            }
                        )

        if not normalized_refs:
            normalized_refs = _evidence_from_hints(evidence_hints, documents)
        if not normalized_refs:
            normalized_refs = [_default_evidence_ref(documents)]

        item["evidence_refs"] = normalized_refs

        repaired.append(item)

    data["test_cases"] = repaired
    return data


def _validate_qa_payload(data):
    errors = sorted(qa_output_validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.path) or "root"
        raise ValueError(f"QA schema validation failed at {loc}: {first.message}")


def _evidence_ref_maps_to_context(ref, documents: dict) -> bool:
    filename = str(ref.filename).strip()
    if filename not in documents:
        return False

    doc_text = documents[filename]
    snippet = str(ref.line_snippet).strip().lower()
    if not snippet or snippet not in doc_text.lower():
        return False

    if ref.section:
        section = str(ref.section).strip().lower()
        if section and section not in doc_text.lower():
            return False

    return True


def _is_grounded_test_case(tc: TestCase, state: SDLCState, doc_context: str, documents: dict) -> bool:
    step_text = " ".join([f"{step.action} {step.expected_result}" for step in tc.steps])
    combined = " ".join(
        [
            tc.description,
            tc.pre_action,
            tc.post_action,
            step_text,
            " ".join(tc.expected_observables),
            " ".join(tc.tool_commands),
            " ".join(tc.log_assertions),
        ]
    ).lower()
    tokens = _tokenize(combined)

    if tokens & GENERIC_WEB_TERMS:
        return False

    allowed_text = " ".join(
        [
            str(state.requirement or ""),
            " ".join(state.acceptance_criteria or []),
            str(state.source or ""),
            str(state.processing or ""),
            str(state.output or ""),
            doc_context,
        ]
    )
    allowed_tokens = _tokenize(allowed_text)
    overlap = tokens & allowed_tokens

    evidence_mapped = any(_evidence_ref_maps_to_context(ref, documents) for ref in tc.evidence_refs)
    if not evidence_mapped:
        return False

    # Allow clarified operational commands/assertions while still requiring evidence mapping.
    return len(overlap) >= 1


def is_valid_for_qa(state: SDLCState) -> bool:
    processing_logic = state.processing.logic if state.processing else None
    expected_behavior = state.output.expected_behavior if state.output else None
    return all(
        [
            _has_meaningful_text(state.requirement),
            _has_meaningful_list(state.acceptance_criteria),
            _has_meaningful_text(processing_logic),
            _has_meaningful_text(expected_behavior),
        ]
    )

def extract_json(text: str) -> str:
    # Try to extract JSON inside ``` ```
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    # Fallback: find first JSON object or array
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1)

    return text.strip()

def clean_json(text: str) -> str:
    text = text.strip()

    # Remove ```json ... ```
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]

    return text.strip()

def run_qa_agent(state: SDLCState) -> SDLCState:
    if not is_valid_for_qa(state):
        print("⚠️ Skipping QA generation due to insufficient requirement context")
        state.test_cases = []
        state.review_feedback = "Insufficient context for QA test generation"
        return state

    documents = _load_ground_truth_documents(["doc", "data"])
    doc_context = _build_ground_truth_context(documents)
    hint_commands = (state.metadata.clarification_tool_commands if state.metadata else []) or []
    hint_logs = (state.metadata.clarification_log_assertions if state.metadata else []) or []
    hint_evidence = (state.metadata.clarification_evidence_hints if state.metadata else []) or []
    hint_pre_action = (state.metadata.clarification_pre_action if state.metadata else "") or ""
    hint_post_action = (state.metadata.clarification_post_action if state.metadata else "") or ""
    hint_observables = (state.metadata.clarification_expected_observables if state.metadata else []) or []

    if USE_RULE_BASED_QA:
        rule_cases = _build_rule_based_test_cases(state, documents)
        if rule_cases:
            print("Using rule-based QA generation from clarification inputs")
            data = {"test_cases": rule_cases}
            data = _repair_qa_payload(data, state, documents)
            _validate_qa_payload(data)
            test_cases = [TestCase(**tc) for tc in data["test_cases"]]
            test_cases = [tc for tc in test_cases if _is_grounded_test_case(tc, state, doc_context, documents)]
            state.test_cases = test_cases
            if not test_cases:
                state.review_feedback = "Rule-based generation produced no grounded test cases"
            return state

    # -------- Step 1: Generate --------
    prompt = f"""
        You are a senior automotive embedded QA engineer.

        IMPORTANT DOMAIN:
        - Automotive system (NOT web application)
        - Signal-based communication
        - ECU → HAL → UI pipeline
        - Real-time constraints
        - Safety-critical behavior

        DO NOT generate:
        - Login tests
        - UI form validation
        - Web-based scenarios

        FOCUS ONLY ON:
        - Signal input/output validation
        - Timing constraints (latency)
        - Data accuracy
        - Signal loss / failure handling
        - Component interaction

        Requirement identity:
        Feature ID: {state.feature_id}
        Module: {state.module}
        Requirement Type: {state.requirement_type}
        Requirement Text: {state.requirement}

        System context:
        Source: {state.source}
        Processing: {state.processing}
        Output: {state.output}

        Acceptance Criteria:
        {state.acceptance_criteria}

        User-provided clarification hints (must be used when relevant):
        pre_action: {hint_pre_action}
        post_action: {hint_post_action}
        expected_observables: {hint_observables}
        tool_commands: {hint_commands}
        log_assertions: {hint_logs}
        evidence_hints: {hint_evidence}

                Ground truth reference (organization docs):
                {doc_context}

                HARD RULES:
                - Use only requirement/context/ground-truth facts. Do not invent components or signals.
                - If context is insufficient, return: {{"test_cases": []}}.
                - Output must be STRICT JSON object with exact key `test_cases`.
                - Each testcase must include EXACT keys:
                    id, type, description, pre_action, post_action, steps, expected_observables, tool_commands, log_assertions, evidence_refs
                - steps must be objects with keys: index, action, expected_result.
                - evidence_refs must be an array with entries containing:
                    filename, section, line_snippet
                - filename must match one of these docs: {list(documents.keys())}
                - line_snippet must be a direct quote from the referenced document.
                - Use at least one tool command and one log assertion from user-provided clarification hints.

        Generate MINIMUM 5 test cases covering:
        - Normal signal flow
        - Invalid signal
        - Signal loss
        - Performance delay
        - Boundary values

        Output STRICT JSON only.
        """

    response = llm.invoke(prompt)
    print("RAW LLM OUTPUT:\n", response)

    cleaned = extract_json(response)
    print("\n=== CLEANED JSON ===\n", cleaned)

    # Parse initial output
    try:
        data = _normalize_qa_payload(json.loads(cleaned))
        data = _repair_qa_payload(data, state, documents)
        _validate_qa_payload(data)
        test_cases = [TestCase(**tc) for tc in data["test_cases"]]

        grounded_cases = [tc for tc in test_cases if _is_grounded_test_case(tc, state, doc_context, documents)]
        rejected = len(test_cases) - len(grounded_cases)
        if rejected:
            print(f"⚠️ Rejected {rejected} potentially ungrounded test case(s)")
        test_cases = grounded_cases
    except Exception as e:
        print("Initial parsing failed:", e)
        state.test_cases = []
        state.review_feedback = f"QA parsing failed: {e}"
        return state

    if not test_cases:
        state.test_cases = []
        state.review_feedback = "No grounded test cases generated"
        return state

    if not ENABLE_QA_REVIEW_PASS:
        print("Skipping review pass (SDLC_ENABLE_QA_REVIEW=0)")
        print("FINAL TEST CASE COUNT:", len(test_cases))
        state.test_cases = test_cases
        return state

    # -------- Step 2: Review --------
    review_prompt = f"""
        You are a senior QA reviewer.

        Requirement context:
        Feature ID: {state.feature_id}
        Module: {state.module}
        Requirement Text: {state.requirement}
        Acceptance Criteria: {state.acceptance_criteria}

        Evaluate the following test cases:

        {cleaned}

        Check:
        - Are edge cases covered?
        - Are failure scenarios included?
        - Are performance conditions tested?

        If NOT sufficient:
        - Return FULL improved suite using this exact JSON format:
                    {{"test_cases": [{{"id":"...","type":"manual","description":"...","pre_action":"...","post_action":"...","steps":[{{"index":1,"action":"...","expected_result":"..."}}],"expected_observables":["..."],"tool_commands":["..."],"log_assertions":["..."],"evidence_refs":[{{"filename":"...","section":"...","line_snippet":"..."}}]}}]}}

        If sufficient:
        - Return exactly: {{"status":"PASS"}}
        """

    review_response = llm.invoke(review_prompt)
    improved_json = extract_json(review_response)

    if improved_json and "PASS" not in improved_json.upper():
        print("⚠️ Improving test cases...")

        print("\n=== IMPROVED JSON ===\n", improved_json)
        try:
            improved_data = _normalize_qa_payload(json.loads(improved_json))
            improved_data = _repair_qa_payload(improved_data, state, documents)
            _validate_qa_payload(improved_data)
            improved_cases = [TestCase(**tc) for tc in improved_data["test_cases"]]
            test_cases = [tc for tc in improved_cases if _is_grounded_test_case(tc, state, doc_context, documents)]
            print(f"✅ Improved test cases loaded: {len(test_cases)}")
        except Exception as e:
            print("❌ Improvement parsing failed:", e)
            print("Keeping original test cases")

    # -------- Final --------
    print("FINAL TEST CASE COUNT:", len(test_cases))

    state.test_cases = test_cases
    return state
        
if __name__ == "__main__":
    import json
    from models.sdlc_states import SDLCState

    print("🚀 QA Agent started...")


    # Load sample input
    with open("schemas/sample.json") as f:
        data = json.load(f)

    state = SDLCState(**data)

    # Run agent
    result = run_qa_agent(state)

    # Print output
    print("\n=== FINAL OUTPUT ===")
    print(result)
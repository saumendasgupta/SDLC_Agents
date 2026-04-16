from models.sdlc_states import SDLCState, Source, Processing, Output
from langchain_ollama import OllamaLLM
import json
import re

llm = OllamaLLM(model="llama3.2", temperature=0, format="json")


def _normalize_text(value) -> str:
  if value is None:
    return ""
  if isinstance(value, str):
    return value.strip()
  if isinstance(value, (dict, list)):
    return json.dumps(value, ensure_ascii=True)
  return str(value).strip()


def extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1)

    return text.strip()


def run_po_agent(state: SDLCState) -> SDLCState:

    prompt = f"""
You are a senior automotive system engineer.

Your job is to analyze a requirement and extract structured system behavior.

IMPORTANT DOMAIN:
- Automotive system
- ECU → HAL → UI signal flow
- Real-time constraints

DO NOT assume web/mobile applications.

Requirement:
{state.requirement}

Generate STRICT JSON with:

{{
  "source": {{
    "input_signal": "...",
    "source_component": "..."
  }},
  "processing": {{
    "logic": "...",
    "target_component": "...",
    "transformation": "..."
  }},
  "output": {{
    "output_signal": "...",
    "ui_element": "...",
    "expected_behavior": "..."
  }},
  "acceptance_criteria": [
    "...",
    "..."
  ]
}}

Rules:
- Be specific to automotive systems
- Include timing, signal validation, failure cases
- Keep `source`, `processing`, and `output` fields as plain strings (no nested lists/objects)
- Keep `acceptance_criteria` as array of short strings only
- If any value is not explicitly present in the input requirement/context, return empty string for that field
- Do not invent tool names, command names, components, signals, enums, or timings
- Output ONLY JSON
"""

    response = llm.invoke(prompt)
    print("\n=== PO RAW OUTPUT ===\n", response)

    cleaned = extract_json(response)
    print("\n=== PO CLEANED JSON ===\n", cleaned)

    try:
        data = json.loads(cleaned)

        # Update state with typed models so downstream validation is reliable.
        source_data = data.get("source") or {}
        processing_data = data.get("processing") or {}
        output_data = data.get("output") or {}
        acceptance_criteria = data.get("acceptance_criteria") or []

        if not isinstance(acceptance_criteria, list):
            acceptance_criteria = [str(acceptance_criteria)]

        state.source = Source(
          origin=_normalize_text(source_data.get("origin") or state.source.origin if state.source else "Codebeamer"),
          input_signal=_normalize_text(source_data.get("input_signal")),
          source_component=_normalize_text(source_data.get("source_component")),
        )
        state.processing = Processing(
          logic=_normalize_text(processing_data.get("logic")),
          target_component=_normalize_text(processing_data.get("target_component")),
          transformation=_normalize_text(processing_data.get("transformation")),
        )
        state.output = Output(
          output_signal=_normalize_text(output_data.get("output_signal")),
          ui_element=_normalize_text(output_data.get("ui_element")),
          expected_behavior=_normalize_text(output_data.get("expected_behavior")),
        )
        state.acceptance_criteria = [
          _normalize_text(item)
          for item in acceptance_criteria
          if _normalize_text(item)
        ]

    except Exception as e:
        print("❌ PO parsing failed:", e)

    return state
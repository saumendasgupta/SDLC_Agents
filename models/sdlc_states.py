from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class RequirementType(str, Enum):
    API = "API"
    UI = "UI"
    SYSTEM = "SYSTEM"

# ---------- Source ----------
class Source(BaseModel):
    origin: str = "Codebeamer"
    input_signal: Optional[str] = None
    source_component: Optional[str] = None


# ---------- Processing ----------
class Processing(BaseModel):
    logic: Optional[str] = None
    target_component: Optional[str] = None
    transformation: Optional[str] = None


# ---------- Output ----------
class Output(BaseModel):
    output_signal: Optional[str] = None
    ui_element: Optional[str] = None
    expected_behavior: Optional[str] = None


# ---------- Test Case ----------
class EvidenceRef(BaseModel):
    filename: str
    section: Optional[str] = None
    line_snippet: str


class TestStep(BaseModel):
    index: int
    action: str
    expected_result: str


class TestCase(BaseModel):
    id: str
    type: str  # manual / automation
    description: str
    pre_action: str
    post_action: str
    steps: List[TestStep]
    expected_observables: List[str]
    tool_commands: List[str]
    log_assertions: List[str]
    evidence_refs: List[EvidenceRef]


# ---------- Non Functional ----------
class NonFunctional(BaseModel):
    performance: Optional[str] = None
    safety: Optional[str] = None
    error_handling: Optional[str] = None

class Metadata(BaseModel):
    priority: Optional[str] = None
    status: Optional[str] = None
    source_agent: Optional[str] = None
    clarification_tool_commands: Optional[List[str]] = None
    clarification_log_assertions: Optional[List[str]] = None
    clarification_evidence_hints: Optional[List[str]] = None
    clarification_pre_action: Optional[str] = None
    clarification_post_action: Optional[str] = None
    clarification_expected_observables: Optional[List[str]] = None

# ---------- Main SDLC State ----------
class SDLCState(BaseModel):
    version: Optional[str] = "1.0"
    feature_id: str
    module: str
    requirement: str
    requirement_type: RequirementType  # API / UI / SYSTEM

    id: Optional[str] = None
    source: Optional[Source] = None
    processing: Optional[Processing] = None
    output: Optional[Output] = None

    acceptance_criteria: Optional[List[str]] = None
    test_cases: Optional[List[TestCase]] = None
    non_functional: Optional[NonFunctional] = None

    review_feedback: Optional[str] = None
    metadata: Optional[Metadata] = None
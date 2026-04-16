# SDLC Multi-Agent Contract Specification

## 1. Contract Metadata

- `contract_id`: `SDLC-AGENT-CONTRACT-V1`
- `version`: `1.0.0`
- `status`: `draft | active | deprecated`
- `owner_team`: `Platform Engineering`
- `reviewers`: `Architecture, QA Governance, DevEx`
- `effective_date`: `YYYY-MM-DD`
- `compatibility_policy`: backward-compatible changes allowed in minor versions only
- `deprecation_policy`: minimum one release notice before field removal

## 2. Purpose and Scope

This contract defines how all SDLC agents (PO, Architect, Developer, QA, Reviewer) exchange artifacts.

This is not a prompt guideline. It is the organization-level interface agreement for:

- input/output schema
- data source trust policy
- grounding and evidence requirements
- validation and rejection behavior
- traceability and auditability

## 3. Common Envelope (Required for All Agents)

Every agent request and response must include this envelope.

```json
{
	"artifact_id": "string",
	"feature_id": "string",
	"requirement_ids": ["string"],
	"agent_role": "PO|ARCHITECT|DEVELOPER|QA|REVIEWER",
	"input_artifacts": ["string"],
	"output_artifacts": ["string"],
	"run_id": "string",
	"trace_id": "string",
	"status": "draft|in_review|approved|rejected|error",
	"errors": [
		{
			"code": "string",
			"message": "string"
		}
	],
	"warnings": ["string"],
	"created_at": "ISO-8601",
	"updated_at": "ISO-8601",
	"metadata": {
		"owner_team": "string",
		"source_system": "string",
		"model_name": "string",
		"model_version": "string"
	}
}
```

## 4. Ground Truth Source Policy

## 4.1 Approved Input Source Types

- `xlsx` (requirements sheets, mapping tables)
- `md`/`doc`/`docx` (specification and process docs)
- `png`/`jpg` (screenshots, diagrams)

## 4.2 Source Location Convention

- primary source directory: `data/`
- optional categorized subfolders:
	- `data/requirements/`
	- `data/specs/`
	- `data/images/`

## 4.3 Source Trust Ranking

When conflicting facts exist, use this precedence:

1. signed requirement specification
2. approved architecture/ICD document
3. exported team knowledge-base pages
4. spreadsheet annotations
5. screenshots/images

## 4.4 Image Extraction Policy

- OCR-derived text from images must be marked as `low_confidence` unless verified by another source.
- OCR-only statements cannot be used as sole evidence for critical assertions.

## 5. Retrieval and Grounding Policy (RAG)

## 5.1 Mandatory Retrieval Behavior

- Retrieve relevant chunks from `data/` before generation.
- Generation without retrieval is forbidden for production mode.
- Each generated claim must map to at least one retrieved source snippet.

## 5.2 Evidence Reference Contract

Each generated testcase must include one or more `evidence_refs`.

```json
{
	"filename": "string",
	"section": "string",
	"line_snippet": "string"
}
```

Validation rules:

- `filename` must exist in retrieved sources.
- `line_snippet` must match source text.
- if `section` is provided, it must exist in the same file.

Failure behavior:

- missing evidence => reject testcase
- unmapped evidence => reject testcase

## 6. QA Agent Contract

## 6.1 QA Input (Payload)

```json
{
	"requirement": "string",
	"requirement_type": "API|UI|SYSTEM",
	"source": {
		"input_signal": "string",
		"source_component": "string"
	},
	"processing": {
		"logic": "string",
		"target_component": "string",
		"transformation": "string"
	},
	"output": {
		"output_signal": "string",
		"ui_element": "string",
		"expected_behavior": "string"
	},
	"acceptance_criteria": ["string"],
	"retrieved_context": [
		{
			"filename": "string",
			"section": "string",
			"snippet": "string",
			"confidence": "high|medium|low"
		}
	]
}
```

## 6.2 QA Output (Payload)

```json
{
	"test_cases": [
		{
			"id": "string",
			"type": "manual|automation",
			"description": "string",
			"pre_action": "string",
			"post_action": "string",
			"steps": [
				{
					"index": 1,
					"action": "string",
					"expected_result": "string"
				}
			],
			"expected_observables": ["string"],
			"tool_commands": ["string"],
			"log_assertions": ["string"],
			"evidence_refs": [
				{
					"filename": "string",
					"section": "string",
					"line_snippet": "string"
				}
			]
		}
	]
}
```

## 6.3 QA Coverage Rules

Minimum required coverage dimensions:

- positive flow
- negative flow
- edge/boundary behavior
- failure behavior
- timing/performance constraints

Optional domain-specific dimensions:

- transition-based notifications
- persistency and restore behavior
- authorization-dependent behavior

## 7. Validation and Rejection Gates

Artifacts must pass all gates before save/export.

1. `schema_gate`
- strict schema validation for envelope and payload

2. `grounding_gate`
- each testcase must have at least one valid evidence ref

3. `context_completeness_gate`
- required fields present and non-placeholder

4. `domain_guardrail_gate`
- reject web/mobile-only irrelevant terms for automotive signal workflows

5. `minimum_quality_gate`
- configurable minimum accepted testcase count after filtering

Standard rejection response:

```json
{
	"status": "rejected",
	"errors": [
		{
			"code": "QA_GROUNDING_FAILED",
			"message": "No evidence reference mapped to retrieved context"
		}
	]
}
```

## 8. Audit and Traceability Requirements

The system must store:

- model name/version
- prompt hash
- retrieval snapshot (selected source chunks)
- generated output before and after validation
- rejection reasons
- reviewer decisions

Audit records must be queryable by:

- `feature_id`
- `requirement_id`
- `trace_id`
- `run_id`

## 9. Change Management

Any contract change requires:

- RFC or change request ID
- impact analysis (agents and pipelines affected)
- backward compatibility decision
- migration plan
- version bump

## 10. Implementation Guidance for Current Repository

Near-term actions:

1. ingest all ground truth from `data/` (xlsx, doc/docx/md, png via OCR)
2. add retriever component that returns structured `retrieved_context`
3. update QA models/schemas to include step-level objects and observables
4. export QA output to deterministic markdown format compatible with organization test-document template
5. enforce all validation gates before writing `test/*.md` and `outputs/*.xlsx`

## 11. Non-Goals

- Free-form generation without evidence
- Prompt-only quality control with no schema or grounding gates
- Team-specific contract forks without version governance
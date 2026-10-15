## Description
<!-- Provide a concise summary of the changes and why they are necessary. -->

## Component & Ownership
- **Component:** [e.g., Logic Reviewer / Security Auditor / Style & Doc / Orchestrator / API / UI]
- **Author:** @[GitHub Username]
- **Files Modified/Created:**
  - `path/to/file`

## Rubric Evidence Addressed
- [ ] **Category A:** Multi-Agent Architecture (Distinct agent, tool use, coordination)
- [ ] **Category B:** Design & Schemas (Schema adherence, data flow)
- [ ] **Category C:** Robustness & Demo (Tool failure fallback, input validation)
- [ ] **Category F:** Engineering Practice (Clean structure, no secrets, modularity)
- [ ] **Category G:** Individual Contribution (Dedicated commits, standalone module)

## PR Quality Checklist
- [ ] Implemented class extends `BaseAgent` (if agent)
- [ ] All tool invocations wrapped via `run_tool()` in `tools.tool_base`
- [ ] Emits structured `TraceEvent` objects to blackboard trace
- [ ] LLM inputs and outputs conform strictly to `lib.schemas`
- [ ] Handles critique requests and returns structured `CritiqueResponse`
- [ ] Automated unit tests added in `tests/` and passing locally
- [ ] No hardcoded secrets, paths, or API keys
- [ ] Single-owner rule respected: zero edits to files owned by other members

## Local Verification
```bash
# Run relevant test suite
pytest tests/<test_file>.py -v
```
<!-- Paste test results or execution summary below -->

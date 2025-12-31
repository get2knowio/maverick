# Feature Specification: Generator Agents

**Feature Branch**: `019-generator-agents`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create lightweight, single-purpose generation agents that use query() for text generation without tools"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Commit Message Generation (Priority: P1)

A developer completes code changes and needs a well-formatted conventional commit message. Instead of manually writing the message, the workflow automatically generates one based on the diff and file statistics.

**Why this priority**: Commit messages are the most frequent text generation need in development workflows. Every code change requires a commit message, making this the highest-value generator.

**Independent Test**: Can be tested by providing a sample git diff and file stats, then verifying the output follows conventional commit format (type(scope): description).

**Acceptance Scenarios**:

1. **Given** a git diff showing changes to authentication code, **When** the CommitMessageGenerator is invoked with the diff and file stats, **Then** it returns a message like "feat(auth): add password reset functionality"
2. **Given** a diff with changes across multiple files, **When** the generator is invoked with an optional scope hint, **Then** the scope in the commit message matches the provided hint
3. **Given** a bug fix diff, **When** the generator is invoked, **Then** the commit type is "fix" rather than "feat"
4. **Given** an empty or invalid diff, **When** the generator is invoked, **Then** it returns an appropriate error message

---

### User Story 2 - Pull Request Description Generation (Priority: P1)

A developer is ready to create a pull request after completing multiple commits. The workflow needs to generate a comprehensive PR description that summarizes all changes, testing status, and relevant context.

**Why this priority**: PR descriptions are critical for code review quality and project documentation. Every PR needs a description, and generating them automatically ensures consistency.

**Independent Test**: Can be tested by providing a list of commits, diff statistics, task summary, and validation results, then verifying the output is properly formatted markdown with required sections.

**Acceptance Scenarios**:

1. **Given** a list of commits, diff stats, and validation results, **When** the PRDescriptionGenerator is invoked, **Then** it returns a markdown document with Summary, Changes, and Testing sections
2. **Given** failing validation results, **When** the generator is invoked, **Then** the Testing section accurately reflects the failures
3. **Given** a task summary describing the feature, **When** the generator is invoked, **Then** the Summary section incorporates the task context

---

### User Story 3 - Quick Code Analysis (Priority: P2)

A developer needs a quick explanation or review of a code snippet without invoking the full CodeReviewerAgent. The lightweight analyzer provides fast, focused analysis for specific purposes.

**Why this priority**: Quick code analysis is frequently needed during development for understanding unfamiliar code or getting a fast review. It complements but doesn't replace the full code review workflow.

**Independent Test**: Can be tested by providing a code snippet and analysis type, then verifying the output provides relevant analysis matching the requested type.

**Acceptance Scenarios**:

1. **Given** a code snippet and analysis_type="explain", **When** the CodeAnalyzer is invoked, **Then** it returns a plain-English explanation of what the code does
2. **Given** a code snippet and analysis_type="review", **When** the analyzer is invoked, **Then** it returns potential issues, improvements, and observations
3. **Given** a code snippet and analysis_type="summarize", **When** the analyzer is invoked, **Then** it returns a brief summary of the code's purpose and structure
4. **Given** an invalid analysis_type, **When** the analyzer is invoked, **Then** it returns an error or defaults to "explain"

---

### User Story 4 - Error Explanation (Priority: P2)

A developer encounters a validation failure (lint error, test failure, build error) and needs to understand what went wrong and how to fix it. The ErrorExplainer translates cryptic error output into actionable guidance.

**Why this priority**: Error understanding accelerates debugging. While not as frequent as commit messages, clear error explanations significantly improve developer experience during validation cycles.

**Independent Test**: Can be tested by providing error output and optional source context, then verifying the explanation is clear and includes actionable fix suggestions.

**Acceptance Scenarios**:

1. **Given** a Python type error and the relevant source code, **When** the ErrorExplainer is invoked, **Then** it explains the type mismatch in plain English and suggests a fix
2. **Given** a failing test output, **When** the explainer is invoked, **Then** it identifies why the test failed and what assertion was violated
3. **Given** a lint error, **When** the explainer is invoked, **Then** it explains the rule being violated and how to correct the code
4. **Given** error output without source context, **When** the explainer is invoked, **Then** it still provides a useful explanation based on the error alone

---

### Edge Cases

- What happens when input is empty or malformed? (All generators return clear error messages)
- What happens when the Claude API is unavailable? (Generators raise exception immediately on first API error; no internal retry—caller handles retry logic)
- How does the system handle very large inputs (e.g., massive diffs)? (Generators truncate to size limits—100KB for diffs, 10KB for snippets—log a WARNING, and proceed with truncated input)
- What happens when generated output doesn't match expected format? (Consumers handle gracefully)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a GeneratorAgent base class that encapsulates common generation logic
- **FR-002**: GeneratorAgent MUST use the Claude Agent SDK's query() function with max_turns=1 for single-shot generation
- **FR-003**: GeneratorAgent MUST NOT use any tools (allowed_tools should be empty or omitted)
- **FR-004**: Each concrete generator MUST define its own system prompt that enforces output format
- **FR-005**: CommitMessageGenerator MUST accept diff, file_stats, and optional scope_hint as input
- **FR-006**: CommitMessageGenerator MUST return output following conventional commit format (type(scope): description)
- **FR-007**: PRDescriptionGenerator MUST accept commits, diff_stats, task_summary, and validation_results as input
- **FR-008**: PRDescriptionGenerator MUST return markdown with configurable sections (Summary, Changes, Testing as defaults)
- **FR-009**: CodeAnalyzer MUST accept code snippet and analysis_type (one of: explain, review, summarize) as input
- **FR-010**: CodeAnalyzer MUST return analysis text appropriate to the requested analysis type
- **FR-011**: ErrorExplainer MUST accept error_output and optional source_context as input
- **FR-012**: ErrorExplainer MUST return plain-English explanation with suggested fix when possible
- **FR-013**: All generators MUST be async (async generate() method)
- **FR-014**: All generators MUST extract plain text from the Claude API response
- **FR-015**: All generators MUST handle empty or invalid input gracefully with clear error messages
- **FR-016**: All generators MUST log inputs/outputs at DEBUG level and errors at WARNING/ERROR level using standard Python logging
- **FR-017**: All generators MUST truncate inputs exceeding size limits (100KB for diffs, 10KB for code snippets) and log a WARNING before proceeding
- **FR-018**: All generators MUST raise exceptions immediately on API errors without internal retry. Generators are stateless single-shot operations; callers (workflows) implement retry with exponential backoff per Constitution IV.

### Key Entities

- **GeneratorAgent**: Base class providing common generation logic, holds name, system_prompt, and model configuration. Provides async generate(context: dict) -> str method.
- **CommitMessageGenerator**: Generates conventional commit messages from code change context. Input context includes diff, file_stats, scope_hint.
- **PRDescriptionGenerator**: Generates markdown pull request descriptions. Input context includes commits, diff_stats, task_summary, validation_results.
- **CodeAnalyzer**: Generates code analysis based on requested type. Input context includes code, analysis_type.
- **ErrorExplainer**: Generates error explanations with fix suggestions. Input context includes error_output, source_context.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Commit messages generated by CommitMessageGenerator follow conventional commit format 100% of the time (parseable by conventional-commit validators)
- **SC-002**: PR descriptions generated by PRDescriptionGenerator include all required sections (Summary, Changes, Testing) 100% of the time
- **SC-003**: Code analysis from CodeAnalyzer is relevant to the requested analysis_type at least 95% of the time (human evaluation)
- **SC-004**: Error explanations from ErrorExplainer are more understandable than raw error output at least 90% of the time (human evaluation)
- **SC-005**: All generators return results within 5 seconds for typical inputs (single API call)
- **SC-006**: Generator failures provide clear error messages that help diagnose the issue 100% of the time
- **SC-007**: All generators work correctly with the Claude Agent SDK's query() function (no tool-related errors)

## Clarifications

### Session 2025-12-18

- Q: How should generator activity be logged/monitored? → A: Standard logging only (log inputs/outputs at DEBUG level, errors at WARNING/ERROR)
- Q: What happens when input exceeds size limits (100KB diff, 10KB snippet)? → A: Truncate with warning (truncate input to limit, log warning, proceed with generation)
- Q: Should generators retry on API failure or fail immediately? → A: Fail immediately (raise exception on first API error, let caller handle retry logic)
- Q: How should generators handle potentially sensitive data in inputs? → A: Document dependency (generators assume upstream context builders filter secrets; document this assumption)

## Assumptions

- The Claude Agent SDK's query() function is available and suitable for single-shot text generation
- Conventional commit format is well-defined: type(scope): description, where type is one of: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
- PR description sections (Summary, Changes, Testing) are the standard required sections; additional sections can be added via template customization
- Analysis types for CodeAnalyzer are limited to: explain, review, summarize (extensible in future if needed)
- Generators are called synchronously by workflows at specific points, not used as autonomous agents
- Maximum input sizes follow reasonable limits (e.g., diffs under 100KB, code snippets under 10KB)
- Upstream context builders (e.g., from 018-context-builder) are responsible for detecting and filtering secrets from inputs before passing to generators; generators do not perform secret scanning

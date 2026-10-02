# TeachX Agent Instructions

## Start here

Before substantial work, read `docs/HANDOFF.md`, `docs/roadmap.md`,
`docs/architecture.md`, `README.md`, and `docs/tutorials/README.md`.

Before writing, editing, or reviewing documentation, read
`docs/documentation-guide.md`.

## Documentation is part of done

Every task ends with a documentation decision:

- New user-visible behavior, configuration, API, architecture, or workflow:
  update the relevant Chinese tutorial and synchronize README, roadmap, and
  HANDOFF where applicable.
- Bug fix or behavior change: update the affected tutorial, troubleshooting,
  reference, or handoff material.
- Internal refactor or test-only change: no new tutorial is required, but check
  existing documentation for drift, state the documentation decision in the
  final response, and update docs when the explanation is now inaccurate.

Do not call a task complete while its documentation is missing or stale.

## Audience

TeachX docs are written for a reader with basic programming knowledge but little
Web, Agent, database, or deployment experience. Use plain Chinese, define jargon
at first use, show the expected result of every command, and explain the why
before the internal implementation.

## Safety and verification

Never print or commit API keys, Auth Secrets, local account passwords, or other
secrets. Never delete `data/teachx.db` or knowledge source files without explicit
user confirmation. Automatic tests must use Mock providers and must not consume
real API credits.

Before claiming completion, run the applicable checks and report actual evidence,
including known unrelated failures when they exist.

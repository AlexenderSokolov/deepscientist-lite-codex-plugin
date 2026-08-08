# Third-Party Notices

## DBOS Transact for Python 2.29.0

Pinned runtime dependency for the Phase 1-4 managed durable-workflow controller.
Repository: https://github.com/dbos-inc/dbos-transact-py
License: MIT. No DBOS source code is vendored in this plugin.

Phase 4 adds no bundled runtime dependency. Its evidence, verification, review,
and release aggregation layers use the Python standard library, the existing
DBOS pin, and an externally supplied Codex host. Codex is not redistributed by
this controller package.

## Architecture references

OpenSymphony (MIT) and codex-sidecar (MIT) inform thread and response-gap
terminology only. Dagu (GPL-3.0) is reference-only; no Dagu code is copied,
linked, or bundled.

## Additional architecture and protocol references

`codex-autoresearch` (MIT), Temporal (MIT), Prefect (Apache-2.0), LangGraph
(MIT), and Pueue (MIT OR Apache-2.0) are acknowledged as reference-only
projects. No source code, tests, binaries, or assets from them are copied or
bundled. OpenAI Codex (Apache-2.0) is the authority for the generated Hook and
app-server protocol schema pinned for this spike; no Codex source is vendored.

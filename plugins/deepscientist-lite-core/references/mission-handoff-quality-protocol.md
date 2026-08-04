# Mission Handoff Quality Protocol

## Purpose

This protocol implements the six-stage Handoff (offer, accept, execute,
return, integrate, close), seven quality gates G0-G6, Quality Contract,
and Review Package for DS Lite v6.

## Schema: ds-lite.mission-handoff-quality.v1

### Six-Stage Handoff

1. **offer**: Mission is offered to DS Lite
2. **accept**: DS Lite accepts the mission
3. **execute**: DS Lite executes the mission
4. **return**: DS Lite returns the results
5. **integrate**: Results are integrated (returned != integrated)
6. **close**: Mission is closed

Key rule: `returned` does not equal `integrated`. Integration is a
separate phase that requires explicit confirmation.

### Seven Quality Gates

- **G0-identity**: Identity and authorization
- **G1-requirements**: Requirements coverage
- **G2-security-privacy**: Security and privacy
- **G3-license-supply-chain**: License and supply chain
- **G4-engineering-quality**: Engineering quality
- **G5-scientific-method**: Scientific method
- **G6-release-readiness**: Release readiness

Key rule: `unknown` or `not-run` gates cannot aggregate into `pass`.

### Risk Levels

- **Q0**: No risk
- **Q1**: Low risk
- **Q2**: Medium risk
- **Q3**: High risk
- **Q4**: Critical risk

### Review Package

The Review Package aggregates findings from multiple reviewers and
preserves disagreements. Each finding has:

- `finding_id`: Unique identifier
- `severity`: blocker, critical, major, minor, info
- `status`: open, addressed, wont-fix, false-positive, deferred
- `description`: Human-readable description

The overall verdict is `blocked` if any blocker or critical finding is
open, otherwise `pass`.

### Mission Order

The Mission Order is a versioned JSON document that defines:

- `mission_id`: Unique mission identifier
- `project_id`: Project identifier
- `objective`: Mission objective
- `non_goals`: What the mission does not aim to achieve
- `owner_id`: Mission owner
- `budget`: Resource budget
- `acceptance_criteria`: Criteria for mission success
- `stop_conditions`: Conditions for stopping the mission
- `authority_digest`: Digest of the authorizing authority
- `status`: Current mission status
# Claim Evidence Chain Protocol

## Purpose

This protocol defines how atomic claims are bound to their evidence at
creation time. Each claim must have a stable selector, a transformation
chain, a dependence group, executed code reference, and an independent
verifier.

## Schema: ds-lite.chain-of-evidence.v1

### Selector Types

- `file-range`: A range within a file
- `cell-range`: A range of cells in a spreadsheet
- `line-range`: A range of lines in a code file
- `json-path`: A JSONPath expression
- `xpath`: An XPath expression
- `regex-match`: A regular expression match
- `commit-hash`: A git commit hash
- `artifact-ref`: A reference to an artifact

### Transformation Types

- `identity`: No transformation (direct read)
- `aggregation`: Aggregation of multiple values
- `filtering`: Filtering of data
- `normalization`: Normalization of data
- `statistical-test`: Statistical test
- `machine-learning`: Machine learning inference
- `manual-annotation`: Manual annotation
- `code-execution`: Code execution
- `data-join`: Data join
- `custom`: Custom transformation

### Dependence Types

- `shared-dataset`: Claims share the same dataset
- `shared-code`: Claims share the same code
- `shared-author`: Claims share the same author
- `shared-derivation`: Claims share the same derivation chain
- `shared-method`: Claims share the same method
- `independent`: Claims are independent

## Validation Rules

1. **Missing selector**: Claim without a selector is blocked
2. **Missing evidence refs**: Claim without evidence references is blocked
3. **Missing executed code ref**: Claim without executed code reference is blocked
4. **Missing verifier**: Claim without a verifier is blocked
5. **Missing dependence group**: Claim without a dependence group is blocked
6. **Empty transformation chain**: Triggers warning (identity transform may be implicit)
7. **Shared dependencies**: When detected, triggers warning

## Dependency Audit

The `check_dependency_group` function detects when multiple claims share
the same dependence group, indicating they are not independent evidence.
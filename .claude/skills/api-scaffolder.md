---
name: api-scaffolder
description: >
  Generates complete API endpoint code: route handler, request/response types, 
  validation, error handling, and unit tests — all matching existing codebase 
  patterns. Triggers on: "scaffold an endpoint", "create an API route for", 
  "add an endpoint", "generate the route for", "create a CRUD for".
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash(find * -name "*.ts" -o -name "*.py" -o -name "*.js" -not -path "*/node_modules/*")
  - Bash(rg *)
  - Bash(cat *)
---

# API Scaffolder Skill

## Process

1. **Read existing patterns first** (this is non-negotiable):
   - Find 2-3 existing route handlers: `rg "router\." --type ts -l` or equivalent
   - Read them completely — understand the exact pattern used
   - Find the validation approach: zod? joi? pydantic? custom?
   - Find how errors are returned — consistent error shape?
   - Find how auth is applied — middleware? decorator?

2. **Gather endpoint spec from user** (ask if not provided):
   - HTTP method + path
   - Authentication required? Which roles?
   - Request body/query params schema
   - Response schema (success + all error cases)
   - Any business logic to include

3. **Generate — match patterns exactly**:
   - Route handler (following existing file structure)
   - Request/response types (TypeScript interfaces or Python models)
   - Validation schema (same library as existing code)
   - Error responses (same shape as existing errors)
   - Unit tests (same testing framework, same mock patterns)
   - Update router registration file

4. **Verify generated code**:
   - Types are complete (no `any`)
   - All error cases handled
   - Test covers happy path + validation error + auth error
   - Matches existing patterns exactly

## Output
Generated files listed with brief description of what each does.

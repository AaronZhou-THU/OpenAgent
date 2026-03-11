---
name: code-review
description: Perform thorough code reviews — security audits, performance analysis, correctness checks, maintainability scoring, dependency analysis, and language-specific anti-patterns for Python, JavaScript/TypeScript, Go, and Rust.
---

# Code Review Skill

Conduct comprehensive, structured code reviews. Covers security, correctness, performance, maintainability, and language-specific patterns.

## Review Process

1. **Understand context**: read the PR description, linked issues, related files
2. **Read top-down**: module structure → public API → implementation details
3. **Check each category**: security → correctness → performance → maintainability
4. **Write findings**: severity + location + description + suggested fix
5. **Verdict**: approve, request changes, or block

## Review Checklist

### 1. Security (Critical — review first)

```
[ ] Injection
    - SQL: raw string concatenation in queries? Use parameterized queries.
    - Command: user input in subprocess/os.system/exec? Use allowlists.
    - XSS: unescaped user content rendered in HTML? Use auto-escaping templates.
    - Path traversal: user input in file paths? Validate and use os.path.realpath().
    - Template injection: user input in template strings? Use sandboxed engines.
    - SSRF: user-controlled URLs in server requests? Validate against allowlist.

[ ] Authentication
    - Hardcoded credentials, API keys, or secrets in source code?
    - Weak password hashing? (Must use bcrypt/scrypt/argon2, never MD5/SHA-1)
    - JWT: proper signature verification? Short expiry? Refresh token rotation?
    - Session fixation: regenerate session ID after login?

[ ] Authorization
    - Missing access controls on endpoints?
    - Broken object-level auth: can user A access user B's resources?
    - Privilege escalation: can regular user perform admin actions?
    - IDOR: predictable IDs without ownership check?

[ ] Data Exposure
    - Sensitive data in logs (passwords, tokens, PII)?
    - Verbose error messages exposing internals to clients?
    - Debug endpoints or admin panels accessible in production?
    - Secrets in version control (.env files, private keys)?

[ ] Dependencies
    - Known CVEs in dependencies? (npm audit, pip-audit, cargo audit)
    - Typosquatting risk? (verify package names)
    - Pinned versions? (avoid floating ranges for critical deps)
```

### 2. Correctness

```
[ ] Logic Errors
    - Off-by-one errors in loops, slicing, pagination
    - Null/None/undefined handling: unguarded dereferences
    - Edge cases: empty collections, zero values, negative numbers, max int
    - Boolean logic: De Morgan violations, inverted conditions
    - Floating-point comparisons (use epsilon, not ==)

[ ] Concurrency
    - Race conditions: shared mutable state without synchronization
    - Deadlocks: lock ordering violations, nested locks
    - Async pitfalls: missing await, fire-and-forget without error handling
    - Thread safety: global/class variables mutated by multiple threads

[ ] Resource Management
    - Unclosed files, DB connections, HTTP clients, sockets
    - Missing try/finally or context managers (with/using/defer)
    - Memory leaks: growing caches without eviction, circular references
    - Connection pool exhaustion under load

[ ] Error Handling
    - Swallowed exceptions (bare except/catch with no action)
    - Missing error paths: what happens when the API/DB/file call fails?
    - Error propagation: is the original error preserved or lost?
    - Partial failure: if step 3 of 5 fails, are steps 1-2 rolled back?
    - Retry logic: exponential backoff? Max retries? Idempotency?

[ ] Data Integrity
    - Missing database transactions for multi-step mutations
    - Race between check-and-act (TOCTOU)
    - Inconsistent state after partial failure
    - Missing unique constraints, foreign keys, or CHECK constraints
```

### 3. Performance

```
[ ] Database
    - N+1 queries: loop with individual fetches → use JOIN or batch
    - Missing indexes on filtered/sorted/joined columns
    - SELECT *: fetch only needed columns
    - Unbounded queries: missing LIMIT on collection endpoints
    - Large transactions holding locks too long

[ ] Algorithmic
    - O(n²) or worse where O(n) or O(n log n) is possible
    - Repeated computation: cache expensive results
    - String concatenation in loops: use builder/join
    - Unnecessary copies of large data structures

[ ] I/O
    - Blocking I/O in async code (sync file/network calls in event loop)
    - Sequential HTTP calls that could be parallelized
    - Missing timeouts on external calls (HTTP, DB, Redis)
    - Large payloads without streaming/pagination

[ ] Caching
    - Repeated identical computations or API calls without memoization
    - Cache invalidation: is stale data handled?
    - Missing HTTP caching headers (ETag, Cache-Control)

[ ] Memory
    - Loading entire large files/datasets into memory
    - Unbounded in-memory collections (growing lists/dicts)
    - Large objects kept alive unnecessarily (closures capturing scope)
```

### 4. Maintainability

```
[ ] Naming & Clarity
    - Variable/function names describe purpose (not implementation)
    - Consistent naming conventions within the codebase
    - Abbreviations and acronyms are well-known or documented
    - No misleading names (e.g., getUser() that also modifies state)

[ ] Structure
    - Functions: single responsibility, under 50 lines, max 3 params preferred
    - Nesting: max 3 levels; extract helper functions for deep nesting
    - Files: one concern per file, under 500 lines preferred
    - No circular dependencies between modules

[ ] Duplication
    - Copy-pasted code blocks (extract shared function)
    - Similar logic across endpoints (extract middleware/decorator)
    - Repeated error handling patterns (extract error handler)

[ ] Dead Code
    - Unused imports, variables, functions, classes
    - Commented-out code blocks (delete — it's in version control)
    - Unreachable code after return/throw/break
    - Feature flags for long-shipped features

[ ] Tests
    - New code has corresponding tests
    - Tests cover happy path + error cases + edge cases
    - Tests are isolated (no shared mutable state, no ordering dependency)
    - Mocks/stubs are minimal and focused
    - No tests of implementation details (only behavior)
```

## Language-Specific Checks

### Python

```python
# WRONG — mutable default argument (shared across calls)
def add_item(item, items=[]):
    items.append(item)
    return items

# RIGHT
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items

# WRONG — bare except swallows KeyboardInterrupt, SystemExit
try:
    risky()
except:
    pass

# RIGHT — catch specific exceptions
try:
    risky()
except (ValueError, ConnectionError) as e:
    logger.error("Failed: %s", e)

# WRONG — blocking I/O in async function
async def get_data():
    data = open("file.txt").read()      # blocks the event loop
    resp = requests.get("http://...")    # blocks the event loop

# RIGHT
async def get_data():
    async with aiofiles.open("file.txt") as f:
        data = await f.read()
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://...")

# WRONG — string formatting with % for SQL (injection risk)
cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)

# RIGHT — parameterized query
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# Check for:
# - Type hints on public API (function signatures, return types)
# - Context managers for resource cleanup (with open, async with session)
# - __all__ for public module API
# - dataclass/pydantic instead of raw dicts for structured data
# - pathlib instead of os.path for file operations
```

### JavaScript / TypeScript

```javascript
// WRONG — == allows type coercion
if (value == null) ...
if (status == 200) ...

// RIGHT — strict equality
if (value === null || value === undefined) ...
if (status === 200) ...

// WRONG — unhandled promise rejection
async function doWork() {
  fetchData();  // missing await — unhandled rejection
}

// RIGHT
async function doWork() {
  await fetchData();
}

// WRONG — prototype pollution
function merge(target, source) {
  for (const key in source) {
    target[key] = source[key];  // __proto__, constructor are valid keys
  }
}

// RIGHT — check own property and blocklist dangerous keys
function merge(target, source) {
  for (const key of Object.keys(source)) {
    if (key === '__proto__' || key === 'constructor') continue;
    target[key] = source[key];
  }
}

// WRONG — RegExp DoS (catastrophic backtracking)
const re = /^(a+)+$/;  // exponential on "aaaaaaaaaaaaaaaaX"

// Check for:
// - TypeScript: no any/unknown without narrowing, no @ts-ignore without comment
// - React: missing dependency arrays in useEffect/useMemo/useCallback
// - React: state updates in render path (infinite loop)
// - Node: unhandled 'error' events on streams
// - No var declarations (use const/let)
// - Optional chaining for deep property access (obj?.foo?.bar)
```

### Go

```go
// WRONG — error ignored
data, _ := json.Marshal(obj)

// RIGHT — handle every error
data, err := json.Marshal(obj)
if err != nil {
    return fmt.Errorf("marshal object: %w", err)
}

// WRONG — goroutine leak (no way to stop)
go func() {
    for {
        doWork()
    }
}()

// RIGHT — cancellable via context
go func(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            return
        default:
            doWork()
        }
    }
}(ctx)

// Check for:
// - defer for resource cleanup (file.Close, mutex.Unlock, rows.Close)
// - Context propagation through call chain
// - sync.Mutex for shared state, sync.RWMutex for read-heavy
// - Struct field alignment (group by size to reduce padding)
// - Error wrapping with %w for errors.Is/As compatibility
// - No init() functions (hard to test, implicit ordering)
```

### Rust

```rust
// WRONG — unwrap in production code (panics on None/Err)
let value = map.get("key").unwrap();

// RIGHT — handle the error
let value = map.get("key").ok_or_else(|| AppError::NotFound("key"))?;

// Check for:
// - .unwrap() / .expect() only in tests, never in production paths
// - Clone usage: is it necessary? Can we borrow instead?
// - Lifetime annotations: are they minimal and correct?
// - Error types: use thiserror for library errors, anyhow for application errors
// - Unsafe blocks: justified, minimal, and well-documented?
// - Clippy warnings addressed (#[allow(clippy::...)] with reason)
```

## Dependency Analysis

```bash
# Python
pip-audit                                  # known CVEs
pip list --outdated                        # stale versions
pipdeptree                                 # dependency tree

# JavaScript
npm audit                                  # known CVEs
npx depcheck                               # unused dependencies
npm outdated                               # stale versions

# Go
go list -m -u all                          # outdated modules
govulncheck ./...                          # known vulnerabilities

# Rust
cargo audit                                # known CVEs
cargo outdated                             # stale versions
cargo deny check                           # license + advisory check

# General
grep -rn "TODO\|FIXME\|HACK\|XXX" .       # tech debt markers
grep -rn "password\|secret\|token\|api.key" . --include="*.py" --include="*.js" --include="*.ts" --include="*.go"
```

## Output Format

```markdown
## Code Review: [file/component/PR#]

### Summary
[1-2 sentence overview of what the change does and overall impression]

### Critical Issues (must fix before merge)
1. **[SECURITY] SQL injection in user search** (file.py:42)
   - Description: User input concatenated directly into SQL query
   - Impact: Attackers can read/modify/delete any data in the database
   - Fix: Use parameterized query: `cursor.execute("... WHERE name = %s", (name,))`

2. **[CORRECTNESS] Race condition in balance update** (account.py:78)
   - Description: Read-then-write without transaction or locking
   - Impact: Concurrent requests can cause double-spending
   - Fix: Wrap in SELECT ... FOR UPDATE or use atomic F-expression

### Warnings (should fix)
1. **[PERFORMANCE] N+1 query in order listing** (views.py:95)
   - Description: Loop fetching user for each order individually
   - Fix: Use `select_related('user')` or batch query
   - Impact: ~100ms per extra query, significant at scale

2. **[MAINTAINABILITY] 120-line function** (utils.py:30)
   - Description: `process_data()` handles parsing, validation, transformation, and saving
   - Fix: Extract into 4 focused functions

### Suggestions (nice to have)
1. **[STYLE] Inconsistent naming** (helpers.py:15)
   - `getUserData` mixed with `fetch_user_profile` — pick one convention
2. **[TEST] Missing edge case** (test_orders.py)
   - No test for empty cart checkout — add test for 0-item order

### Positive Notes
- Clean separation of concerns in the service layer
- Good use of type hints throughout
- Error messages are user-friendly and consistent

### Verdict
- [ ] Approve — ready to merge
- [x] Request changes — critical issues must be addressed
- [ ] Block — fundamental design problem, needs rethink

### Metrics
- Files reviewed: 12
- Critical issues: 2
- Warnings: 4
- Suggestions: 3
- Test coverage: ~78% (new code: 85%)
```

## Severity Definitions

| Severity | Meaning | Action |
|----------|---------|--------|
| **Critical** | Security vulnerability, data loss risk, crash in production | Must fix before merge |
| **Warning** | Performance issue, correctness risk, significant maintainability debt | Should fix before merge |
| **Suggestion** | Style improvement, minor optimization, readability enhancement | Optional, can be follow-up |
| **Note** | Observation, question, discussion point | No action required |

## Best Practices for Reviewers

1. **Review the diff, not the whole file** — focus on what changed and its immediate context
2. **Security first** — always check injection, auth, and data exposure before anything else
3. **One concern per comment** — don't combine unrelated feedback in a single comment
4. **Suggest, don't demand** — "Consider using X because Y" is better than "Change this to X"
5. **Praise good code** — call out clean patterns, good tests, thoughtful error handling
6. **Check tests** — tests are code too; review them for correctness and coverage
7. **Timebox** — spend ~15 min per 200 lines; diminishing returns after 60 min total
8. **Re-review** — after changes are made, verify the fix doesn't introduce new issues

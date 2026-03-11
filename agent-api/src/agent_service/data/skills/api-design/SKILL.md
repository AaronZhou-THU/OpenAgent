---
name: api-design
description: Design production-quality REST and GraphQL APIs — resource modeling, authentication, pagination, filtering, error handling, versioning, rate limiting, OpenAPI specs, and implementation patterns for FastAPI, Express, and Django.
---

# API Design Skill

Design and implement production-quality APIs. Covers REST conventions, authentication, pagination, error handling, OpenAPI specifications, and framework-specific patterns.

## Resource Naming

```
# Plural nouns for collections
GET    /api/v1/users
GET    /api/v1/users/{id}
POST   /api/v1/users
PUT    /api/v1/users/{id}
PATCH  /api/v1/users/{id}
DELETE /api/v1/users/{id}

# Nest for direct relationships (max 2 levels)
GET    /api/v1/users/{id}/orders
GET    /api/v1/users/{id}/orders/{order_id}

# Use kebab-case for multi-word resources
GET    /api/v1/order-items
GET    /api/v1/user-profiles

# Actions as sub-resources (not verbs in URL)
POST   /api/v1/orders/{id}/cancel        # not /api/v1/cancel-order
POST   /api/v1/users/{id}/reset-password
POST   /api/v1/reports/generate

# Singleton sub-resources
GET    /api/v1/users/{id}/profile         # one profile per user
PUT    /api/v1/users/{id}/settings
```

## HTTP Methods & Status Codes

| Method | Usage | Idempotent | Request Body | Response |
|--------|-------|------------|-------------|----------|
| GET | Read resource(s) | Yes | No | 200 + data |
| POST | Create resource | No | Yes | 201 + created resource + Location header |
| PUT | Full replace | Yes | Yes | 200 + updated resource |
| PATCH | Partial update | Yes | Yes | 200 + updated resource |
| DELETE | Remove resource | Yes | No | 204 (no body) |

### Status Code Reference

```
# Success
200 OK                  — GET, PUT, PATCH success
201 Created             — POST success (include Location header)
204 No Content          — DELETE success, PUT with no response body
206 Partial Content     — Range requests (file downloads)

# Redirection
301 Moved Permanently   — Resource URL changed (update clients)
304 Not Modified        — Conditional GET, client cache valid (ETag/If-None-Match)

# Client errors
400 Bad Request         — Malformed JSON, invalid syntax
401 Unauthorized        — Missing or invalid authentication
403 Forbidden           — Authenticated but not authorized
404 Not Found           — Resource does not exist
405 Method Not Allowed  — Valid URL, wrong HTTP method
409 Conflict            — Duplicate key, state violation, optimistic lock failure
413 Payload Too Large   — Request body exceeds limit
415 Unsupported Media   — Wrong Content-Type
422 Unprocessable       — Valid JSON but fails validation (prefer over 400 for field errors)
429 Too Many Requests   — Rate limited (include Retry-After header)

# Server errors
500 Internal Error      — Unexpected server failure
502 Bad Gateway         — Upstream service down
503 Service Unavailable — Server overloaded (include Retry-After)
504 Gateway Timeout     — Upstream service timeout
```

## Request/Response Envelope

### Standard Response

```json
{
  "data": {
    "id": "usr_abc123",
    "email": "alice@example.com",
    "name": "Alice",
    "role": "admin",
    "created_at": "2024-12-15T09:30:00Z"
  }
}
```

### Collection Response with Pagination

```json
{
  "data": [
    {"id": "usr_abc123", "name": "Alice"},
    {"id": "usr_def456", "name": "Bob"}
  ],
  "meta": {
    "page": 2,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  },
  "links": {
    "self": "/api/v1/users?page=2&per_page=20",
    "first": "/api/v1/users?page=1&per_page=20",
    "prev": "/api/v1/users?page=1&per_page=20",
    "next": "/api/v1/users?page=3&per_page=20",
    "last": "/api/v1/users?page=8&per_page=20"
  }
}
```

### Error Response

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {"field": "email", "message": "Invalid email format"},
      {"field": "age", "message": "Must be between 1 and 150"}
    ],
    "request_id": "req_7f3a2b1c"
  }
}
```

### Error Code Catalog (define per-domain)

```python
# errors.py — machine-readable error codes
ERRORS = {
    "VALIDATION_ERROR":     (422, "Request validation failed"),
    "NOT_FOUND":            (404, "Resource not found"),
    "DUPLICATE":            (409, "Resource already exists"),
    "UNAUTHORIZED":         (401, "Authentication required"),
    "FORBIDDEN":            (403, "Insufficient permissions"),
    "RATE_LIMITED":         (429, "Too many requests"),
    "INTERNAL_ERROR":       (500, "Internal server error"),
    # Domain-specific
    "INSUFFICIENT_BALANCE": (422, "Account balance too low"),
    "ORDER_ALREADY_SHIPPED":(409, "Cannot modify a shipped order"),
}
```

## Pagination Strategies

### Offset-Based (simple, allows page jumping)

```
GET /api/v1/users?page=3&per_page=25

# Backend: SELECT * FROM users ORDER BY id LIMIT 25 OFFSET 50
# Good for: admin dashboards, small datasets
# Problem: page drift on inserts, slow at high offsets
```

### Cursor-Based (stable, performant for large datasets)

```
GET /api/v1/events?limit=25&after=evt_abc123

{
  "data": [...],
  "meta": { "has_more": true },
  "cursors": {
    "after": "evt_xyz789"
  }
}

# Backend: SELECT * FROM events WHERE id > 'evt_abc123' ORDER BY id LIMIT 25
# Good for: feeds, timelines, real-time data, infinite scroll
# Problem: no page jumping, no total count
```

### Keyset-Based (for sorted results)

```
GET /api/v1/posts?limit=25&sort=-created_at&after_created_at=2024-12-01T00:00:00Z&after_id=post_abc

# Backend: WHERE (created_at, id) < ('2024-12-01', 'post_abc') ORDER BY created_at DESC, id DESC LIMIT 25
```

## Filtering, Sorting, Field Selection

```
# Filtering — query params matching field names
GET /api/v1/users?role=admin&active=true&created_after=2024-01-01

# Range filters
GET /api/v1/products?price_min=10&price_max=100

# Multiple values (comma-separated)
GET /api/v1/orders?status=pending,processing

# Sorting (prefix - for descending)
GET /api/v1/users?sort=-created_at,name

# Field selection (sparse fieldsets)
GET /api/v1/users?fields=id,name,email

# Search (full-text)
GET /api/v1/users?q=alice

# Combined
GET /api/v1/products?category=electronics&price_min=50&sort=-rating&fields=id,name,price&page=1&per_page=20
```

## Authentication & Authorization

### JWT Bearer Token

```
# Client sends
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

# Token payload
{
  "sub": "usr_abc123",
  "role": "admin",
  "exp": 1734567890,
  "iat": 1734481490
}
```

### API Key (server-to-server)

```
# Header-based (preferred)
X-API-Key: sk_live_abc123def456

# Query param (avoid — leaks in logs)
GET /api/v1/data?api_key=sk_live_abc123def456
```

### OAuth 2.0 Scopes

```
# Token request with scopes
POST /oauth/token
{
  "grant_type": "authorization_code",
  "code": "auth_code_here",
  "scope": "read:users write:orders"
}

# Endpoint requires specific scope
@require_scope("write:orders")
def create_order(request): ...
```

## Rate Limiting

```
# Response headers
X-RateLimit-Limit: 100        # requests per window
X-RateLimit-Remaining: 42     # requests left
X-RateLimit-Reset: 1734567890 # window reset (Unix timestamp)
Retry-After: 30               # seconds until retry (on 429)
```

### Rate limit tiers

```python
RATE_LIMITS = {
    "free":       "100/hour",
    "pro":        "1000/hour",
    "enterprise": "10000/hour",
}
# Apply per-user, per-endpoint, or per-API-key
```

## Versioning

### URL versioning (recommended — explicit, cacheable)

```
GET /api/v1/users
GET /api/v2/users
```

### Header versioning (cleaner URLs, harder to test)

```
Accept: application/vnd.myapi.v2+json
```

### Versioning rules

```
# Breaking changes → new version
- Removing a field
- Renaming a field
- Changing a field type
- Changing URL structure
- Changing authentication method

# Non-breaking changes → same version
- Adding a new optional field
- Adding a new endpoint
- Adding a new query parameter
- Adding a new enum value (if clients handle unknown values)
```

## OpenAPI / Swagger Specification

```yaml
openapi: 3.1.0
info:
  title: My API
  version: 1.0.0
  description: Production API for user management

servers:
  - url: https://api.example.com/v1
    description: Production
  - url: https://staging-api.example.com/v1
    description: Staging

paths:
  /users:
    get:
      summary: List users
      operationId: listUsers
      tags: [Users]
      parameters:
        - name: page
          in: query
          schema: { type: integer, default: 1, minimum: 1 }
        - name: per_page
          in: query
          schema: { type: integer, default: 20, minimum: 1, maximum: 100 }
        - name: role
          in: query
          schema: { type: string, enum: [admin, user, viewer] }
      responses:
        '200':
          description: Paginated user list
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/User' }
                  meta:
                    $ref: '#/components/schemas/PaginationMeta'
        '401':
          $ref: '#/components/responses/Unauthorized'

    post:
      summary: Create user
      operationId: createUser
      tags: [Users]
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreateUserRequest' }
      responses:
        '201':
          description: User created
          headers:
            Location:
              schema: { type: string }
              description: URL of created resource
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: '#/components/schemas/User' }
        '422':
          $ref: '#/components/responses/ValidationError'

components:
  schemas:
    User:
      type: object
      properties:
        id: { type: string, example: "usr_abc123" }
        email: { type: string, format: email }
        name: { type: string }
        role: { type: string, enum: [admin, user, viewer] }
        created_at: { type: string, format: date-time }
      required: [id, email, name, role, created_at]

    CreateUserRequest:
      type: object
      properties:
        email: { type: string, format: email }
        name: { type: string, minLength: 1, maxLength: 100 }
        role: { type: string, enum: [admin, user, viewer], default: user }
      required: [email, name]

    PaginationMeta:
      type: object
      properties:
        page: { type: integer }
        per_page: { type: integer }
        total: { type: integer }
        total_pages: { type: integer }

  responses:
    Unauthorized:
      description: Authentication required
      content:
        application/json:
          schema:
            type: object
            properties:
              error:
                type: object
                properties:
                  code: { type: string, example: "UNAUTHORIZED" }
                  message: { type: string }

    ValidationError:
      description: Validation failed
      content:
        application/json:
          schema:
            type: object
            properties:
              error:
                type: object
                properties:
                  code: { type: string, example: "VALIDATION_ERROR" }
                  message: { type: string }
                  details:
                    type: array
                    items:
                      type: object
                      properties:
                        field: { type: string }
                        message: { type: string }

  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - BearerAuth: []
```

## FastAPI Implementation

```python
from fastapi import FastAPI, Query, Path, HTTPException, Depends, status
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

app = FastAPI(title="My API", version="1.0.0")

# --- Schemas ---

class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="user", pattern="^(admin|user|viewer)$")

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: datetime

class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int

class UserListResponse(BaseModel):
    data: list[UserResponse]
    meta: PaginationMeta

class ErrorDetail(BaseModel):
    field: str | None = None
    message: str

class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []

class ErrorResponse(BaseModel):
    error: ErrorBody

# --- Error handler ---

class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []

@app.exception_handler(APIError)
async def api_error_handler(request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )

# --- Endpoints ---

@app.get("/api/v1/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    role: str | None = Query(None, pattern="^(admin|user|viewer)$"),
    sort: str = Query("created_at", pattern="^-?(created_at|name|email)$"),
    q: str | None = Query(None, min_length=1, max_length=100),
):
    # Build query from params, paginate, return
    ...

@app.post("/api/v1/users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate):
    # Validate, create, return with Location header
    ...

@app.get("/api/v1/users/{user_id}", response_model=dict)
async def get_user(user_id: str = Path(pattern="^usr_[a-z0-9]+$")):
    ...

@app.patch("/api/v1/users/{user_id}", response_model=dict)
async def update_user(user_id: str, body: UserUpdate):
    ...

@app.delete("/api/v1/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str):
    ...
```

## Express.js Implementation

```javascript
const express = require('express');
const router = express.Router();

// Middleware — standard error wrapper
const asyncHandler = (fn) => (req, res, next) =>
  Promise.resolve(fn(req, res, next)).catch(next);

// GET /api/v1/users
router.get('/users', asyncHandler(async (req, res) => {
  const { page = 1, per_page = 20, role, sort = 'created_at', q } = req.query;

  const { users, total } = await userService.list({ page, per_page, role, sort, q });

  res.json({
    data: users,
    meta: {
      page: Number(page),
      per_page: Number(per_page),
      total,
      total_pages: Math.ceil(total / per_page),
    },
  });
}));

// POST /api/v1/users
router.post('/users', asyncHandler(async (req, res) => {
  const user = await userService.create(req.body);
  res.status(201)
    .location(`/api/v1/users/${user.id}`)
    .json({ data: user });
}));

// Global error handler
app.use((err, req, res, next) => {
  const status = err.statusCode || 500;
  res.status(status).json({
    error: {
      code: err.code || 'INTERNAL_ERROR',
      message: err.message,
      details: err.details || [],
      request_id: req.id,
    },
  });
});
```

## Best Practices

1. **Version from day one**: `/api/v1/` — changing later is painful
2. **Consistent envelope**: always `{"data": ..., "meta": ...}` for collections, `{"data": ...}` for singles
3. **Use prefixed IDs**: `usr_abc123`, `ord_def456` — self-documenting, prevents cross-resource confusion
4. **Validate at the boundary**: never trust client input; validate types, ranges, formats, lengths
5. **Idempotency keys**: for POST/mutation endpoints, accept `Idempotency-Key` header to prevent double-processing
6. **Pagination defaults**: always paginate collections; default `per_page=20`, max `per_page=100`
7. **ISO 8601 dates**: always `2024-12-15T09:30:00Z` — never Unix timestamps in API responses
8. **ETag/If-None-Match**: for GET caching; `If-Match` for optimistic concurrency on PUT/PATCH
9. **Request IDs**: generate and return `X-Request-Id` on every response for debugging
10. **CORS**: configure explicitly per-origin, never `Access-Control-Allow-Origin: *` in production
11. **Content negotiation**: require `Content-Type: application/json`, reject others with 415
12. **Graceful deprecation**: `Sunset` header + docs notice before removing endpoints

# API

41 endpoints under `/api/v1`, plus `/health`. Interactive documentation is
served at `/docs` in development and **disabled in production** — the schema
describes the whole business surface and there is no reason to publish it.

## Conventions

**Money is integer cents** in every request and response
(`total_price_cents: 33600` is $336.00). No floats cross the wire. Percentages
are basis points (`2000` is 20%).

**Customers are identified by a session token**, not an account. `POST
/design-sessions` returns one; it goes in the path. Only its SHA-256 hash is
stored, so a leaked database does not yield working tokens.

**Admins send a bearer token** obtained from `POST /admin/auth/session`. A
valid Supabase token is not enough — the account also needs an active
`admin_profiles` row, or the answer is 403.

**Errors share one envelope:**

```json
{
  "error": {
    "code": "DATE_FULL",
    "message": "That date is fully booked.",
    "details": {"next_available": ["2026-08-16", "2026-08-17", "2026-08-18"]}
  }
}
```

| Status | Means |
|---|---|
| 400 | malformed request |
| 401 | missing or invalid admin token |
| 403 | authenticated but not an administrator |
| 404 | unknown token, order number or id |
| 409 | the business rejected it — full date, revision limit, illegal status change |
| 422 | the request shape failed validation |
| 429 | rate limited |

409 is the interesting one: the request was well-formed and the **business**
said no. `details` always says which rule.

## Public endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/availability` | Capacity calendar |
| `POST` | `/api/v1/availability/check` | Check one date |
| `GET` | `/api/v1/catalog` | Full public catalog |
| `POST` | `/api/v1/delivery/calculate` | Zone and fee for an address |
| `POST` | `/api/v1/design-sessions` | Start a design session |
| `GET` | `/api/v1/design-sessions/{token}` | Resume a saved design |
| `GET` | `/api/v1/design-sessions/{token}/designs` | All design versions |
| `POST` | `/api/v1/design-sessions/{token}/designs/{design_id}/approve` | Approve a design version |
| `POST` | `/api/v1/design-sessions/{token}/generate-design` | Create the first design |
| `POST` | `/api/v1/design-sessions/{token}/messages` | Send a message to the assistant |
| `POST` | `/api/v1/design-sessions/{token}/orders` | Place the order |
| `POST` | `/api/v1/design-sessions/{token}/revisions` | Request a change to the design |
| `GET` | `/api/v1/design-sessions/{token}/specification` | Current structured specification |
| `PATCH` | `/api/v1/design-sessions/{token}/specification` | Edit the specification directly |
| `POST` | `/api/v1/design-sessions/{token}/uploads` | Upload an inspiration or personal image |
| `POST` | `/api/v1/design-sessions/{token}/validate` | Confirm the specification before design |
| `GET` | `/api/v1/orders/{order_number}` | Look up an order |
| `POST` | `/api/v1/pricing/calculate` | Price a specification |
| `GET` | `/health` | Liveness and dependency check |

### The flow

```
POST /design-sessions                     → token
POST /design-sessions/{token}/messages     → conversation, repeat until complete
GET  /design-sessions/{token}/specification
POST /design-sessions/{token}/validate      → feasibility + price, the gate
POST /design-sessions/{token}/generate-design
GET  /design-sessions/{token}/designs       → poll until status is ready
POST /design-sessions/{token}/revisions     → at most 3, enforced server-side
POST /design-sessions/{token}/designs/{id}/approve
POST /design-sessions/{token}/orders        → order number
```

Image generation is **asynchronous**: `generate-design` returns immediately
with a design row whose `status` is `generating`. Poll `GET .../designs`. With
a live provider this takes about a minute.

`/pricing/calculate` and `/availability/check` are the same engines the order
path uses, exposed so a price can be shown during the conversation without
risk of the quote and the invoice disagreeing.

## Admin endpoints

All require a bearer token and an active admin profile.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/admin/audit-log` | Recent administrative actions |
| `POST` | `/api/v1/admin/auth/session` | Sign in |
| `DELETE` | `/api/v1/admin/auth/session` | Sign out |
| `GET` | `/api/v1/admin/availability` | Capacity calendar |
| `PATCH` | `/api/v1/admin/availability/{day}` | Set capacity for a date |
| `GET` | `/api/v1/admin/catalog/{catalog_type}` | List catalog items |
| `POST` | `/api/v1/admin/catalog/{catalog_type}` | Create a catalog item |
| `PATCH` | `/api/v1/admin/catalog/{catalog_type}/{item_id}` | Update a catalog item |
| `DELETE` | `/api/v1/admin/catalog/{catalog_type}/{item_id}` | Deactivate a catalog item |
| `GET` | `/api/v1/admin/customers` | Customer records |
| `GET` | `/api/v1/admin/customers/{customer_id}` | One customer and their orders |
| `GET` | `/api/v1/admin/dashboard` | Today at the atelier |
| `GET` | `/api/v1/admin/me` | Who am I |
| `GET` | `/api/v1/admin/orders` | Order list with filters |
| `GET` | `/api/v1/admin/orders/{order_id}` | Full order detail |
| `POST` | `/api/v1/admin/orders/{order_id}/approve` | Approve a special order |
| `POST` | `/api/v1/admin/orders/{order_id}/notes` | Add an internal note |
| `PATCH` | `/api/v1/admin/orders/{order_id}/price` | Override the price |
| `POST` | `/api/v1/admin/orders/{order_id}/reject` | Reject an order |
| `POST` | `/api/v1/admin/orders/{order_id}/status` | Change order status |
| `GET` | `/api/v1/admin/settings` | All settings |
| `PATCH` | `/api/v1/admin/settings/{key}` | Change a setting |

Two worth noting:

`GET /admin/dashboard` returns **four separate money figures** — order value,
paid, outstanding, estimated. They are never added together, because summing a
confirmed price with an estimate produces a number that means nothing.

`PATCH /admin/orders/{id}/price` requires a reason and writes the previous
price, the new price, the administrator and the timestamp to `audit_log`. There
is no way to change a price without leaving that trail.

## Rate limits

Per IP, in-process. Conversation and generation endpoints are limited more
tightly than reads because each one costs an API call to a paid provider.

*Ceiling:* in-process counters reset on restart and are not shared between
replicas. Correct for one instance; a second replica needs Redis.

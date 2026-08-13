# Design system and screens

## Source of truth

The visual design system is produced in **Stitch**, not invented in CSS.

| Item | Value |
|---|---|
| Stitch project | `2064497605592133162` — "Mayan's Cake Factory" |
| Design system asset | `assets/2131526806607800438` — "Maison Mayan — Parisian Patisserie" |
| Status | ✅ created and applied to the project |

`frontend/static/css/tokens.css` mirrors that design system. When a token changes,
change it in Stitch first and mirror it here, so the two do not drift.

### Tokens

| Token | Value | Role |
|---|---|---|
| Primary | `#8C6239` | caramel, primary actions |
| Secondary | `#C9A227` | antique gold, dividers and price emphasis only |
| Tertiary | `#C98B84` | soft rose, decorative accents |
| Paper | `#FDFBF8` | page background |
| Ink | `#2C2320` | text, warm brown — never pure black |
| Radius | `8px` | `ROUND_EIGHT` |
| Headline | Playfair Display | page titles, cake names |
| Body | DM Sans | everything else |

## Screen generation — how it actually behaves

Generation **works**, but the MCP call almost always returns
`The operation timed out` before the job finishes. The job still completes
server-side. An earlier note in this file claimed generation was blocked and that
zero screens existed; that was wrong, and this correction records why.

### What misled the diagnosis

- `generate_screen_from_text` times out on response delivery even when the job succeeds.
- `list_screens` returns `{}` or `Request contains an invalid argument` **while a job
  is running**, which made it look as though nothing had been created.
- Only after the queue drained did all the earlier screens appear at once.

### The working procedure

1. Call `generate_screen_from_text` for **one** screen.
2. Expect a timeout. Do not retry — a retry starts a second job and both slow down.
3. Wait roughly 60–120 seconds.
4. Call `list_screens` and collect the new screen.
5. Only then start the next screen.

> [!important] One job at a time per project
> Firing a second generation while one is in flight returns
> `Request contains an invalid argument`. Screens must be generated sequentially.

### Why generation appeared to stop — corrected diagnosis

An earlier note here concluded that generation had stopped on a **usage quota**.
That was wrong, and the correction is worth keeping because the wrong diagnosis
was reasonable and still misleading.

What actually happened: the requests were **queued, not rejected**. The Stitch
project had hit a **stored-asset limit**, so new work sat in the queue
indefinitely. Freeing space in the Stitch UI drained it, and four screens that
had "failed" hours earlier — three chat variants and the admin dashboard —
appeared at once.

> [!important] A timeout means nothing about success or failure
> `generate_screen_from_text` almost always times out. The job may complete
> seconds later, minutes later, or only once storage frees up. **Never retry on
> a timeout** — each retry queues another job, which is why three identical chat
> screens exist.

**If generation seems stuck:** check stored assets in the Stitch UI and delete
what is not needed, rather than waiting for a quota window that does not exist.

## Screens generated so far

| Screen | ID | Size |
|---|---|---|
| Home page (full) | `2dd1f749469844d9822590b711291446` | 2560 × 8294 |
| Home page (condensed variant) | `0776f1169c1b4fec8f06f1ec6b6a09bf` | 2560 × 2310 |
| Order confirmation | `ace814083f944a5a979ff1c6ddddb51f` | 2560 × 2990 |
| Bakery staff sign-in | `3189eb4070f7409da1bdfeef4c535a9d` | 2560 × 2048 |
| Wordmark asset | `51eae36eb3c840f59a3e7a41bc867df9` | 1024 × 1024 |
| Hero cake photograph | `7253ca5af15c444a9d9707c29568e785` | 848 × 1264 |

### Still to generate

**Customer:** AI design conversation · specification summary · design preview with
revisions · fulfilment

**Admin:** dashboard · order list · order detail · catalog · availability · settings

Plus mobile variants of the key customer screens.

Prompts for all of them are in `docs/design/screen-briefs.md`.

## Retrieving a screen

```bash
# htmlCode.downloadUrl and screenshot.downloadUrl come from list_screens
curl -sL -o screen.html "<htmlCode.downloadUrl>"
```

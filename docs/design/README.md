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

## Screen generation — BLOCKED

Screen generation through Stitch is **not currently working**. Three attempts on
2026-08-12 all timed out and registered no screen:

| Attempt | Prompt | Model | Result |
|---|---|---|---|
| 1 | Home page, long detailed prompt | Gemini 3.1 Pro | timeout, no screen |
| 2 | Home page, condensed prompt | default | timeout, no screen |
| 3 | Order confirmation, minimal prompt | Gemini 3 Flash | timeout, no screen |

The project's `updateTime` advanced on each attempt (19:26 → 19:28 → 19:29) and the
design system was applied successfully, so the service is reachable and accepting
requests — but `screenInstances` stays empty and `list_screens` returns either `{}`
or `Request contains an invalid argument`. Prompt length is not the cause, since the
minimal prompt failed identically.

> [!important]
> Screens are **not** being hand-designed as a workaround. The specification is
> explicit that layouts must come from Stitch, and inventing them here would
> quietly violate that. The design tokens above are a legitimate exception because
> Stitch genuinely produced them.

### Screens still to generate

**Customer:** home · AI design conversation · specification summary · design preview
with revisions · fulfilment (pickup/delivery) · order confirmation

**Admin:** login · dashboard · order list · order detail · catalog management ·
availability and capacity · settings

Each in desktop and mobile.

### To retry

```
mcp__stitch__generate_screen_from_text
  projectId:     2064497605592133162
  designSystem:  assets/2131526806607800438
  deviceType:    DESKTOP | MOBILE
```

Prompts for all 13 screens are kept in `docs/design/screen-briefs.md`, so a retry
does not mean rewriting them.

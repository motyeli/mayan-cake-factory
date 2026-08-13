# Assumptions and open questions

Everything here is a decision made without being told, or a question that needs
Mayan's answer. None of it is hidden in code comments.

## Assumptions made

| Assumption | Why | If wrong |
|---|---|---|
| USD display currency | the business price range was given in dollars | `currency` is a setting; the schema stores cents and a currency code |
| `Europe/Paris` timezone | the bakery is in Paris | a setting |
| English only | spec §1 | no i18n scaffolding was added, so this is a real change |
| Bakery coordinates ≈ Eiffel Tower | the exact address was never given | env + settings, never hard-coded |
| Guests, no customer accounts | spec §6 | the CRM already stores customers, so accounts are additive |
| A size **is** a tier count | Medium is a single-tier cake | asking for 2 tiers on a Medium is refused with a suggestion |
| Straight-line distance for zones | no routing API configured | under-estimates a real route, so boundaries are generous to the customer |
| Three representative prices on the home page | picked from real catalog rows, not hard-coded | changes automatically with the catalog |

## Open questions for Mayan

**Deposit policy.** The schema has `deposit_required` and
`deposit_amount_cents`, but no rule sets them. Is a deposit wanted, and above
what value?

**Fondant pricing.** The spec gives a $40–$150 range. It is modelled as $40 plus
a size-scaled rule. Does that match how it is actually quoted?

**Data retention.** GDPR requires a defined period. How long should design
sessions, conversations and uploaded photographs be kept after an order
completes?

**Shared time slots.** Collection and delivery currently use the same four
windows. Do delivery windows differ?

**Rush surcharge.** Seeded at 20% under 48 h and 35% under 24 h. Real numbers?

**Complexity multipliers.** 1.0 / 1.2 / 1.5 come from the spec. Do they reflect
actual extra labour?

## Deliberate scope exclusions

Native apps · multiple bakeries · customer accounts · online payment · coupons ·
loyalty · GPS tracking · WhatsApp · email notifications · reviews · 3D/AR ·
full inventory · driver portal · multiple languages.

Each was excluded to keep the MVP shippable. Re-scoping is Mayan's call, but
none of these is a small addition.

## Known incomplete work

- **Fulfilment page** — the API works (`/delivery/calculate`,
  `/availability/check`, order creation); there is no page for choosing a date,
  slot and address. The order flow currently goes through the API directly.
- **Catalog and availability admin screens** — APIs work, no pages. Acceptance
  criteria 24 and 25 are satisfied at the API level only.
- **Fonts not self-hosted** — system fallbacks are used to avoid a Google Fonts
  request. The design is not yet typographically faithful.
- **Three Stitch screens were never generated** — fulfilment, admin order list
  and admin order detail. The latter two were built by extending the admin
  design language Stitch produced for the dashboard.

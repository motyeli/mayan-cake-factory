# Screen briefs

Ready-to-send prompts for `mcp__stitch__generate_screen_from_text`.
Always pass `designSystem: assets/2131526806607800438` so every screen inherits
the Maison Mayan system. Generate each in `DESKTOP` and `MOBILE`.

Written against spec §8 (customer screens) and §32–§34 (admin screens). Every brief
states the real content, because a screen designed around placeholder text hides the
layout problems that real content causes — long cake names, five decorations, a
missing price.

---

## Customer

### C1 · Home

> Home page for a premium Paris custom cake atelier, "Mayan's Cake Factory". Customers design and order a bespoke cake remotely.
>
> Slim header with wordmark and a "Design Your Cake" button. Hero with headline "Design your cake, from anywhere", a short sub-line, a primary "Design Your Cake" button, the note "Free to design. No account needed.", and a tall rounded photo of an elegant flower-topped cake on a neutral studio background. A four-step "How it works" row: Describe it, We shape it, See it, Order it. A grid of seven cake style cards with photos: Minimalist, Floral, Birthday, Luxury, Wedding and Engagement, Corporate, Photo and Illustration. A pricing band showing "from $100" for 6–8 servings, "from $260" for 16–20, "from $950" for 50–70, with a note that the full breakdown is shown before ordering. Two fulfilment cards: free atelier collection in two-hour windows, and Paris delivery at $25 / $45 / $75 by distance zone. A five-item FAQ accordion. A calm bordered note: "Generated cake images are visual representations. Handmade cakes may include minor variations in colour, texture, shape and decoration." Footer with address, hours and policy links.
>
> Warm off-white paper, deep warm brown text, caramel buttons, gold only for thin dividers and price emphasis. Elegant, calm, generous whitespace. Not futuristic, no AI or robot iconography.

### C2 · AI design conversation

> Two-column cake design screen for a Paris cake atelier.
>
> Left, about two thirds width: a conversation. Assistant messages left-aligned on white cards with a thin border; customer messages right-aligned on a soft caramel tint. Show a real exchange: assistant asks "Tell me about the cake you would like to create", customer replies about a 20-person birthday in September, assistant recommends a Medium size and asks about flavour, customer sends an inspiration photo shown as a small rounded thumbnail with the caption "Inspiration — a design direction, not an exact copy". Below the thread, a text input with an image-upload button, a send button, and three suggested quick replies as outlined chips: "Something floral", "Not sure about flavour", "It is for a wedding".
>
> Right, a sticky panel: heading "Your cake so far". A running specification list — Event, Date, Servings, Size, Shape, Tiers, Flavour, Filling, Frosting, Style, Colours, Decorations, Inscription, Dietary, Collection or delivery. Known values in normal text; unknown ones show a muted "Not chosen yet". Under it, a bordered price block reading "Estimated so far $340" with a "See breakdown" text link. Under that, a small availability line with a green dot: "12 September has capacity". At the bottom a primary button "Review full specification", disabled-looking with the helper text "3 details still needed".
>
> Above the conversation, a slim four-step progress indicator: Describe, Confirm, Design, Order — with Describe active.

### C3 · Specification summary

> Confirmation screen showing a complete cake specification before an image is generated.
>
> Headline "Please confirm your cake". A single wide card with the specification in two columns of label and value pairs: Event type Birthday, Event date 12 September 2026, Servings 20, Size Medium, Shape Round, Tiers 1, Flavour Vanilla, Filling Raspberry mascarpone, Frosting Buttercream, Style Floral, Main colours light pink / white / gold shown as small colour dots, Decorations fresh flowers and gold leaf and edible pearls shown as chips, Inscription "Happy Birthday Emma", Dietary requirements none, Allergen notes none, Fulfilment Delivery.
>
> Beside it a price card: base Medium $260, premium filling $25, fresh flowers $30, gold leaf $40, detailed complexity ×1.2, delivery zone 1 $25 — with a clear total of $412 in large type. A calm inline note about the shared kitchen and allergens. Each specification row has a small "Change" text link. At the bottom a primary button "Create my design" and a secondary "Keep editing".

### C4 · Design preview and revisions

> Cake design preview screen.
>
> Large generated cake image on the left, on a clean neutral background, with a caption underneath: "This image is a visual representation. Handmade cakes may include minor variations in colour, texture, shape and decoration."
>
> Right column: the cake specification summary in compact form, the price $412, and a revision area headed "Would you like to change anything?" with a text area whose placeholder shows real examples like "Make the flowers smaller" or "Change the main colour to light pink". Under it, a clear counter "2 of 3 free revisions left" and a primary button "Request this change".
>
> Below the image, a horizontal strip of previous versions as small thumbnails labelled Version 1, Version 2, Version 3, with the current one visibly selected and each showing its price. A prominent primary button "Approve this design".

### C5 · Fulfilment

> Pickup or delivery selection screen for a Paris cake atelier.
>
> Two large selectable cards at the top: "Collect from the atelier — free" and "Delivery in Paris — from $25", with delivery selected. Then a date picker showing a month with some dates visibly unavailable and a note "12 September has capacity". Then a row of two-hour time windows as selectable chips: 10:00–12:00, 12:00–14:00, 14:00–16:00, 16:00–18:00, one of them shown as full and unavailable.
>
> A delivery address block with a labelled address field showing an autocomplete suggestion list, and a result panel confirming "Zone 1 — up to 5 km · delivery $25". Then contact fields: full name, email, phone, each with a visible label above it.
>
> A final order summary card with the price breakdown and total $412. Three checkboxes with real wording for allergen acknowledgement, generated-image acknowledgement, and privacy and cancellation policy. Primary button "Place order".

### C6 · Order confirmation

> Order confirmation page for a Paris cake atelier. Large heading "Your order is confirmed", the order number MCF-20260812-01001 shown prominently and easy to copy, the finished cake image, a specification summary, delivery date and time window with the address, and a price total of $412.
>
> A calm panel explaining that payment is arranged separately with the bakery and no payment was taken online. A bordered block with a "Save your order link" button and the note that the link stays active for 14 days and lets the customer return to the design. Secondary links to the cancellation policy and to contact the atelier.
>
> Also produce a variant of this screen for a special order: the status reads "Awaiting bakery approval", the price is labelled "Estimated price, subject to bakery approval", and an explanatory line says Mayan will review the design personally.

---

## Admin

### A1 · Login

> Simple, calm admin login for a bakery. Centred card on a warm off-white background. Wordmark, heading "Bakery sign in", labelled email and password fields, a primary "Sign in" button, and an inline error state example reading "Email or password is incorrect." Nothing decorative, no marketing copy. Small footer note that this area is for bakery staff.

### A2 · Dashboard

> Admin dashboard for a small Paris bakery, dense but calm, same warm paper and caramel palette.
>
> A row of summary tiles: Orders today 4, Orders this week 19, Production points used today 7 of 10 shown as a small bar, Orders awaiting approval 3.
>
> A money section that clearly separates four different figures with distinct labels and visual weight: Confirmed order value $4,820, Amount paid $0, Outstanding $4,820, Estimated value of special orders $2,300. It must be visually obvious that unpaid order value is not collected revenue — do not present these as one revenue number.
>
> A production load chart for the next seven days showing points used against the daily limit, with one day visibly full.
>
> A list of orders awaiting approval with reason badges such as "Three-tier", "Rush order", "Above $1,500". A warnings panel listing allergen declarations and rush orders needing attention. A panel of full time slots for the coming week.

### A3 · Order list

> Admin order list, dense table layout. Columns: order number, customer name, fulfilment date, pickup or delivery, status badge, complexity level, production points, total price, and warning icons for rush and allergen.
>
> Above the table a filter bar with controls for fulfilment date range, creation date, status, pickup or delivery, cake style, complexity, price range, standard or special order, and a search box for name, phone or email. Show some filters as active chips that can be removed.
>
> Status badges use distinct calm colours for Draft, Awaiting bakery approval, Confirmed, In production, Ready for pickup, Out for delivery, Completed, Cancelled. Include sorting indicators on column headers and pagination at the bottom. Also show an empty state for when no orders match the filters.

### A4 · Order detail

> Admin order detail page for a custom cake order.
>
> Header with the order number MCF-20260812-01001, a status badge, and action buttons: Confirm, Reject, Change status, Add internal note.
>
> Main column: the approved cake image with previous versions as smaller thumbnails beside it; the full structured specification; decorations as chips; dietary requirements and a clearly marked allergen warning; the price breakdown line by line with the total; production points and complexity level.
>
> Side column: customer contact details with their previous order count, event details, fulfilment date and time window, delivery address with the calculated zone and distance, manual approval reasons listed as bullet points, internal notes, a status history timeline, and an audit log.
>
> Include a price override control that makes it clear a reason is mandatory, showing the previous price, the new price and a required reason field.

### A5 · Catalog management

> Admin catalog management screen. Left sidebar listing catalog types: Sizes, Flavours, Fillings, Frostings, Design styles, Decorations, Dietary options, Recommended combinations. Sizes is selected.
>
> Main area: an editable table of cake sizes with columns for name, serving range, base price, tiers, production points, preparation hours, a requires-approval toggle, an active toggle, and display order. Show inline editing on one row and an "Add size" button. Prices shown in dollars but noted as stored in cents.
>
> Include a panel for marking an item temporarily unavailable with a date range and a reason, and an empty state for a catalog type with no items yet.

### A6 · Availability and capacity

> Admin availability screen for a bakery. A month calendar where each day shows production points used against the limit, for example "7 / 10", with full days clearly marked, blocked days visually distinct, and one day showing a holiday label.
>
> Clicking a day opens a side panel to set the maximum production points, the maximum orders, block or unblock the date, allow or disallow rush orders, reserve capacity, and add a note.
>
> Below the calendar, a time slot section listing the four two-hour windows with per-day order limits and the number reserved, and controls to enable, disable or edit each window.

### A7 · Settings

> Admin settings screen, grouped into clearly separated sections with a description under each heading.
>
> Bakery details: name, address, coordinates. Business rules: default lead time 48 hours, minimum lead time 24 hours, daily production points 10, maximum orders per day 6, automatic approval price ceiling $1,500, automatic approval serving ceiling 80, rush surcharge 20 percent. Customer experience: save link expiry 14 days, maximum free revisions 3. Currency and timezone.
>
> Long-form editable text areas for the cancellation policy, the allergen disclaimer and the generated-image disclaimer, each showing its real current wording. A save bar that appears when something has changed, with Save and Discard buttons, and a note that changes are recorded in the audit log.

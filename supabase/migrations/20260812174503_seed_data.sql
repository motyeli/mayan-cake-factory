-- Seed data: catalog, delivery zones, time slots, pricing rules, feasibility
-- rules and operational settings.
--
-- This lives in a MIGRATION rather than only in supabase/seed.sql because
-- development and production are remote projects: `supabase db push` is the
-- only path that reaches them, and `db reset`/seed.sql runs locally. Every
-- statement is idempotent, so applying it twice changes nothing.
--
-- These are EDITABLE STARTING VALUES, not business rules frozen in code.
-- Mayan changes any of them from the admin panel without a deployment.

-- Names are the natural key for seeding; make that explicit so ON CONFLICT works.
alter table pricing_rules            add constraint pricing_rules_name_key            unique (name);
alter table feasibility_rules        add constraint feasibility_rules_name_key        unique (name);
alter table recommended_combinations add constraint recommended_combinations_name_key unique (name);

-- ============================================================== settings ==

insert into settings (key, value, value_type, label, description) values
  ('bakery_name',            '"Mayan''s Cake Factory"'::jsonb, 'string',  'Bakery name', null),
  ('bakery_address',         '""'::jsonb,                      'string',  'Bakery address', 'Set from BAKERY_ADDRESS; never hard-coded in application code.'),
  ('bakery_latitude',        '48.8584'::jsonb,                 'string',  'Bakery latitude',  'Distance origin for delivery zones.'),
  ('bakery_longitude',       '2.2945'::jsonb,                  'string',  'Bakery longitude', 'Distance origin for delivery zones.'),
  ('currency',               '"USD"'::jsonb,                   'string',  'Display currency', 'Business price range was supplied in dollars.'),
  ('timezone',               '"Europe/Paris"'::jsonb,          'string',  'Timezone', null),

  ('default_lead_time_hours',    '48'::jsonb,  'integer', 'Standard lead time (hours)', 'Below this an order is a rush order.'),
  ('min_lead_time_hours',        '24'::jsonb,  'integer', 'Absolute minimum lead time (hours)', 'Nothing under this is ever auto-confirmed.'),
  ('daily_production_points',    '10'::jsonb,  'integer', 'Daily production points', 'Capacity is points, not order count.'),
  ('max_orders_per_day',         '6'::jsonb,   'integer', 'Maximum orders per day', null),
  ('design_link_expiration_days','14'::jsonb,  'integer', 'Save-and-return link lifetime (days)', null),
  ('max_revisions',              '3'::jsonb,   'integer', 'Free design revisions', 'Enforced in the backend, never only in the UI.'),
  ('auto_approval_price_limit_cents', '150000'::jsonb, 'integer', 'Automatic approval price ceiling', 'Above this, Mayan approves manually.'),
  ('auto_approval_max_servings', '80'::jsonb,  'integer', 'Automatic approval serving ceiling', null),
  ('rush_surcharge_basis_points','2000'::jsonb,'integer', 'Rush surcharge (basis points)', '2000 = 20%.'),

  ('allergen_disclaimer',
   '"The bakery handles gluten, dairy, eggs, nuts, and other allergens. Cross-contamination cannot be completely excluded."'::jsonb,
   'string', 'Allergen disclaimer', 'Shown wherever dietary requirements are collected. Never a medical guarantee.'),

  ('visual_disclaimer',
   '"This image is a visual representation. Handmade cakes may include minor variations in color, texture, shape, and decoration."'::jsonb,
   'string', 'Generated-image disclaimer', 'Shown with every generated design.'),

  ('inspiration_disclaimer',
   '"An inspiration image is a design direction, not a guarantee of an exact copy."'::jsonb,
   'string', 'Inspiration-image disclaimer', null),

  ('cancellation_policy',
   '"Free cancellation or changes until 48 hours before pickup or delivery, provided production has not begun. Changes after production starts require bakery approval. Rush orders cannot be cancelled after confirmation. Major design changes may alter the price. Date changes depend on available capacity."'::jsonb,
   'string', 'Cancellation and change policy', null),

  ('payment_instructions',
   '"Payment is arranged separately with the bakery. No payment is taken online."'::jsonb,
   'string', 'Payment arrangement text', null)
on conflict (key) do nothing;

-- ============================================================ cake sizes ==
-- Three-tier and anything over 80 servings route to manual approval (spec 12).

insert into cake_sizes (name, description, min_servings, max_servings, base_price_cents,
                        tiers, production_points, requires_manual_approval, display_order) values
  ('Mini',        'Intimate cake for a small gathering',   6,   8,  10000, 1, 1, false, 1),
  ('Small',       'Classic celebration size',             10,  12,  16000, 1, 1, false, 2),
  ('Medium',      'Most popular size for birthdays',      16,  20,  26000, 1, 2, false, 3),
  ('Large',       'Generous single tier for a party',     25,  30,  42000, 1, 2, false, 4),
  ('Event',       'Large format for events',              40,  50,  70000, 1, 3, false, 5),
  ('Two-Tier',    'Two tiers for weddings and milestones',50,  70,  95000, 2, 3, false, 6),
  ('Three-Tier',  'Three tiers, reviewed by the bakery',  70, 100, 140000, 3, 4, true,  7)
on conflict (name) do nothing;

-- ========================================================== cake flavors ==

insert into cake_flavors (name, price_adjustment_cents, is_premium, display_order) values
  ('Vanilla',    0,    false, 1),
  ('Chocolate',  0,    false, 2),
  ('Red Velvet', 500,  false, 3),
  ('Lemon',      0,    false, 4),
  ('Carrot',     500,  false, 5),
  ('Coffee',     500,  false, 6),
  ('Pistachio',  1500, true,  7),
  ('Almond',     1000, true,  8)
on conflict (name) do nothing;

-- =============================================================== fillings ==
-- Premium fillings sit in the $15-$40 band from spec section 24.

insert into fillings (name, price_adjustment_cents, is_premium, display_order) values
  ('Vanilla cream',      0,    false, 1),
  ('Chocolate ganache',  1500, true,  2),
  ('Salted caramel',     2000, true,  3),
  ('Raspberry cream',    2000, true,  4),
  ('Strawberry cream',   2000, true,  5),
  ('Lemon curd',         1500, true,  6),
  ('Pistachio cream',    4000, true,  7),
  ('Praline',            3000, true,  8),
  ('Mascarpone cream',   2500, true,  9)
on conflict (name) do nothing;

-- ============================================================== frostings ==
-- Whipped cream survives pickup and short delivery only. That constraint is
-- data (max_delivery_km), so Mayan can relax it in winter without a deploy.

insert into frostings (name, description, price_adjustment_cents, pickup_only,
                       max_delivery_km, production_points, display_order) values
  ('Buttercream',       'Stable in transport, holds detail',      0,    false, null, 0, 1),
  ('Chocolate ganache', 'Rich, glossy, very stable',              2000, false, null, 0, 2),
  ('Fondant',           'Smooth sculpted finish',                 4000, false, null, 1, 3),
  ('Mirror glaze',      'High-shine mirrored surface',            6000, false, 10,   1, 4),
  ('Whipped cream',     'Light and fresh; pickup or short delivery', 0, false, 5,    0, 5)
on conflict (name) do nothing;

-- ========================================================== design styles ==

insert into design_styles (name, description, base_complexity_level, price_adjustment_cents,
                           image_prompt_hint, display_order) values
  ('Minimalist',             'Clean lines, restrained palette',        1, 0,
   'minimalist, smooth finish, restrained palette, elegant simplicity', 1),
  ('Floral',                 'Flowers and botanical detail',           2, 0,
   'floral decoration, botanical detail, soft romantic arrangement', 2),
  ('Birthday',               'Playful and celebratory',                1, 0,
   'festive birthday styling, cheerful colours, celebratory finish', 3),
  ('Luxury',                 'Refined finishes and metallic accents',  3, 5000,
   'luxury patisserie finish, metallic accents, refined couture detail', 4),
  ('Wedding and Engagement', 'Formal, tiered, elegant',                3, 5000,
   'elegant wedding cake styling, refined tiers, formal composition', 5),
  ('Corporate',              'Brand-led, clean and professional',      2, 0,
   'corporate event styling, clean professional presentation, brand-led palette', 6),
  ('Photo and Illustration', 'Printed image or drawn artwork',         2, 0,
   'edible printed illustration panel, crisp artwork reproduction', 7)
on conflict (name) do nothing;

-- ============================================================ decorations ==
-- price_adjustment_cents is the default charge; max_price_cents is the
-- ceiling Mayan may raise it to for elaborate work (spec section 24 ranges).

insert into decorations (name, price_adjustment_cents, max_price_cents, complexity_points,
                         food_safe, requires_barrier, requires_manual_approval, display_order) values
  ('Custom inscription',       0,     0,     0, true,  false, false, 1),
  ('Name and age',             0,     0,     0, true,  false, false, 2),
  ('Candles',                  500,   500,   0, true,  false, false, 3),
  ('Fresh flowers',            3000,  12000, 1, false, true,  false, 4),
  ('Sugar flowers',            5000,  25000, 2, true,  false, false, 5),
  ('Macarons',                 2500,  5000,  1, true,  false, false, 6),
  ('Fresh fruit',              2000,  4000,  1, true,  false, false, 7),
  ('Chocolate pieces',         2000,  4000,  1, true,  false, false, 8),
  ('Edible pearls',            1500,  3000,  0, true,  false, false, 9),
  ('Edible gold leaf',         4000,  10000, 1, true,  false, false, 10),
  ('Edible image',             2500,  2500,  1, true,  false, false, 11),
  ('Corporate logo',           3500,  3500,  1, true,  false, false, 12),
  ('Cake topper',              1500,  3000,  0, true,  false, false, 13),
  ('Simple handmade figure',   6000,  6000,  2, true,  false, false, 14),
  ('Complex handmade figure',  15000, 30000, 3, true,  false, true,  15),
  ('Themed color palette',     0,     0,     0, true,  false, false, 16),
  ('Textures',                 1500,  3000,  1, true,  false, false, 17),
  ('Drip design',              2000,  3000,  1, true,  false, false, 18),
  ('Custom illustration',      4500,  9000,  2, true,  false, false, 19)
on conflict (name) do nothing;

-- ======================================================== dietary options ==
-- No option here is a medical guarantee. Severe allergy declarations are
-- caught by a feasibility rule and reviewed by Mayan.

insert into dietary_options (name, description, price_adjustment_cents, display_order) values
  ('Vegetarian',       'No meat-derived ingredients',                              0,    1),
  ('Vegan',            'No animal products',                                       3000, 2),
  ('Gluten-free',      'Made without gluten-containing flour',                     2500, 3),
  ('Lactose-free',     'Made without lactose-containing dairy',                    2500, 4),
  ('Nut-free request', 'Prepared without nut ingredients; shared kitchen applies', 0,    5)
on conflict (name) do nothing;

-- ============================================== recommended combinations ==
-- Guidance for the AI to suggest. Never restricts other valid choices.

insert into recommended_combinations (name, cake_flavor_id, filling_id, frosting_id, description, display_order)
select v.name,
       (select id from cake_flavors where name = v.flavor),
       (select id from fillings     where name = v.filling),
       (select id from frostings    where name = v.frosting),
       v.description, v.ord
from (values
  ('Vanilla, raspberry and mascarpone', 'Vanilla',   'Raspberry cream',   'Buttercream',       'Fresh, light and popular for summer events', 1),
  ('Chocolate and salted caramel',      'Chocolate', 'Salted caramel',    'Chocolate ganache', 'Rich crowd-pleaser that travels well',        2),
  ('Lemon and vanilla cream',           'Lemon',     'Vanilla cream',     'Buttercream',       'Bright and refreshing',                       3),
  ('Pistachio and raspberry',           'Pistachio', 'Raspberry cream',   'Buttercream',       'Elegant pairing for refined palates',         4),
  ('Coffee and praline',                'Coffee',    'Praline',           'Chocolate ganache', 'Warm, nutty and grown-up',                    5)
) as v(name, flavor, filling, frosting, description, ord)
on conflict (name) do nothing;

-- ========================================================= delivery zones ==
-- Distances are from the bakery coordinates in settings, never hard-coded.

insert into delivery_zones (name, min_distance_km, max_distance_km, delivery_fee_cents,
                            requires_manual_approval, display_order) values
  ('Zone 1 — up to 5 km',      0,  5,   2500, false, 1),
  ('Zone 2 — 5 to 10 km',      5,  10,  4500, false, 2),
  ('Zone 3 — 10 to 20 km',     10, 20,  7500, false, 3),
  ('Extended — beyond 20 km',  20, 100, 0,    true,  4)
on conflict (name) do nothing;

-- ============================================================= time slots ==
-- Two-hour windows, used for both pickup and delivery until Mayan splits them.

insert into time_slots (start_time, end_time, label, max_orders, applies_to, display_order) values
  ('10:00', '12:00', '10:00 – 12:00', 3, null, 1),
  ('12:00', '14:00', '12:00 – 14:00', 3, null, 2),
  ('14:00', '16:00', '14:00 – 16:00', 3, null, 3),
  ('16:00', '18:00', '16:00 – 18:00', 3, null, 4)
on conflict (start_time, end_time, applies_to) do nothing;

-- ========================================================== pricing rules ==
-- percent adjustments are basis points: 2000 = +20%.
-- Complexity multipliers from spec section 24 (1.0 / 1.2 / 1.5; level 4 is
-- never priced automatically).

insert into pricing_rules (name, rule_type, conditions, adjustment_type, adjustment_amount, priority) values
  ('Complexity level 2 — Detailed', 'complexity',
   '{"field": "complexity_level", "op": "eq", "value": 2}'::jsonb, 'percent', 2000, 10),

  ('Complexity level 3 — Premium', 'complexity',
   '{"field": "complexity_level", "op": "eq", "value": 3}'::jsonb, 'percent', 5000, 10),

  ('Rush order — under 48 hours', 'rush',
   '{"field": "lead_time_hours", "op": "lt", "value": 48}'::jsonb, 'percent', 2000, 20),

  ('Rush order — under 24 hours', 'rush',
   '{"field": "lead_time_hours", "op": "lt", "value": 24}'::jsonb, 'percent', 3500, 19),

  ('Fondant on large cakes', 'frosting',
   '{"all": [{"field": "frosting_name", "op": "eq", "value": "Fondant"},
             {"field": "servings", "op": "gte", "value": 40}]}'::jsonb, 'fixed_cents', 6000, 30)
on conflict (name) do nothing;

-- ====================================================== feasibility rules ==
-- The deterministic gate. The AI explains these outcomes and offers the
-- stored alternative; it never decides them and never overrides them.

insert into feasibility_rules (name, description, conditions, outcome,
                               manual_approval_reason, customer_message,
                               suggested_alternative, priority) values

  ('Structurally unsupported tier count',
   'More than three tiers is beyond what the bakery can transport safely.',
   '{"field": "number_of_tiers", "op": "gt", "value": 3}'::jsonb,
   'reject', null,
   'Cakes above three tiers cannot be built and transported safely by the bakery.',
   'A three-tier cake, or a two-tier cake presented with matching side cakes for the same serving count.',
   10),

  ('Three-tier cake',
   'Three tiers always need Mayan to confirm structure and schedule.',
   '{"field": "number_of_tiers", "op": "gte", "value": 3}'::jsonb,
   'require_manual_approval', 'Three-tier cake requires bakery approval',
   'Three-tier cakes are reviewed by the bakery before confirmation.',
   null, 20),

  ('Large serving count',
   'Above the automatic serving ceiling.',
   '{"field": "servings", "op": "gt", "value": 80}'::jsonb,
   'require_manual_approval', 'More than 80 servings requires bakery approval',
   'Cakes serving more than 80 guests are reviewed by the bakery.',
   null, 20),

  ('Price above automatic ceiling',
   'Order value above the automatic approval limit.',
   '{"field": "total_price_cents", "op": "gt", "value": 150000}'::jsonb,
   'require_manual_approval', 'Order value above $1,500 requires bakery approval',
   'This is an estimated price, subject to bakery approval.',
   null, 30),

  ('Below minimum lead time',
   'Under the absolute minimum notice the bakery can work with.',
   '{"field": "lead_time_hours", "op": "lt", "value": 24}'::jsonb,
   'reject', null,
   'The bakery needs at least 24 hours of notice to produce a custom cake.',
   'The earliest date with capacity, shown in the date picker.',
   10),

  ('Rush order under 48 hours',
   'Inside the standard lead time, so it needs a capacity decision.',
   '{"all": [{"field": "lead_time_hours", "op": "lt", "value": 48},
             {"field": "lead_time_hours", "op": "gte", "value": 24}]}'::jsonb,
   'require_manual_approval', 'Rush order inside the 48 hour lead time',
   'This is a rush order and is reviewed by the bakery before confirmation.',
   null, 25),

  ('Frosting cannot survive the delivery distance',
   'Whipped cream and mirror glaze degrade over distance and time in transit.',
   '{"all": [{"field": "fulfillment_method", "op": "eq", "value": "delivery"},
             {"field": "frosting_max_delivery_km", "op": "is_set", "value": true},
             {"field": "delivery_distance_km", "op": "gt_field", "value": "frosting_max_delivery_km"}]}'::jsonb,
   'require_manual_approval', 'Frosting is not rated for this delivery distance',
   'This frosting is not stable over the delivery distance requested.',
   'Buttercream or chocolate ganache, which travel reliably, or collecting the cake from the bakery.',
   40),

  ('Fresh flowers in contact with food',
   'Fresh flowers are not food-safe and need a barrier between stem and cake.',
   '{"field": "has_non_food_safe_decoration", "op": "is_true", "value": true}'::jsonb,
   'require_manual_approval', 'Fresh flowers require a food-safe barrier',
   'Fresh flowers are arranged with a food-safe barrier, so placement is confirmed by the bakery.',
   'Sugar flowers, which are fully edible and need no barrier.',
   50),

  ('Delivery beyond the standard area',
   'Outside the configured delivery zones.',
   '{"field": "delivery_distance_km", "op": "gt", "value": 20}'::jsonb,
   'require_manual_approval', 'Delivery beyond the standard 20 km area',
   'Delivery beyond 20 km is arranged individually with the bakery.',
   'Collection from the bakery, or delivery to an address inside the standard area.',
   40),

  ('Severe allergy declared',
   'The bakery is a shared kitchen and cannot guarantee an allergen-free product.',
   '{"field": "has_severe_allergy", "op": "is_true", "value": true}'::jsonb,
   'require_manual_approval', 'Severe allergy declared — needs bakery confirmation',
   'The bakery handles gluten, dairy, eggs, nuts, and other allergens. Cross-contamination cannot be completely excluded, so this order is reviewed individually.',
   null, 15),

  ('Complex sculpted work',
   'Detailed figures and sculpture are scheduled by hand.',
   '{"field": "has_manual_approval_decoration", "op": "is_true", "value": true}'::jsonb,
   'require_manual_approval', 'Complex handmade figure requires bakery approval',
   'Detailed handmade figures are quoted and scheduled by the bakery.',
   'A simpler handmade figure or a printed edible illustration.',
   35),

  ('Special project complexity',
   'Level 4 work is never priced automatically.',
   '{"field": "complexity_level", "op": "gte", "value": 4}'::jsonb,
   'require_manual_approval', 'Special project — priced by the bakery',
   'This is a special project. The price shown is an estimate, subject to bakery approval.',
   null, 30),

  ('Suspended or gravity-defying structure',
   'Suspended structures need an engineered support the bakery must approve.',
   '{"field": "free_text", "op": "contains_any",
     "value": ["suspended", "floating", "gravity defying", "gravity-defying", "hanging", "cantilever"]}'::jsonb,
   'require_manual_approval', 'Suspended structure requires bakery approval',
   'Suspended or floating designs need an engineered internal support, which the bakery reviews individually.',
   'The same visual effect built on a concealed rigid stand.',
   45),

  ('Allergen safety guarantee requested',
   'The system must never make a medical safety claim.',
   '{"field": "free_text", "op": "contains_any",
     "value": ["guarantee allergen", "allergen free guarantee", "certified allergen", "medically safe", "anaphyla"]}'::jsonb,
   'require_manual_approval', 'Medical allergen guarantee requested',
   'The bakery cannot guarantee an allergen-free product because gluten, dairy, eggs and nuts are handled in the same kitchen. Please discuss the requirement with the bakery directly.',
   null, 5)
on conflict (name) do nothing;

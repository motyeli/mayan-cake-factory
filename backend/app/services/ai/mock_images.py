"""Mock image provider — renders an actual cake, not a grey placeholder.

Draws the specification as an SVG: the right number of tiers, the requested
shape, the customer's colour palette, decorations and the inscription. That
matters because a placeholder would let real bugs hide — a tier count that
never reaches the prompt, or a colour list that is silently dropped, is
visible here and invisible behind a grey box.

SVG rather than a raster format so there is no image dependency at all.
"""

from __future__ import annotations

import hashlib
import re

from app.services.ai.providers import GeneratedImage

WIDTH, HEIGHT = 1024, 1024

# Named colours the customer is likely to say, mapped to something plausible
# for a cake. Anything unrecognised is hashed to a stable pastel, so the same
# word always produces the same colour across regenerations.
_PALETTE = {
    "white": "#FFFFFF", "ivory": "#FFFFF0", "cream": "#FFFDD0",
    "pink": "#F8C8D8", "light pink": "#FADCE4", "blush": "#F2C6C2",
    "red": "#C43D3D", "burgundy": "#7B2D3B", "orange": "#E8A15C",
    "peach": "#FFCBA4", "yellow": "#F5DE8C", "gold": "#C9A227",
    "green": "#8FA97C", "sage": "#B2C2A6", "mint": "#B8E0D2",
    "blue": "#9FC0DE", "navy": "#2C3E56", "purple": "#B29AC4",
    "lilac": "#C9B6DB", "lavender": "#D3C4E3", "black": "#2B2B2B",
    "silver": "#C7CBD1", "grey": "#B9B4AE", "brown": "#8C6239",
}


def _color(name: str) -> str:
    key = (name or "").strip().lower()
    if key in _PALETTE:
        return _PALETTE[key]
    digest = hashlib.sha256(key.encode()).digest()
    # Bias light so text stays readable and it still looks like a cake.
    r, g, b = (170 + digest[i] % 70 for i in range(3))
    return f"#{r:02X}{g:02X}{b:02X}"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _read(prompt: str) -> dict:
    """Recover the drawable facts from the generated prompt.

    The prompt is built by `prompts.image_prompt` from the resolved
    specification, so parsing it here keeps the provider interface to a single
    string argument — the same interface a real provider needs.
    """
    lowered = prompt.lower()

    tiers = 1
    match = re.search(r"(\d)-tier", lowered)
    if match:
        tiers = max(1, min(4, int(match.group(1))))

    shape = "round"
    for candidate in ("square", "rectangle", "heart", "round"):
        if candidate in lowered:
            shape = candidate
            break

    colors: list[str] = []
    match = re.search(r"colour palette of ([^.]+)", lowered)
    if match:
        colors = [c.strip() for c in match.group(1).split(",") if c.strip()]

    inscription = None
    match = re.search(r'"([^"]{1,120})"', prompt)
    if match:
        inscription = match.group(1)

    decorations: list[str] = []
    match = re.search(r"decorated with ([^.]+)", lowered)
    if match:
        decorations = [d.strip() for d in match.group(1).split(",") if d.strip()]

    return {
        "tiers": tiers,
        "shape": shape,
        "colors": colors or ["ivory"],
        "inscription": inscription,
        "decorations": decorations,
    }


def render_cake_svg(prompt: str) -> str:
    facts = _read(prompt)
    tiers, shape = facts["tiers"], facts["shape"]
    colors = facts["colors"]

    base_width, tier_height = 520, 150
    bottom = 780
    parts: list[str] = []

    for index in range(tiers):
        width = base_width - index * (base_width * 0.22)
        height = tier_height - index * 8
        x = (WIDTH - width) / 2
        y = bottom - (index + 1) * height - index * 6
        fill = _color(colors[index % len(colors)])
        radius = {"round": 26, "square": 6, "rectangle": 6, "heart": 40}.get(shape, 26)

        parts.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{width:.0f}" height="{height:.0f}" '
            f'rx="{radius}" fill="{fill}" stroke="#E0D6C8" stroke-width="2"/>'
        )
        if shape == "round":
            parts.append(
                f'<ellipse cx="{WIDTH/2:.0f}" cy="{y:.0f}" rx="{width/2:.0f}" ry="16" '
                f'fill="{fill}" stroke="#E0D6C8" stroke-width="2"/>'
            )

    # Decorations as small marks along the top tier, so their presence and
    # count are visible rather than implied.
    top_width = base_width - (tiers - 1) * (base_width * 0.22)
    top_y = bottom - tiers * tier_height
    for i, decoration in enumerate(facts["decorations"][:7]):
        cx = WIDTH / 2 - top_width / 2 + (i + 1) * (top_width / 8)
        parts.append(
            f'<circle cx="{cx:.0f}" cy="{top_y - 10:.0f}" r="13" fill="{_color(decoration)}" '
            f'opacity="0.9"/>'
        )

    stand = (
        f'<rect x="{WIDTH/2-300:.0f}" y="{bottom:.0f}" width="600" height="18" rx="9" fill="#D8CDBC"/>'
        f'<rect x="{WIDTH/2-40:.0f}" y="{bottom+18:.0f}" width="80" height="70" fill="#D8CDBC"/>'
        f'<rect x="{WIDTH/2-140:.0f}" y="{bottom+88:.0f}" width="280" height="20" rx="10" fill="#CCC0AC"/>'
    )

    inscription = ""
    if facts["inscription"]:
        inscription = (
            f'<text x="{WIDTH/2:.0f}" y="{bottom - tier_height/2:.0f}" text-anchor="middle" '
            f'font-family="Georgia, serif" font-size="30" fill="#5A4632">'
            f"{_escape(facts['inscription'])}</text>"
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img">'
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#FDFBF8"/>'
        f'<ellipse cx="{WIDTH/2}" cy="{bottom+118}" rx="330" ry="26" fill="#EFE7DA"/>'
        f"{''.join(parts)}{stand}{inscription}"
        f'<text x="{WIDTH/2:.0f}" y="980" text-anchor="middle" font-family="Georgia, serif" '
        f'font-size="22" fill="#9C8B78">Preview — generated in development mode</text>'
        f"</svg>"
    )


class MockImages:
    """Implements ImageGenerationProvider and ImageRevisionProvider."""

    name = "mock"

    async def generate(self, *, prompt: str) -> GeneratedImage:
        return GeneratedImage(
            data=render_cake_svg(prompt).encode("utf-8"),
            content_type="image/svg+xml",
            prompt=prompt,
            provider=self.name,
            provider_result_id=hashlib.sha256(prompt.encode()).hexdigest()[:16],
            usage={"mode": "mock"},
        )

    async def revise(
        self, *, prompt: str, instruction: str, previous_image: bytes | None = None
    ) -> GeneratedImage:
        combined = f"{prompt}\n\nRevision requested: {instruction}"
        image = await self.generate(prompt=combined)
        image.prompt = combined
        return image

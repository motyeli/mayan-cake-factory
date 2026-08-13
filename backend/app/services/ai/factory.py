"""Provider selection.

The only place that knows which vendor is configured. Everything else depends
on the protocols in `providers.py`.

`AI_MODE=mock` is the default and needs no credentials. In `live` mode a
provider that cannot be constructed — missing key, unknown vendor — falls back
to the mock with a loud log line, because a customer mid-conversation is better
served by a working assistant than by a 500.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ai.mock_images import MockImages
from app.services.ai.mock_llm import MockLLM

logger = get_logger(__name__)


def get_llm_provider():
    settings = get_settings()
    if settings.ai_mode == "mock":
        return MockLLM()

    if settings.llm_provider == "openai":
        try:
            from app.services.ai.openai_llm import build_openai_llm

            return build_openai_llm()
        except Exception as exc:  # fall back rather than fail a live session
            logger.error(
                "falling back to the mock language model",
                extra={"error_type": type(exc).__name__, "llm_provider": settings.llm_provider},
            )
            return MockLLM()

    logger.error("unknown LLM_PROVIDER, using mock", extra={"llm_provider": settings.llm_provider})
    return MockLLM()


def get_image_provider():
    settings = get_settings()
    if settings.ai_mode == "mock":
        return MockImages()

    if settings.image_provider == "openai":
        try:
            from app.services.ai.openai_llm import build_openai_images

            return build_openai_images()
        except Exception as exc:  # fall back rather than fail a live session
            logger.error(
                "falling back to the mock image provider",
                extra={"error_type": type(exc).__name__, "image_provider": settings.image_provider},
            )
            return MockImages()

    logger.error(
        "unknown IMAGE_PROVIDER, using mock", extra={"image_provider": settings.image_provider}
    )
    return MockImages()

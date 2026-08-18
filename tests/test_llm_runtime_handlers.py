from __future__ import annotations

import pytest

from src.server.llm_runtime_handlers import create_llm_runtime_handlers
from src.server.runtime.session import GameSessionRuntime, create_default_game_state


class _RecordingManager:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def broadcast(self, message: dict[str, str]) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_global_llm_failure_broadcast_redacts_internal_detail() -> None:
    runtime = GameSessionRuntime(create_default_game_state())
    manager = _RecordingManager()
    handlers = create_llm_runtime_handlers(
        runtime=runtime,
        manager=manager,
        settings_service=object(),
        create_llm_updated_handler=lambda **_kwargs: None,
        test_connectivity_impl=lambda **_kwargs: (True, ""),
    )
    internal_error = "C:\\private\\provider: bearer-secret"

    await handlers.handle_global_llm_failure(internal_error)

    assert runtime.get_llm_failure_state() == (True, internal_error)
    assert manager.messages == [
        {
            "type": "llm_config_required",
            "error": "LLM configuration requires administrator attention.",
        }
    ]
    assert "bearer-secret" not in str(manager.messages)

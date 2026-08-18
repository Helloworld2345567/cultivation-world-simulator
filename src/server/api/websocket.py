from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.server.services.public_api_contract import PUBLIC_LLM_CONFIG_REQUIRED_MESSAGE


def create_websocket_router(
    *,
    manager,
    runtime,
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)

        if runtime.get("llm_check_failed", False):
            await websocket.send_json({
                "type": "llm_config_required",
                "error": PUBLIC_LLM_CONFIG_REQUIRED_MESSAGE,
            })
            print("Sent LLM configuration requirement to client")

        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text('{"type":"pong"}')
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception as exc:
            print(f"WS Error: {exc}")
            manager.disconnect(websocket)

    return router

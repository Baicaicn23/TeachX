from fastapi import Request, WebSocket

from teachx.api.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_ws_container(websocket: WebSocket) -> ApplicationContainer:
    return websocket.app.state.container

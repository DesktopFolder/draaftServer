from fastapi import WebSocket
from db import PopulatedUser

from models.ws import NON_ADMIN_PLAYER_ACTIONS, ActionError, PlayerAction, PlayerActionEnum, WebSocketMessage, serialize
from rooms import get_room_from_code, get_user_room_code

## NOT USING ANY OF THIS CODE LOL
async def handle_playeraction(websocket: WebSocket, msg: PlayerAction, user: PopulatedUser):
    code = get_user_room_code(user.uuid)
    if code is None:
        return await websocket.send_text(serialize(ActionError(text="could not find room code for user")))
    room = get_room_from_code(code)
    if room is None:
        # Should never happen
        return await websocket.send_text(serialize(ActionError(text="could not find room from code")))

    if msg.action not in NON_ADMIN_PLAYER_ACTIONS and user.uuid != room.admin:
        return await websocket.send_text(serialize(ActionError(text=f"non-admin user cannot take action {msg.action}")))

    match msg.action:
        case PlayerActionEnum.kick:
            pass
        case PlayerActionEnum.leave:
            pass
        case PlayerActionEnum.spectate:
            pass
        case PlayerActionEnum.player:
            pass

async def handle_websocket_message(websocket: WebSocket, message: WebSocketMessage, user: PopulatedUser):
    msg = message.message
    match msg:
        case PlayerAction():
            await handle_playeraction(websocket, msg, user)
        case _:
            pass

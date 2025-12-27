from fastapi import WebSocket
from db import PopulatedUser

from models.ws import NON_ADMIN_PLAYER_ACTIONS, ActionError, AdvancementUpdate, PositionUpload, PlayerAction, PlayerActionEnum, WebSocketMessage, serialize
from rooms import get_room_from_code, get_user_room_code
from utils import LOG

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

# yeah I'm using this code lol
async def handle_advancement(msg: AdvancementUpdate, user: PopulatedUser):
    from db_utils import into_gaming_player
    from room_manager import mg
    from models.ws import PlayerAdvancementUpdate
    res = into_gaming_player(user)
    if res is None:
        return
    r, d = res
    uuid = user.uuid

    # the real advancement handling code
    LOG('Handling advancement for:', r.code, 'of:', msg.advancement)

    a = msg.as_vanilla_advancement()
    if a is None:
        LOG(f'Not an advancement: {a}')
        return

    if uuid not in r.state.player_advancements:
        r.state.player_advancements[uuid] = set()

    l = r.state.player_advancements[uuid]
    if a in l:
        return

    l.add(a)

    # Potentially this player is now finished
    if len(l) >= 80:
        if uuid not in r.state.hit_80_at:
            LOG(f"Player {uuid} hit 80 advancements!")
            r.register_completion(uuid)

    # Save into the DB
    r.save_state()
    # Send the update to all players
    await mg.broadcast_room(r, PlayerAdvancementUpdate(uuid=uuid, latest_advancement=a, count=len(l)))

async def handle_position_update(msg: PositionUpload, user: PopulatedUser):
    from db_utils import into_gaming_player
    from room_manager import mg
    from models.ws import PositionUpdate
    res = into_gaming_player(user)
    if res is None:
        return
    room, _ = res
    uuid = user.uuid
    await mg.broadcast_room(room, PositionUpdate(x=msg.x, y=msg.y, z=msg.z, dimension=msg.dimension, room_code=room.code, uuid=uuid))
    


async def handle_websocket_message(websocket: WebSocket, message: WebSocketMessage, user: PopulatedUser):
    msg = message.message
    match msg:
        case PlayerAction():
            await handle_playeraction(websocket, msg, user)
        case AdvancementUpdate():
            await handle_advancement(msg, user)
        case PositionUpload():
            await handle_position_update(msg, user)
        case _:
            pass

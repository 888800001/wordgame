import time
import random

def create_room(rooms, owner_ip, owner_name, custom_id=None, is_long=False):
    # 房间号逻辑
    if custom_id and len(custom_id) == 4 and custom_id.isdigit():
        if custom_id in rooms:
            return None  # 已存在
        room_id = custom_id
    else:
        room_id = f"{random.randint(1000,9999)}"
        while room_id in rooms:
            room_id = f"{random.randint(1000,9999)}"

    rooms[room_id] = {
        "owner_ip": owner_ip,
        "owner_name": owner_name,
        "players": {
            owner_ip: {"name": owner_name, "ready": False, "coins": 20000}
        },
        "created_at": time.time(),
        "is_long": is_long,
        "selected_game": "字字转机",
        "in_game": False
    }
    return room_id


def join_room(rooms, room_id, ip, name):
    if room_id not in rooms:
        return False
    room = rooms[room_id]
    if ip in room["players"]:
        return True  # 已在房间中
    if len(room["players"]) >= 8:
        return False
    room["players"][ip] = {"name": name, "ready": False, "coins": 20000}
    return True


def leave_room(rooms, room_id, ip):
    if room_id not in rooms:
        return
    room = rooms[room_id]
    if ip in room["players"]:
        del room["players"][ip]
    # 如果房主退出 → 房间销毁
    if ip == room["owner_ip"] or len(room["players"]) == 0:
        del rooms[room_id]


def toggle_ready(room, ip):
    if ip not in room["players"]:
        return
    room["players"][ip]["ready"] = not room["players"][ip]["ready"]


def start_game(room, game_name):
    room["in_game"] = True
    room["selected_game"] = game_name


def cleanup_rooms(rooms, timeout=300):
    now = time.time()
    for rid in list(rooms.keys()):
        if not rooms[rid]["is_long"] and now - rooms[rid]["created_at"] > timeout:
            del rooms[rid]

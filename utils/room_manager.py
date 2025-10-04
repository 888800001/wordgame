import time, random
ROOM_TIMEOUT_SEC=300
def now_ts(): return time.time()
def gen_available_room_id(rooms):
    for _ in range(2000):
        rid=f"{random.randint(0,9999):04d}"
        if rid not in rooms: return rid
    return f"{random.randint(1000,9999)}"
def mark_active(room): room['last_active']=now_ts()
def clean_expired_rooms(rooms):
    now=now_ts(); expired=[]
    for rid,room in list(rooms.items()):
        last=room.get('last_active', room.get('created_at', now))
        if now-last>ROOM_TIMEOUT_SEC: expired.append(rid)
    for rid in expired: del rooms[rid]

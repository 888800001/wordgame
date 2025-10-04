def create_user(users, ip, name):
    if ip not in users:
        users[ip] = {"name": name, "coins": 20000}


def get_balance(users, ip):
    if ip not in users:
        return 0
    return users[ip]["coins"]


def add_coins(users, ip, amount):
    if ip in users:
        users[ip]["coins"] += amount
        if users[ip]["coins"] < 0:
            users[ip]["coins"] = 0


def sync_room_coins(room, users):
    """同步房间内金币至全局用户"""
    for ip, pdata in room["players"].items():
        if ip in users:
            users[ip]["coins"] = pdata["coins"]

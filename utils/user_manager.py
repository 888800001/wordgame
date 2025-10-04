def ensure_player(players, player_key, name, default_money=20000):
    if player_key not in players:
        players[player_key]={"name":name,"seat":None,"ready":False,"money":default_money}
    else:
        players[player_key]["name"]=name
def apply_transfers(players, transfers):
    if sum(transfers.values())!=0: return False
    for pid,delta in transfers.items():
        if pid in players: players[pid]['money']=int(players[pid].get('money',0))+int(delta)
    return True

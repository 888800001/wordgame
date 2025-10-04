import time, random, importlib
from typing import Dict
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="线下游戏平台｜大厅", page_icon="🎮", layout="wide")
st_autorefresh(interval=500, key="refresh")

@st.cache_resource
def ROOMS() -> Dict[str, dict]:
    return {}

def load_game_module(name: str):
    return importlib.import_module(name)

GAMES = {
    "word": {"id": "word","title": "字字转机（语言学习）","supports_lang": True,"module": load_game_module("games.word")},
    "poker":{"id": "poker","title": "德州扑克（占位）","supports_lang": False,"module": load_game_module("games.poker")},
    "tenhalf":{"id":"tenhalf","title":"十点半（占位）","supports_lang": False,"module": load_game_module("games.tenhalf")},
}

ROOM_TIMEOUT_SEC = 300
def now_ts(): return time.time()
def clean_expired_rooms():
    now = now_ts()
    for rid, room in list(ROOMS.items()):
        last = room.get("last_active", room.get("created_at", now))
        if now - last > ROOM_TIMEOUT_SEC:
            del ROOMS()[rid]
def mark_active(room): room["last_active"] = now_ts()
def gen_available_room_id():
    for _ in range(2000):
        rid = f"{random.randint(0,9999):04d}"
        if rid not in ROOMS(): return rid
    return f"{random.randint(1000,9999)}"

def ensure_player_in_room(room, player_key, name):
    players = room["players"]
    if player_key not in players:
        used = {p.get("seat") for p in players.values() if p.get("seat") is not None}
        seat = 0
        while seat in used: seat += 1
        players[player_key] = {"name": name, "seat": seat, "ready": False, "money": 20000}
    else:
        players[player_key]["name"] = name

def apply_settlement_to_room(room, transfers: Dict[str,int]) -> bool:
    if sum(transfers.values()) != 0:
        st.error("结算非零和，已拒绝写入。")
        return False
    for pid, delta in transfers.items():
        if pid in room["players"]:
            room["players"][pid]["money"] = int(room["players"][pid]["money"]) + int(delta)
    mark_active(room); return True

if "selected_game" not in st.session_state: st.session_state.selected_game = "word"
if "player_key" not in st.session_state: st.session_state.player_key = ""
if "my_name" not in st.session_state: st.session_state.my_name = "玩家A"
if "current_room" not in st.session_state: st.session_state.current_room = None
if "prefill_room_id" not in st.session_state: st.session_state.prefill_room_id = gen_available_room_id()

def view_hub():
    clean_expired_rooms()
    st.title("🎮 线下多人游戏平台｜大厅")

    st.subheader("选择游戏")
    game_ids = list(GAMES.keys()); titles = [GAMES[g]["title"] for g in game_ids]
    idx = game_ids.index(st.session_state.selected_game) if st.session_state.selected_game in game_ids else 0
    sel = st.selectbox("请选择要玩的游戏", options=titles, index=idx)
    st.session_state.selected_game = game_ids[titles.index(sel)]
    meta = GAMES[st.session_state.selected_game]

    st.markdown("---")
    tabs = st.tabs(["创建房间","加入房间","房间列表"])

    with tabs[0]:
        st.markdown("#### 创建房间")
        player_key = st.text_input("我的唯一ID（掉线可重连）", value=st.session_state.player_key or "")
        my_name = st.text_input("我的昵称", value=st.session_state.my_name or "")
        room_id = st.text_input("房间号（4位数字，可修改）", value=st.session_state.prefill_room_id)
        max_players = st.slider("人数上限", 2, 12, 6)
        game_lang = None
        if meta["supports_lang"]:
            lang_map = {"中文":"zh","English":"en","Deutsch":"de","Français":"fr"}
            disp = st.selectbox("字字转机卡面语言（开局后锁定）", list(lang_map.keys()), index=0)
            game_lang = lang_map[disp]
        if st.button("创建"):
            if not player_key: st.error("请填写唯一ID"); return
            if not (len(room_id)==4 and room_id.isdigit()): st.error("房间号必须为4位数字"); return
            if room_id in ROOMS(): st.error("房间号已存在，请更换"); return
            ROOMS()[room_id] = {
                "room_id": room_id, "game": meta["id"], "host_key": player_key,
                "max_players": max_players, "players": {}, "stage": "lobby",
                "created_at": now_ts(), "last_active": now_ts(),
                "game_state": {}, "game_lang": game_lang,
            }
            room = ROOMS()[room_id]
            ensure_player_in_room(room, player_key, my_name or "玩家A")
            st.session_state.player_key = player_key
            st.session_state.my_name = my_name or "玩家A"
            st.session_state.current_room = room_id
            st.success(f"已创建房间 {room_id}（{meta['title']}）"); st.rerun()

    with tabs[1]:
        st.markdown("#### 加入房间")
        join_room = st.text_input("输入房间号（4位数字）")
        player_key = st.text_input("我的唯一ID", value=st.session_state.player_key or "", key="join_pid")
        my_name = st.text_input("我的昵称", value=st.session_state.my_name or "玩家B", key="join_name")
        if st.button("加入"):
            room = ROOMS().get(join_room)
            if not room: st.error("房间不存在或已过期"); return
            if len(room["players"]) >= room["max_players"]: st.error("房间已满"); return
            ensure_player_in_room(room, player_key, my_name); mark_active(room)
            st.session_state.player_key = player_key; st.session_state.my_name = my_name
            st.session_state.current_room = join_room
            st.success(f"已加入房间 {join_room}（{GAMES[room['game']]['title']}）"); st.rerun()

    with tabs[2]:
        st.markdown("#### 当前房间")
        clean_expired_rooms()
        if not ROOMS(): st.caption("暂无房间")
        else:
            cols = st.columns(3)
            for i,(rid,room) in enumerate(sorted(ROOMS().items(), key=lambda x:-x[1]["last_active"])):
                with cols[i%3]:
                    st.markdown(f"**房间 {rid}**｜游戏：{GAMES[room['game']]['title']}｜人数：{len(room['players'])}/{room['max_players']}")
                    if room["game"]=="word":
                        st.caption(f"卡面语言：{room.get('game_lang','zh')}  ｜ 状态：{room['stage']}")
                    else:
                        st.caption(f"状态：{room['stage']}")
                    if st.button(f"加入 {rid}", key=f"quick_join_{rid}"):
                        r = ROOMS().get(rid)
                        if not r: st.error("房间不存在或已过期")
                        elif len(r["players"])>=r["max_players"]: st.error("房间已满")
                        else:
                            pk = st.session_state.player_key or f"guest_{random.randint(1000,9999)}"
                            nm = st.session_state.my_name or "玩家X"
                            ensure_player_in_room(r, pk, nm); mark_active(r)
                            st.session_state.current_room = rid; st.rerun()

def view_room(room_id: str):
    room = ROOMS().get(room_id)
    if not room: st.warning("房间不存在或已过期"); st.session_state.current_room=None; return
    my_key = st.session_state.player_key
    if my_key not in room["players"]: st.warning("你不在该房间"); st.session_state.current_room=None; return

    meta = GAMES[room["game"]]; is_host = (my_key == room["host_key"])
    st.header(f"🛖 房间 {room_id}｜{meta['title']}")

    c1,c2,c3 = st.columns(3)
    with c1:
        new_name = st.text_input("我的昵称", value=room["players"][my_key]["name"])
        if new_name != room["players"][my_key]["name"]:
            room["players"][my_key]["name"]=new_name; mark_active(room)
    with c2:
        seats = list(range(room["max_players"]))
        others = {p.get("seat") for k,p in room["players"].items() if k!=my_key}
        cur = room["players"][my_key].get("seat",0)
        idx = seats.index(cur) if cur in seats else 0
        new_seat = st.selectbox("选择座位（顺时针）", seats, index=idx)
        if new_seat != cur:
            if new_seat in others: st.error("座位已被占用")
            else: room["players"][my_key]["seat"]=new_seat; mark_active(room)
    with c3:
        ready = st.toggle("准备", value=room["players"][my_key].get("ready", False))
        if ready != room["players"][my_key].get("ready", False):
            room["players"][my_key]["ready"]=ready; mark_active(room)

    st.subheader("玩家列表")
    cols = st.columns(2)
    for i,(pid,p) in enumerate(sorted(room["players"].items(), key=lambda x:(x[1].get('seat') is None, x[1].get('seat',0)))):
        with cols[i%2]:
            st.write(f"**{p['name']}**｜座位 {p.get('seat','-')}｜资金：{p.get('money',20000)}｜{'✅已准备' if p.get('ready') else '⬜未准备'}")
            if is_host and pid != room["host_key"]:
                if st.button(f"踢出 {p['name']}", key=f"kick_{pid}"):
                    del room["players"][pid]; mark_active(room); st.rerun()

    st.markdown("---"); st.subheader("房主控制")
    room["max_players"] = st.slider("人数上限", 2, 12, room["max_players"])
    if meta["supports_lang"]: st.info(f"卡面语言（仅字字转机；开局后锁定）：{room.get('game_lang','zh')}")
    else: st.caption("本游戏不涉及卡面语言切换")

    all_ready = (len(room["players"])>=2) and all(p.get("seat") is not None and p.get("ready") for p in room["players"].values())
    if st.button("开始游戏", disabled=not (is_host and all_ready)):
        room["stage"]="playing"; room["game_state"]={}; mark_active(room); st.rerun()

    st.markdown("---")
    if st.button("返回大厅"): st.session_state.current_room=None; st.rerun()

def view_playing(room_id: str):
    room = ROOMS().get(room_id)
    if not room: st.session_state.current_room=None; st.rerun(); return
    my_key = st.session_state.player_key
    if my_key not in room["players"]: st.session_state.current_room=None; st.rerun(); return

    meta = GAMES[room["game"]]
    st.header(f"🎮 对局中｜{meta['title']}｜房间 {room_id}")

    def emit_settlement(transfers: Dict[str,int], note: str = ""):
        if apply_settlement_to_room(room, transfers):
            room["stage"]="finished"; room["game_state"]["last_settlement"]={"transfers":transfers,"note":note,"ts":now_ts()}
            st.success("结算成功。已进入结束页。")
        else:
            st.error("结算失败：请检查是否零和。")

    try:
        meta["module"].run(room, my_key, emit_settlement)
    except Exception as e:
        st.error(f"子游戏运行出错：{e}")

    st.markdown("---")
    if st.button("返回准备页"): room["stage"]="lobby"; mark_active(room); st.rerun()
    if st.button("返回大厅"): st.session_state.current_room=None; st.rerun()

def view_finished(room_id: str):
    room = ROOMS().get(room_id)
    if not room: st.session_state.current_room=None; st.rerun(); return
    meta = GAMES[room["game"]]
    st.header(f"🏁 本局已结束｜{meta['title']}｜房间 {room_id}")

    report = room["game_state"].get("last_settlement")
    if report:
        st.subheader("结算明细（零和）")
        transfers = report["transfers"]
        for pid,delta in sorted(transfers.items(), key=lambda x:-x[1]):
            name = room["players"].get(pid,{}).get("name",pid)
            st.write(f"{name}：{'+' if delta>=0 else ''}{delta}")
        if report.get("note"): st.caption(f"备注：{report['note']}")
    else:
        st.info("本局未提交结算。")

    st.markdown("---"); st.subheader("房间钱包（最新）")
    for pid,p in sorted(room["players"].items(), key=lambda x:(x[1].get('seat') is None, x[1].get('seat',0))):
        st.write(f"{p['name']}｜资金：{p.get('money',20000)}")

    st.markdown("---")
    if st.button("返回准备页"): room["stage"]="lobby"; mark_active(room); st.rerun()
    if st.button("返回大厅"): st.session_state.current_room=None; st.rerun()

def main():
    room_id = st.session_state.current_room
    if not room_id: view_hub(); return
    room = ROOMS().get(room_id)
    if not room: st.session_state.current_room=None; st.rerun(); return
    stage = room["stage"]
    if stage=="lobby": view_room(room_id)
    elif stage=="playing": view_playing(room_id)
    elif stage=="finished": view_finished(room_id)
    else: view_hub()

if __name__ == "__main__":
    main()

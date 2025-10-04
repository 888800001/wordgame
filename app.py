import streamlit as st
import random
import time
from datetime import datetime, timedelta

# ===================== 初始化房间状态 =====================
if "ROOMS" not in st.session_state:
    st.session_state["ROOMS"] = {}

ROOMS = st.session_state["ROOMS"]

# ===================== 房间工具函数 =====================

def clean_expired_rooms():
    """清理超过5分钟未活动的房间"""
    now = datetime.now()
    expired = []
    for rid, room in list(ROOMS.items()):
        if now - room["last_active"] > timedelta(minutes=5):
            expired.append(rid)
    for rid in expired:
        del ROOMS[rid]

def create_room(room_id: str, max_players: int):
    """创建一个新房间"""
    if room_id in ROOMS:
        return False, "❌ 房间号已存在，请换一个！"
    ROOMS[room_id] = {
        "players": {},  # {player_id: {"name": str, "money": int, "ready": bool}}
        "max_players": max_players,
        "game": None,
        "last_active": datetime.now(),
    }
    return True, f"✅ 房间 {room_id} 创建成功！"

def join_room(room_id: str, player_id: str, name: str):
    """加入房间"""
    if room_id not in ROOMS:
        return False, "❌ 房间不存在。"
    room = ROOMS[room_id]
    if len(room["players"]) >= room["max_players"]:
        return False, "❌ 房间已满。"
    if player_id not in room["players"]:
        room["players"][player_id] = {"name": name, "money": 20000, "ready": False}
    room["last_active"] = datetime.now()
    return True, f"✅ {name} 加入了房间 {room_id}。"

def toggle_ready(room_id: str, player_id: str):
    """切换准备状态"""
    player = ROOMS[room_id]["players"][player_id]
    player["ready"] = not player["ready"]
    ROOMS[room_id]["last_active"] = datetime.now()

def all_ready(room_id: str):
    """检查是否所有人都已准备"""
    room = ROOMS[room_id]
    if not room["players"]:
        return False
    return all(p["ready"] for p in room["players"].values())

def leave_room(room_id: str, player_id: str):
    """离开房间"""
    if room_id in ROOMS and player_id in ROOMS[room_id]["players"]:
        del ROOMS[room_id]["players"][player_id]
        ROOMS[room_id]["last_active"] = datetime.now()

def get_room_summary(room_id: str):
    """显示房间信息"""
    room = ROOMS.get(room_id)
    if not room:
        return "房间不存在。"
    players = "\n".join(
        [f"- {p['name']}｜💰{p['money']}｜{'✅准备' if p['ready'] else '❌未准备'}"
         for p in room["players"].values()]
    )
    return f"房间号：{room_id}\n人数：{len(room['players'])}/{room['max_players']}\n\n{players}"

# ===================== 主界面逻辑 =====================

def view_hub():
    """大厅界面"""
    st.title("🎮 桌游团建大厅 | Game Hub")

    clean_expired_rooms()

    st.subheader("创建或加入房间")

    # 创建房间
    with st.expander("🆕 创建房间"):
        room_id_input = st.text_input("输入房间号（默认随机4位）", value=str(random.randint(1000, 9999)))
        max_players = st.slider("最大人数", 2, 8, 4)
        if st.button("创建房间"):
            ok, msg = create_room(room_id_input, max_players)
            st.toast(msg)
            if ok:
                st.session_state["current_room"] = room_id_input
                st.rerun()

    # 加入房间
    with st.expander("🚪 加入房间"):
        join_id = st.text_input("输入房间号", key="join_room_input")
        player_name = st.text_input("你的昵称", key="join_name")
        if st.button("加入"):
            player_id = f"user_{random.randint(100000, 999999)}"
            ok, msg = join_room(join_id, player_id, player_name or player_id)
            st.toast(msg)
            if ok:
                st.session_state["current_room"] = join_id
                st.session_state["player_id"] = player_id
                st.rerun()

    st.divider()
    st.subheader("📋 当前房间列表（最近活动）")

    if not ROOMS:
        st.info("暂无活跃房间，快来创建一个吧！")
    else:
        for rid, room in ROOMS.items():
            st.write(f"房间 {rid} ｜ {len(room['players'])}/{room['max_players']} 人 ｜ 最近活动：{room['last_active'].strftime('%H:%M:%S')}")

def view_room(room_id: str, player_id: str):
    """房间内部界面"""
    room = ROOMS.get(room_id)
    if not room:
        st.error("房间不存在或已过期。")
        if st.button("返回大厅"):
            del st.session_state["current_room"]
            st.rerun()
        return

    st.title(f"🏠 房间 {room_id}")
    st.caption(f"当前人数：{len(room['players'])}/{room['max_players']}")

    player = room["players"].get(player_id)
    if not player:
        st.error("你似乎不在这个房间。")
        if st.button("返回大厅"):
            del st.session_state["current_room"]
            st.rerun()
        return

    st.markdown(get_room_summary(room_id))

    col1, col2 = st.columns(2)
    with col1:
        if st.button("切换准备状态"):
            toggle_ready(room_id, player_id)
            st.rerun()
    with col2:
        if st.button("退出房间"):
            leave_room(room_id, player_id)
            del st.session_state["current_room"]
            st.rerun()

    st.divider()

    # 房主操作（第一个加入的人为房主）
    player_keys = list(room["players"].keys())
    host_id = player_keys[0] if player_keys else None
    if player_id == host_id:
        st.success("你是房主，可以开始游戏。")
        game_choice = st.selectbox("选择游戏", ["字字转机", "德州扑克", "十点半"])
        if st.button("开始游戏", disabled=not all_ready(room_id)):
            room["game"] = game_choice
            st.session_state["in_game"] = True
            st.toast(f"🎮 游戏开始：{game_choice}")
            st.rerun()
    else:
        st.info("等待房主开始游戏...")

def run_game(room_id: str, player_id: str):
    """游戏分发逻辑"""
    game = ROOMS[room_id]["game"]
    st.title(f"🎯 当前游戏：{game}")

    if game == "字字转机":
        from games import word
        word.run(room_id, player_id, ROOMS)
    elif game == "德州扑克":
        from games import poker
        poker.run(room_id, player_id, ROOMS)
    elif game == "十点半":
        from games import tenhalf
        tenhalf.run(room_id, player_id, ROOMS)
    else:
        st.error("未知游戏类型。")

    st.divider()
    if st.button("🏠 返回大厅"):
        ROOMS[room_id]["game"] = None
        st.session_state["in_game"] = False
        st.rerun()

# ===================== 主程序入口 =====================
def main():
    st.set_page_config(page_title="桌游团建平台", page_icon="🎲", layout="centered")

    room_id = st.session_state.get("current_room")
    player_id = st.session_state.get("player_id")
    in_game = st.session_state.get("in_game", False)

    if not room_id:
        view_hub()
        return
    if in_game:
        run_game(room_id, player_id)
    else:
        view_room(room_id, player_id)

if __name__ == "__main__":
    main()

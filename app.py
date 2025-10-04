import streamlit as st
import time
from utils import room_manager, user_manager
from games import word, poker, tenhalf

# ========== 页面配置 ==========
st.set_page_config(page_title="WordGame 大厅", page_icon="🎮", layout="centered")

# ========== 初始化全局状态 ==========
if "users" not in st.session_state:
    st.session_state.users = {}  # {ip: {"name": str, "coins": int}}
if "rooms" not in st.session_state:
    st.session_state.rooms = {}  # {room_id: {...}}
if "current_room" not in st.session_state:
    st.session_state.current_room = None
if "current_game" not in st.session_state:
    st.session_state.current_game = None
if "ip" not in st.session_state:
    st.session_state.ip = f"user_{int(time.time()*1000)%100000}"  # 模拟唯一 IP
if "name" not in st.session_state:
    st.session_state.name = ""
if "last_active" not in st.session_state:
    st.session_state.last_active = time.time()

# ========== 登录界面 ==========
def login_screen():
    st.title("🎮 WordGame 平台大厅")
    st.write("欢迎来到多人桌游大厅，请输入昵称开始游戏。")

    name = st.text_input("请输入你的昵称：", value=st.session_state.name)
    if st.button("进入大厅"):
        if not name.strip():
            st.warning("请输入昵称！")
            return
        st.session_state.name = name.strip()
        user_manager.create_user(st.session_state.users, st.session_state.ip, name)
        st.success(f"欢迎你，{name}！")
        st.session_state.current_room = None
        st.session_state.current_game = None
        st.rerun()

# ========== 房间大厅 ==========
def lobby_screen():
    st.header("🏠 游戏大厅")
    st.write(f"你好，{st.session_state.name}（💰 {user_manager.get_balance(st.session_state.users, st.session_state.ip)} 金币）")

    col1, col2 = st.columns(2)
    with col1:
        new_room = st.text_input("输入自定义房间号（可选，4位数字）", "")
        is_long = st.checkbox("创建为长期房间（金币长期保存）", value=False)
        if st.button("创建房间"):
            room_id = room_manager.create_room(st.session_state.rooms, st.session_state.ip, st.session_state.name, new_room, is_long)
            if room_id:
                st.session_state.current_room = room_id
                st.rerun()
            else:
                st.error("房间号无效或已存在，请换一个！")

    with col2:
        join_room = st.text_input("加入已有房间号：", "")
        if st.button("加入房间"):
            if room_manager.join_room(st.session_state.rooms, join_room, st.session_state.ip, st.session_state.name):
                st.session_state.current_room = join_room
                st.rerun()
            else:
                st.error("房间不存在或已满。")

    st.divider()
    st.subheader("📜 当前存在的房间")
    if not st.session_state.rooms:
        st.info("当前没有活跃房间，快创建一个吧！")
    else:
        for rid, info in st.session_state.rooms.items():
            st.write(f"房间 {rid} | 房主：{info['owner_name']} | 玩家数：{len(info['players'])} | {'长期房间' if info['is_long'] else '临时房间'}")

# ========== 房间界面 ==========
def room_screen(room_id):
    room = st.session_state.rooms.get(room_id)
    if not room:
        st.warning("⚠️ 房间不存在或已被销毁。")
        if st.button("返回大厅"):
            st.session_state.current_room = None
            st.rerun()
        return

    st.title(f"🕹️ 房间 {room_id}")
    st.caption(f"房主：{room['owner_name']} | 类型：{'长期' if room['is_long'] else '短期'}")
    players = room["players"]

    # --- 玩家列表 ---
    st.subheader("玩家列表")
    for pid, pdata in players.items():
        ready_state = "✅ 已准备" if pdata["ready"] else "⏳ 未准备"
        host_mark = "👑" if pid == room["owner_ip"] else ""
        st.write(f"{host_mark} {pdata['name']} | 💰 {pdata['coins']} 金币 | {ready_state}")

    st.divider()
    current_ip = st.session_state.ip
    if current_ip == room["owner_ip"]:
        if st.button("开始游戏", use_container_width=True):
            if all(p["ready"] for p in players.values()) and len(players) >= 2:
                st.session_state.current_game = room["selected_game"]
                st.success(f"游戏 {room['selected_game']} 开始！")
                room_manager.start_game(room, st.session_state.current_game)
                st.rerun()
            else:
                st.warning("至少两位玩家并全部准备后才能开始游戏！")
    else:
        # 玩家准备按钮
        if st.button("切换准备状态", use_container_width=True):
            room_manager.toggle_ready(room, current_ip)
            st.rerun()

    st.divider()
    st.subheader("🎲 选择游戏")
    options = ["字字转机", "德州扑克", "十点半"]
    selected = st.radio("选择本局游戏", options, index=options.index(room["selected_game"]))
    if selected != room["selected_game"]:
        room["selected_game"] = selected
        st.experimental_rerun()

    if st.button("退出房间", use_container_width=True):
        room_manager.leave_room(st.session_state.rooms, room_id, current_ip)
        st.session_state.current_room = None
        st.rerun()

# ========== 游戏中 ==========
def game_screen():
    game_name = st.session_state.current_game
    room_id = st.session_state.current_room
    if game_name == "字字转机":
        word.run_game(room_id, st.session_state.rooms, st.session_state.users)
    elif game_name == "德州扑克":
        poker.run_game(room_id, st.session_state.rooms, st.session_state.users)
    elif game_name == "十点半":
        tenhalf.run_game(room_id, st.session_state.rooms, st.session_state.users)
    else:
        st.error("未知的游戏类型。")
    if st.button("返回大厅"):
        st.session_state.current_game = None
        st.session_state.current_room = None
        st.rerun()

# ========== 页面路由 ==========
if not st.session_state.name:
    login_screen()
elif st.session_state.current_room is None:
    lobby_screen()
elif st.session_state.current_game is None:
    room_screen(st.session_state.current_room)
else:
    game_screen()

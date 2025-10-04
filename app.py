import streamlit as st
import random, time, uuid
from utils.room_manager import create_room, get_room, join_room, clean_expired_rooms
from utils.user_manager import create_user, update_balance
from utils.game_state import GameState
from games import word, poker, tenhalf

# ========== 页面设置 ==========
st.set_page_config(page_title="🎮 字字转机游戏平台", page_icon="🎲", layout="wide")

# ========== 初始化 ==========
if "user" not in st.session_state:
    st.session_state["user"] = create_user()
if "view" not in st.session_state:
    st.session_state["view"] = "hub"
if "room_id" not in st.session_state:
    st.session_state["room_id"] = None

user = st.session_state["user"]
current_view = st.session_state["view"]
room_id = st.session_state["room_id"]

# ========== 工具函数 ==========
def switch_view(view_name: str, room_id=None):
    st.session_state["view"] = view_name
    st.session_state["room_id"] = room_id

# ========== 大厅界面 ==========
def view_hub():
    st.title("🎮 字字转机｜游戏大厅")
    st.caption("创建或加入房间，与朋友一起玩！")

    clean_expired_rooms()  # 清理过期房间

    with st.form("create_form"):
        st.subheader("🏠 创建房间")
        input_room = st.text_input("输入自定义4位房间号（可选）", "")
        max_players = st.number_input("最多玩家数", min_value=2, max_value=6, value=4)
        game_type = st.selectbox("选择游戏", ["字字转机", "德州扑克", "十点半"])
        submitted = st.form_submit_button("创建房间")

        if submitted:
            room_code = input_room.strip() if input_room else str(random.randint(1000, 9999))
            if not room_code.isdigit() or len(room_code) != 4:
                st.error("❌ 房间号必须是4位数字")
                return
            room = get_room(room_code)
            if room:
                st.error("❌ 房间号已存在，请换一个")
                return
            create_room(room_code, max_players, game_type)
            join_room(room_code, user, is_host=True)
            switch_view("room", room_code)
            st.rerun()

    st.markdown("---")

    with st.form("join_form"):
        st.subheader("🚪 加入房间")
        join_code = st.text_input("输入房间号").strip()
        join_submit = st.form_submit_button("加入房间")

        if join_submit:
            room = get_room(join_code)
            if not room:
                st.error("❌ 房间不存在")
                return
            if len(room["players"]) >= room["max_players"]:
                st.error("⚠️ 房间已满")
                return
            join_room(join_code, user)
            switch_view("room", join_code)
            st.rerun()

# ========== 房间界面 ==========
def view_room():
    rid = st.session_state["room_id"]
    room = get_room(rid)
    if not room:
        st.error("❌ 房间不存在或已过期。")
        st.button("返回大厅", on_click=lambda: switch_view("hub"))
        return

    player_ids = [p["id"] for p in room["players"]]
    if user["id"] not in player_ids:
        st.error("你似乎不在这个房间。")
        st.button("返回大厅", on_click=lambda: switch_view("hub"))
        return

    st.header(f"🏠 房间 {rid}")
    st.caption(f"当前人数：{len(room['players'])}/{room['max_players']}")
    st.markdown("---")

    for p in room["players"]:
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.write(f"👤 {p['name']}")
        col2.write(f"💰 {p['coins']}")
        col3.write("✅ 已准备" if p["is_ready"] else "⏳ 未准备")

    st.markdown("---")

    if st.button("切换准备状态"):
        for p in room["players"]:
            if p["id"] == user["id"]:
                p["is_ready"] = not p["is_ready"]
        st.rerun()

    # 仅房主能开始游戏
    if any(p["id"] == user["id"] and p.get("is_host") for p in room["players"]):
        all_ready = all(p["is_ready"] for p in room["players"])
        if st.button("🚀 开始游戏", disabled=not all_ready):
            room["status"] = "playing"
            st.rerun()

    st.markdown("---")
    st.button("返回大厅", on_click=lambda: switch_view("hub"))

# ========== 游戏入口 ==========
def view_game():
    rid = st.session_state["room_id"]
    room = get_room(rid)
    if not room:
        st.error("❌ 房间不存在。")
        st.button("返回大厅", on_click=lambda: switch_view("hub"))
        return

    game = room["game"]
    if game == "字字转机":
        word.run(room, user)
    elif game == "德州扑克":
        poker.run(room, user)
    elif game == "十点半":
        tenhalf.run(room, user)
    else:
        st.error("未定义的游戏类型。")

    st.markdown("---")
    st.button("🏠 返回大厅", on_click=lambda: switch_view("hub"))

# ========== 主流程 ==========
def main():
    clean_expired_rooms()
    if current_view == "hub":
        view_hub()
    elif current_view == "room":
        rid = st.session_state["room_id"]
        room = get_room(rid)
        if not room:
            switch_view("hub")
            st.rerun()
        elif room.get("status") == "playing":
            view_game()
        else:
            view_room()

if __name__ == "__main__":
    main()

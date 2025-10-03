# app.py
# -------------------------------------------------------
# 字字转机 · 线下桌游“手机裁判 & 卡牌集成器”
# 玩法：线下抢答；本程序只负责：房间管理、出牌、规则、对决判定、积分与“3秒可中断抢牌”
# -------------------------------------------------------

import streamlit as st
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Tuple, Dict

# ========== 基础配置 ==========
st.set_page_config(page_title="字字转机｜线下房间", page_icon="👾", layout="wide")

# ========== 全局房间存储（简单内存版） ==========
# 注意：这是内存存储，适合线下 Demo。若要长期稳定，请换成数据库/后端服务。
@st.cache_resource
def get_rooms() -> Dict[str, dict]:
    return {}

ROOMS = get_rooms()

# ========== 数据结构 ==========
Alien = Literal["狼", "兔", "猫", "牛", "鹰", "象"]  # 可扩展
CardType = Literal["CATEGORY", "RULE"]

@dataclass
class CategoryCard:
    type: CardType
    alien: Alien
    category_cn: str
    category_en: str

@dataclass
class RuleCard:
    type: CardType
    rule_name: str
    # 规则：("PAIR_FORCE_DUEL", ("狼","兔")) 表示狼&兔也必须对决；None 表示仅同外星人
    payload: Optional[Tuple[str, Optional[Tuple[Alien, Alien]]]] = None

@dataclass
class PlayerState:
    uid: str           # 唯一 id（本地会话生成）
    name: str
    seat: Optional[int] = None       # 座位（顺时针次序）
    ready: bool = False
    pile: List[CategoryCard] = field(default_factory=list)     # 桌面叠（只看顶牌）
    score_cards: List[CategoryCard] = field(default_factory=list)  # 赢到的记分牌
    score_grab: int = 0   # “3秒抢牌”额外积分（每抢一张+1）

# ========== 卡组 & 词汇 ==========
ALIENS: List[Alien] = ["狼", "兔", "猫", "牛", "鹰", "象"]

CATEGORY_POOL = [
    ("水果", "Fruit"),
    ("交通工具", "Transport"),
    ("童话人物", "Fairy Tale Character"),
    ("垃圾食品", "Junk Food"),
    ("动物", "Animal"),
    ("乐器", "Instrument"),
    ("文具", "Stationery"),
    ("运动项目", "Sport"),
]

def build_deck() -> List:
    deck: List = []
    for alien in ALIENS:
        for cn, en in CATEGORY_POOL:
            deck.append(CategoryCard(type="CATEGORY", alien=alien, category_cn=cn, category_en=en))
    rule_cards: List[RuleCard] = [
        RuleCard(type="RULE", rule_name="仅同外星人对决", payload=("SAME_ALIEN_ONLY", None)),
        RuleCard(type="RULE", rule_name="狼&兔也必须对决", payload=("PAIR_FORCE_DUEL", ("狼", "兔"))),
        RuleCard(type="RULE", rule_name="猫&牛也必须对决", payload=("PAIR_FORCE_DUEL", ("猫", "牛"))),
        RuleCard(type="RULE", rule_name="鹰&象也必须对决", payload=("PAIR_FORCE_DUEL", ("鹰", "象"))),
    ]
    deck.extend(rule_cards)
    random.shuffle(deck)
    return deck

# ========== 规则判定 ==========
def should_duel(card_a: Optional[CategoryCard], card_b: Optional[CategoryCard], active_rule: RuleCard) -> bool:
    if not card_a or not card_b: return False
    tag, pair = active_rule.payload if active_rule.payload else ("SAME_ALIEN_ONLY", None)
    if tag == "SAME_ALIEN_ONLY":
        return card_a.alien == card_b.alien
    if tag == "PAIR_FORCE_DUEL" and pair:
        same = (card_a.alien == card_b.alien)
        forced = set(pair) == set([card_a.alien, card_b.alien])
        return same or forced
    return card_a.alien == card_b.alien

# ========== 工具 ==========
def gen_uid() -> str:
    return f"u{random.randint(100000, 999999)}"

def init_room(room_id: str, host_uid: str, host_name: str, max_players: int):
    ROOMS[room_id] = {
        "room_id": room_id,
        "host_uid": host_uid,
        "max_players": max_players,
        "players": {host_uid: PlayerState(uid=host_uid, name=host_name).__dict__},
        "stage": "lobby",   # lobby -> playing -> ended
        "deck": [],
        "active_rule": RuleCard(type="RULE", rule_name="仅同外星人对决", payload=("SAME_ALIEN_ONLY", None)).__dict__,
        "turn_idx": 0,     # 指向「seat 排序」的索引
        "duel": None,      # {"a": uid, "b": uid, "buffer": [cards...]}
        "countdown": None, # {"ends_at": ts, "reason": "flip/duel/tie"}
        "last_action_ts": time.time(),
    }

def get_player_order(room) -> List[str]:
    # 返回按 seat 从小到大的 uid 列表（仅已选座位的玩家）
    seated = [(p["seat"], uid) for uid, p in room["players"].items() if p["seat"] is not None]
    seated.sort(key=lambda x: x[0])
    return [uid for _, uid in seated]

def top_card_of(room, uid: str) -> Optional[CategoryCard]:
    p = room["players"][uid]
    return p["pile"][-1] if p["pile"] else None

def set_countdown(room, seconds: int, reason: str):
    room["countdown"] = {"ends_at": time.time() + seconds, "reason": reason}

def in_countdown(room) -> bool:
    cd = room.get("countdown")
    return bool(cd and cd["ends_at"] > time.time())

def cancel_countdown(room):
    room["countdown"] = None

# ========== 房间/玩家 本地状态 ==========
if "uid" not in st.session_state:
    st.session_state.uid = gen_uid()
if "my_room" not in st.session_state:
    st.session_state.my_room = None   # 当前加入的房间 id
if "my_name" not in st.session_state:
    st.session_state.my_name = f"玩家{random.randint(1, 99)}"

# ========== 视图：大厅 ==========
def view_lobby():
    st.header("👾 字字转机 · 房间大厅")

    tab_create, tab_join = st.tabs(["创建房间（房主）", "加入房间（成员）"])

    with tab_create:
        st.subheader("创建房间")
        host_name = st.text_input("我的昵称", value=st.session_state.my_name, key="host_name")
        room_id = st.text_input("自定义房间号（建议简单如 1234）", value=str(random.randint(1000, 9999)))
        max_players = st.slider("最大人数上限", 2, 10, 6, 1)
        if st.button("创建房间"):
            init_room(room_id, st.session_state.uid, host_name, max_players)
            st.session_state.my_room = room_id
            st.session_state.my_name = host_name
            st.success(f"房间已创建：{room_id}，你是房主。")
            st.rerun()

    with tab_join:
        st.subheader("加入房间")
        name = st.text_input("我的昵称", value=st.session_state.my_name, key="join_name")
        room_id = st.text_input("输入房间号")
        if st.button("加入"):
            if room_id not in ROOMS:
                st.error("房间不存在。")
            else:
                room = ROOMS[room_id]
                if len(room["players"]) >= room["max_players"]:
                    st.error("房间已满。")
                else:
                    room["players"][st.session_state.uid] = PlayerState(uid=st.session_state.uid, name=name).__dict__
                    st.session_state.my_room = room_id
                    st.session_state.my_name = name
                    st.success(f"已加入房间：{room_id}")
                    st.rerun()

    st.markdown("---")
    st.caption("提示：这是共享内存 Demo。要多人同时使用，请把同一个网址分享给朋友，大家各自手机进入同一房间号。")

# ========== 视图：房间准备 ==========
def view_room(room_id: str):
    if room_id not in ROOMS:
        st.warning("房间不存在或已被关闭。")
        if st.button("返回大厅"):
            st.session_state.my_room = None
        return

    room = ROOMS[room_id]
    is_host = (room["host_uid"] == st.session_state.uid)
    st.header(f"🛖 房间 {room_id}（上限 {room['max_players']} 人）")
    st.write(f"当前阶段：**{ '准备中' if room['stage']=='lobby' else ('进行中' if room['stage']=='playing' else '已结束') }**")

    # = 名称、座位、准备 =
    me = room["players"][st.session_state.uid]
    c1, c2, c3, c4 = st.columns([2,2,2,2])
    with c1:
        new_name = st.text_input("我的昵称", value=me["name"])
        if new_name != me["name"]:
            me["name"] = new_name
            st.session_state.my_name = new_name
    with c2:
        seats = list(range(0, room["max_players"]))
        seat = st.selectbox("选择座位（顺时针）", seats, index=seats.index(me["seat"]) if me["seat"] in seats else 0)
        if seat != me.get("seat"):
            # 座位冲突则拒绝
            occupied = {p["seat"] for uid, p in room["players"].items() if uid != st.session_state.uid}
            if seat in occupied:
                st.error("该座位已被占用。")
            else:
                me["seat"] = seat
    with c3:
        if st.toggle("准备/Ready", value=me.get("ready", False)):
            me["ready"] = True
        else:
            me["ready"] = False
    with c4:
        if st.button("退出房间"):
            if is_host and len(room["players"]) > 1:
                st.error("房主不能直接退出，请移交房主或解散房间。")
            else:
                del room["players"][st.session_state.uid]
                st.session_state.my_room = None
                st.rerun()

    # = 玩家列表 =
    st.subheader("玩家列表")
    cols = st.columns(4)
    for i, (uid, p) in enumerate(room["players"].items()):
        with cols[i % 4]:
            st.markdown(f"**{p['name']}**  | 座位：{p['seat']}  | {'✅已准备' if p['ready'] else '⬜未准备'}")
            if is_host and uid != room["host_uid"]:
                if st.button(f"踢出：{p['name']}", key=f"kick_{uid}"):
                    del room["players"][uid]
                    st.toast(f"已踢出 {p['name']}")
                    st.rerun()

    # = 房主设置 =
    if is_host and room["stage"] == "lobby":
        st.markdown("---")
        st.subheader("房主控制")
        room["max_players"] = st.slider("调整房间上限", 2, 10, room["max_players"], 1)
        all_ready = (len(room["players"]) >= 2) and all(p["ready"] and p["seat"] is not None for p in room["players"].values())
        st.write(f"当前已就位：{sum(p['seat'] is not None for p in room['players'].values())} / {room['max_players']}")
        if st.button("开始游戏", disabled=not all_ready):
            # 初始化牌堆、规则、回合
            room["deck"] = [c.__dict__ for c in build_deck()]
            room["active_rule"] = RuleCard(type="RULE", rule_name="仅同外星人对决",
                                           payload=("SAME_ALIEN_ONLY", None)).__dict__
            room["turn_idx"] = 0
            for p in room["players"].values():
                p["pile"] = []
                p["score_cards"] = []
                p["score_grab"] = 0
            room["duel"] = None
            room["stage"] = "playing"
            st.success("游戏开始！")
            st.rerun()

    st.markdown("---")
    if st.button("刷新"):
        st.rerun()

# ========== 视图：游戏主界面 ==========
def view_game(room_id: str):
    room = ROOMS.get(room_id)
    if not room or room["stage"] != "playing":
        st.warning("游戏未开始。")
        if st.button("返回房间"):
            st.rerun()
        return

    is_host = (room["host_uid"] == st.session_state.uid)
    order = get_player_order(room)
    if not order:
        st.warning("无人就位。")
        return

    st.header(f"🎮 对局中 · 房间 {room_id}")

    # 顶部信息
    left, mid, right = st.columns([2,2,2])
    with left:
        st.info(f"当前规则：**{room['active_rule']['rule_name']}**")
    with mid:
        st.metric("剩余牌数", len(room["deck"]))
    with right:
        if st.button("🔄 返回准备（房主）", disabled=not is_host):
            room["stage"] = "lobby"
            st.rerun()

    # 中心：规则牌区域 + 倒计时
    st.markdown("---")
    center = st.container()
    with center:
        cd = room.get("countdown")
        if cd and cd["ends_at"] > time.time():
            remaining = max(0, int(cd["ends_at"] - time.time()))
            st.warning(f"⏱️ 倒计时 {remaining} 秒（原因：{cd['reason']}）——**任意玩家可在倒计时内抢牌**")
        else:
            room["countdown"] = None

    # 玩家圈布局（简化为行列自适应）
    st.subheader("玩家圈")
    cols = st.columns(min(6, len(order)))  # 每行最多 6 个

    # 回合指示
    current_uid = order[room["turn_idx"]] if room["turn_idx"] < len(order) else order[0]

    # --- 玩家格子 ---
    seat_to_col = {}
    for idx, uid in enumerate(order):
        p = room["players"][uid]
        col = cols[idx % len(cols)]
        seat_to_col[p["seat"]] = col

    def draw_one(uid: str):
        if not room["deck"]:
            st.toast("牌堆用尽。")
            return
        card = room["deck"].pop()
        if card["type"] == "RULE":
            room["active_rule"] = card
            st.toast(f"🧩 规则更新：{card['rule_name']}")
            # 翻到规则牌也触发 3 秒倒计时（给人反应/抢牌）
            set_countdown(room, 3, "翻到规则牌")
        else:
            room["players"][uid]["pile"].append(card)
            set_countdown(room, 3, "翻出普通牌")
            # 检查是否与任意玩家触发对决
            my_top = room["players"][uid]["pile"][-1]
            for other_uid in order:
                if other_uid == uid: continue
                other_top = top_card_of(room, other_uid)
                if should_duel(CategoryCard(**my_top) if my_top else None,
                               CategoryCard(**other_top) if other_top else None,
                               RuleCard(**room["active_rule"])):
                    # 进入对决
                    room["duel"] = {
                        "a": uid,
                        "b": other_uid,
                        "buffer": [my_top] + ([other_top] if other_top else [])
                    }
                    st.toast(f"⚔️ 对决触发：{room['players'][uid]['name']} vs {room['players'][other_uid]['name']}")
                    break

        # 轮转回合（若未进入对决）
        if room["duel"] is None:
            room["turn_idx"] = (room["turn_idx"] + 1) % len(order)

    # 抢牌（3秒内）
    def grab_card(target_uid: str, winner_uid: str):
        if not in_countdown(room):
            st.toast("倒计时已结束，不能抢。")
            return
        pile = room["players"][target_uid]["pile"]
        if not pile:
            st.toast("该玩家没有可抢的顶牌。")
            return
        card = pile.pop()
        room["players"][winner_uid]["score_grab"] += 1
        cancel_countdown(room)
        st.toast(f"🎯 抢牌成功！{room['players'][winner_uid]['name']} +1 积分（抢走 {room['players'][target_uid]['name']} 的牌）")

    # 判定对决胜者 / 平手
    def settle_duel_winner(winner_uid: str):
        duel = room["duel"]
        if not duel: return
        buffer_cards = duel["buffer"][:]  # 奖池
        # 双方当前叠也清空并计入奖池
        for u in [duel["a"], duel["b"]]:
            buffer_cards.extend(room["players"][u]["pile"])
            room["players"][u]["pile"].clear()
        # 计分到胜者
        room["players"][winner_uid]["score_cards"].extend(buffer_cards)
        room["duel"] = None
        set_countdown(room, 3, "对决结束")
        st.toast(f"🏆 {room['players'][winner_uid]['name']} 赢下本次对决（共 {len(buffer_cards)} 张计分牌）")

    def tie_flip_next():
        duel = room["duel"]
        if not duel: return
        # 双方各再翻一张（可能翻到规则牌，规则立即生效；直到翻到普通牌为止）
        for u in [duel["a"], duel["b"]]:
            while True:
                if not room["deck"]: break
                c = room["deck"].pop()
                if c["type"] == "RULE":
                    room["active_rule"] = c
                    st.toast(f"✨ 平手期间规则更新：{c['rule_name']}")
                    continue
                else:
                    room["players"][u]["pile"].append(c)
                    duel["buffer"].append(c)
                    break
        set_countdown(room, 3, "平手各翻一张")

    # === 渲染每位玩家格子（含操作） ===
    admin_col = st.sidebar
    admin_col.header("操作控制")
    if room["duel"]:
        a_uid, b_uid = room["duel"]["a"], room["duel"]["b"]
        admin_col.subheader("⚔️ 对决中")
        c1, c2, c3 = admin_col.columns(3)
        with c1:
            if st.button(f"✅ {room['players'][a_uid]['name']} 胜"):
                settle_duel_winner(a_uid)
        with c2:
            if st.button(f"✅ {room['players'][b_uid]['name']} 胜"):
                settle_duel_winner(b_uid)
        with c3:
            if st.button("🤝 同时说出（平手）→ 各翻一张"):
                tie_flip_next()

    admin_col.markdown("---")
    admin_col.subheader("⏱️ 抢牌（3秒内任意时刻）")
    target = admin_col.selectbox("被抢牌的玩家", [room["players"][u]["name"] for u in order], index=0, key="grab_target_name")
    winner = admin_col.selectbox("抢到者", [room["players"][u]["name"] for u in order], index=0, key="grab_winner_name")
    name_to_uid = {room["players"][u]["name"]: u for u in order}
    if admin_col.button("🎯 执行抢牌", disabled=not in_countdown(room)):
        grab_card(name_to_uid[target], name_to_uid[winner])
        st.rerun()

    # 玩家格子显示
    for idx, uid in enumerate(order):
        p = room["players"][uid]
        col = cols[idx % len(cols)]
        with col:
            is_turn = (uid == current_uid and room["duel"] is None)
            st.markdown(f"### {p['name']} {'🟢' if is_turn else ''}")
            top = top_card_of(room, uid)
            if top:
                st.success(f"顶牌：{top['alien']}｜{top['category_cn']} ({top['category_en']})")
            else:
                st.warning("顶牌：无")
            st.caption(f"桌面叠：{len(p['pile'])} 张  |  计分牌：{len(p['score_cards'])}  | 抢牌分：{p['score_grab']}")

            # 回合内允许翻牌（非对决时）
            if st.button("翻我下一张", disabled=not is_turn, key=f"flip_{uid}"):
                draw_one(uid)
                st.rerun()

    st.markdown("---")
    if st.button("刷新"):
        st.rerun()

# ========== 入口路由 ==========
def main():
    # 选择房间/准备/对局
    if st.session_state.my_room is None:
        view_lobby()
        return

    room_id = st.session_state.my_room
    room = ROOMS.get(room_id)
    if not room:
        st.session_state.my_room = None
        st.rerun()
        return

    if room["stage"] == "lobby":
        view_room(room_id)
    elif room["stage"] == "playing":
        view_game(room_id)
    else:
        st.header("对局已结束")
        if st.button("返回大厅"):
            st.session_state.my_room = None

if __name__ == "__main__":
    main()

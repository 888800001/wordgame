# app.py
# 字字转机 · 多人房间（语言锁定在准备阶段、角色中英双标签、规则牌、5秒倒计时、0.5s自动刷新、唯一ID重连）
import time
import random
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Tuple, Dict

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------- 基本配置 ----------
st.set_page_config(page_title="字字转机｜多人房间", page_icon="👾", layout="wide")
st_autorefresh(interval=500, key="refresh")  # 0.5 秒自动刷新

# ---------- 读取类别 ----------
@st.cache_data
def load_categories() -> List[dict]:
    # data/categories.csv 两列: category,en
    df = pd.read_csv("data/categories.csv")
    df = df.dropna()
    return df.to_dict("records")

CATEGORIES = load_categories()

# ---------- 全局房间存储（内存） ----------
@st.cache_resource
def ROOMS() -> Dict[str, dict]:
    return {}

# ---------- 类型 ----------
CardType = Literal["CATEGORY", "RULE"]

@dataclass
class CategoryCard:
    type: CardType
    role_key: str       # 用 key 做匹配/equality
    category_cn: str
    category_en: str

@dataclass
class RuleCard:
    type: CardType
    pair_keys: Tuple[str, str]  # 强制对决的两种 role_key（无序对）

@dataclass
class PlayerState:
    player_key: str
    name: str
    seat: Optional[int] = None
    ready: bool = False
    pile: List[dict] = field(default_factory=list)       # 面前叠（存 dict）
    captured: List[dict] = field(default_factory=list)   # 赢到的牌（计分=张数）

# ---------- 角色与语言 ----------
def build_roles(num_players: int) -> List[dict]:
    """
    n 人 → 取 n+1 个角色，每个角色包含：
      {"key": "r0", "cn": "孙行者", "en": "Amy"}
    中文名集：按你习惯先放西游系 + 变体
    英文名集：简单代号（Amy, Jim, Bob...）
    """
    cn_pool = ["孙行者","者行孙","行者孙","牛魔王","白骨精","铁扇公主","沙和尚","猪悟能","红孩儿","金角大王","银角大王"]
    en_pool = ["Amy","Jim","Bob","Eve","Lily","Max","Zoe","Tom","Ada","Ivy","Jay"]

    need = num_players + 1
    roles = []
    for i in range(need):
        cn = cn_pool[i % len(cn_pool)]
        en = en_pool[i % len(en_pool)]
        roles.append({"key": f"r{i}", "cn": cn, "en": en})
    return roles[:need]

def role_label(room: dict, role_key: str) -> str:
    lang = room["lang"]  # "zh" or "en"
    m = {r["key"]: r for r in room["roles"]}
    if role_key not in m:
        return role_key
    return m[role_key]["cn"] if lang == "zh" else m[role_key]["en"]

# ---------- 辅助 ----------
def random_category_pair() -> Tuple[str, str]:
    c = random.choice(CATEGORIES)
    return c["category"], c["en"]

def player_order(room) -> List[str]:
    seated = [(p["seat"], k) for k, p in room["players"].items() if p["seat"] is not None]
    seated.sort(key=lambda x: x[0])
    return [k for _, k in seated]

def top_card(room, key: str) -> Optional[dict]:
    p = room["players"][key]
    return p["pile"][-1] if p["pile"] else None

def make_category_card(room: dict) -> dict:
    cn, en = random_category_pair()
    role_key = random.choice([r["key"] for r in room["roles"]])
    return CategoryCard(type="CATEGORY", role_key=role_key, category_cn=cn, category_en=en).__dict__

def make_rule_cards(room: dict, count: int) -> List[dict]:
    keys = [r["key"] for r in room["roles"]]
    pairs = set()
    out = []
    tries = 0
    while len(pairs) < count and tries < 100:
        a, b = random.sample(keys, 2)
        if a != b:
            pair = tuple(sorted((a, b)))
            if pair not in pairs:
                pairs.add(pair)
                out.append(RuleCard(type="RULE", pair_keys=pair).__dict__)
        tries += 1
    return out

def active_rule_text(room: dict) -> str:
    """根据房间语言把规则牌人名翻译出来"""
    rule = room.get("active_rule")
    if not rule:
        return "无 / None"
    a_key, b_key = rule["pair_keys"]
    a_name = role_label(room, a_key)
    b_name = role_label(room, b_key)
    if room["lang"] == "zh":
        return f"{a_name} 与 {b_name} 也必须对决"
    else:
        return f"{a_name} & {b_name} must duel too"

def should_duel_pair(room, a_key: str, b_key: str) -> bool:
    """同角色 或 命中当前规则牌指定的强制对决"""
    a = top_card(room, a_key)
    b = top_card(room, b_key)
    if not a or not b:
        return False
    same_role = a["role_key"] == b["role_key"]
    forced = False
    rule = room.get("active_rule")
    if rule:
        pair = set(rule["pair_keys"])
        forced = set([a["role_key"], b["role_key"]]) == pair
    return same_role or forced

def find_any_duel(room) -> Optional[Tuple[str, str]]:
    order = player_order(room)
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = order[i], order[j]
            if should_duel_pair(room, a, b):
                return a, b
    return None

def build_deck(room) -> List[dict]:
    """24×人数 的普通牌 + 1~3 张规则牌，全部混洗"""
    n = len(player_order(room))
    cat_count = 24 * n
    rule_count = min(3, max(1, n - 1))
    deck = [make_category_card(room) for _ in range(cat_count)]
    deck += make_rule_cards(room, rule_count)
    random.shuffle(deck)
    return deck

def start_duel(room, a_key: str, b_key: str):
    room["duel"] = {"a": a_key, "b": b_key, "buffer": []}
    room["duel_timer"] = {"ends_at": time.time() + 5}  # 5秒倒计时

def duel_countdown_left(room) -> int:
    t = room.get("duel_timer")
    if not t:
        return 0
    return max(0, int(t["ends_at"] - time.time()))

def stop_duel_timer(room):
    room["duel_timer"] = None

# ---------- 客户端会话 ----------
if "player_key" not in st.session_state:
    st.session_state.player_key = ""
if "my_room" not in st.session_state:
    st.session_state.my_room = None

# ---------- 大厅 ----------
def view_lobby():
    st.header("👾 字字转机 · 房间大厅 | Lobby")
    tabs = st.tabs(["创建房间（房主 / Host）", "加入房间（成员 / Join）"])

    with tabs[0]:
        st.subheader("创建房间 / Create room")
        room_id = st.text_input("房间号 Room ID", value=str(random.randint(1000, 9999)))
        player_key = st.text_input("我的唯一ID Unique Player ID（重连用）", placeholder="e.g. mc_001")
        my_name = st.text_input("昵称 Name", value="玩家A PlayerA")
        max_players = st.slider("人数上限 Max players", 3, 6, 4)
        lang = st.radio("显示语言 Language（开局后不可更改 / locked after start）",
                        options=["中文", "English"], horizontal=True, index=0)
        if st.button("创建 Create"):
            if not player_key:
                st.error("请填写唯一ID / Please enter unique ID.")
                return
            if room_id in ROOMS():
                st.error("房间号已存在 / Room ID exists.")
                return
            lang_code = "zh" if lang == "中文" else "en"
            ROOMS()[room_id] = {
                "room_id": room_id,
                "host_key": player_key,
                "max_players": max_players,
                "lang": lang_code,             # 语言锁定：开局后不再更改
                "players": {player_key: PlayerState(player_key=player_key, name=my_name).__dict__},
                "stage": "lobby",              # lobby / playing / finished
                "roles": [],                   # [{'key','cn','en'}...]
                "deck": [],
                "turn_idx": 0,
                "active_rule": None,           # 当前规则牌（唯一）
                "duel": None,                  # {"a","b","buffer":[]}
                "duel_timer": None,            # {"ends_at": ts}
                "initial_dealt": False
            }
            st.session_state.player_key = player_key
            st.session_state.my_room = room_id
            st.success(f"已创建房间 {room_id}（你是房主）/ Room created (you are host)")
            st.rerun()

    with tabs[1]:
        st.subheader("加入房间 / Join room")
        room_id = st.text_input("输入房间号 Enter Room ID")
        player_key = st.text_input("我的唯一ID Unique Player ID（重连用）", placeholder="e.g. mc_002", key="join_id")
        my_name = st.text_input("昵称 Name", value="玩家B PlayerB", key="join_name")
        if st.button("加入 Join"):
            if room_id not in ROOMS():
                st.error("房间不存在 / Room not found.")
                return
            room = ROOMS()[room_id]
            if player_key in room["players"]:
                room["players"][player_key]["name"] = my_name  # 接管
            else:
                if len(room["players"]) >= room["max_players"]:
                    st.error("房间已满 / Room is full.")
                    return
                room["players"][player_key] = PlayerState(player_key=player_key, name=my_name).__dict__
            st.session_state.player_key = player_key
            st.session_state.my_room = room_id
            st.success("加入成功 / Joined.")
            st.rerun()

# ---------- 准备阶段 ----------
def view_room(room_id: str):
    room = ROOMS().get(room_id)
    if not room:
        st.warning("房间不存在 / Room not found.")
        st.session_state.my_room = None
        return

    me = room["players"].get(st.session_state.player_key)
    is_host = st.session_state.player_key == room["host_key"]

    st.header(f"🛖 房间 {room_id}（上限 {room['max_players']}）| Max {room['max_players']}")

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        new_name = st.text_input("我的昵称 / My name", value=me["name"])
        if new_name != me["name"]:
            me["name"] = new_name
    with c2:
        seats = list(range(room["max_players"]))
        occ = {p["seat"] for k, p in room["players"].items() if k != st.session_state.player_key}
        idx = me["seat"] if me["seat"] in seats else 0
        seat = st.selectbox("选择座位（顺时针）/ Seat (clockwise)", seats, index=idx)
        if seat != me.get("seat"):
            if seat in occ:
                st.error("该座位已占用 / Seat taken.")
            else:
                me["seat"] = seat
    with c3:
        me["ready"] = st.toggle("准备 / Ready", value=me.get("ready", False))

    st.subheader("玩家 / Players")
    players_sorted = sorted(room["players"].values(), key=lambda p: (p["seat"] is None, p["seat"]))
    cols = st.columns(3)
    for i, p in enumerate(players_sorted):
        with cols[i % 3]:
            st.write(f"**{p['name']}** | 座位 Seat: {p['seat']} | {'✅Ready' if p['ready'] else '⬜Not ready'}")
            if is_host and p["player_key"] != room["host_key"]:
                if st.button(f"踢出 Kick: {p['name']}", key=f"kick_{p['player_key']}"):
                    del room["players"][p["player_key"]]
                    st.toast(f"已踢出 / Kicked: {p['name']}")

    # 房主控制（语言在创建时已锁定，这里仅展示）
    if is_host:
        st.markdown("---")
        st.subheader("房主控制 / Host controls")
        room["max_players"] = st.slider("人数上限 Max", 3, 6, room["max_players"])
        st.info(f"当前语言 / Room language: {'中文' if room['lang']=='zh' else 'English'}（开局后不可更改 / locked after start）")

        all_ready = (len(room["players"]) >= 2) and all(p["ready"] and p["seat"] is not None for p in room["players"].values())
        st.write(f"人数 Players: {len(room['players'])} / {room['max_players']} ；已就位 Seated: "
                 f"{sum(p['seat'] is not None for p in room['players'].values())}")

        if st.button("开始游戏 / Start", disabled=not all_ready):
            order = player_order(room)
            n = len(order)
            room["roles"] = build_roles(n)      # 生成 n+1 角色（含中英标签）
            room["deck"] = build_deck(room)     # 真实牌堆（含规则牌）
            room["turn_idx"] = 0
            for p in room["players"].values():
                p["pile"], p["captured"] = [], []
            room["active_rule"] = None
            room["duel"] = None
            room["duel_timer"] = None
            room["initial_dealt"] = False
            room["stage"] = "playing"
            st.success("游戏开始 / Game started")
            st.rerun()

# ---------- 游戏阶段 ----------
def view_game(room_id: str):
    room = ROOMS()[room_id]
    order = player_order(room)
    if len(order) < 2:
        st.warning("人数不足 / Not enough players.")
        return

    # 首轮每人发一张（规则牌翻到则置中，不给该玩家）
    if not room["initial_dealt"]:
        for k in order:
            if not room["deck"]:
                break
            c = room["deck"].pop()
            if c["type"] == "RULE":
                room["active_rule"] = c
            else:
                room["players"][k]["pile"].append(c)
        room["initial_dealt"] = True
        pair = find_any_duel(room)
        if pair:
            start_duel(room, *pair)

    # 顶部信息
    st.header(f"🎮 对局中 / Playing · 房间 {room_id}")
    left, mid, right = st.columns([2, 2, 2])
    with left:
        st.info(f"语言 / Lang: {'中文' if room['lang']=='zh' else 'English'}（已锁定 / locked）")
    with mid:
        st.metric("剩余牌数 / Cards left", len(room["deck"]))
    with right:
        if room["active_rule"]:
            st.warning(f"当前规则 / Active rule: {active_rule_text(room)}")
        else:
            st.caption("当前规则 / Active rule: 无 / None")

    if room["duel"]:
        remain = duel_countdown_left(room)
        if remain > 0:
            st.error(f"⚔️ 决斗中！请在 {remain}s 内结算 / Duel! Settle within {remain}s")
        else:
            st.error("⚔️ 决斗待结算（倒计时结束）/ Duel pending (timer ended)")

    st.markdown("---")

    # 回合玩家
    turn_key = order[room["turn_idx"]] if room["turn_idx"] < len(order) else order[0]

    # 布局
    cols = st.columns(min(6, len(order)))
    k2c = {order[i]: cols[i % len(cols)] for i in range(len(order))}

    # 行为
    def draw_one(k: str):
        if not room["deck"]:
            st.toast("牌堆用尽 / Deck empty.")
            room["stage"] = "finished"
            return
        card = room["deck"].pop()
        if card["type"] == "RULE":
            room["active_rule"] = card  # 中心唯一规则牌
            # 翻到规则牌后也检查一次是否触发对决
            pair = find_any_duel(room)
            if pair:
                start_duel(room, *pair)
            else:
                room["turn_idx"] = (room["turn_idx"] + 1) % len(order)
            return

        # 普通牌：发到自己
        room["players"][k]["pile"].append(card)
        # 立即检查是否触发对决
        pair = find_any_duel(room)
        if pair:
            start_duel(room, *pair)
        else:
            room["turn_idx"] = (room["turn_idx"] + 1) % len(order)

    def settle_by_loser(loser_key: str):
        duel = room["duel"]
        if not duel:
            return
        if loser_key not in (duel["a"], duel["b"]):
            st.toast("该玩家不在当前决斗中 / Not part of the duel.")
            return
        winner_key = duel["b"] if loser_key == duel["a"] else duel["a"]

        # 奖池 + 失败者顶牌
        buffer_cards = list(duel["buffer"])
        loser_pile = room["players"][loser_key]["pile"]
        if loser_pile:
            buffer_cards.append(loser_pile[-1])

        # 胜者收入、失败者顶牌移除
        room["players"][winner_key]["captured"].extend(buffer_cards)
        if loser_pile:
            loser_pile.pop()

        room["duel"] = None
        stop_duel_timer(room)
        # 从胜者下家继续
        room["turn_idx"] = (player_order(room).index(winner_key) + 1) % len(order)

    def tie_flip_one_each():
        duel = room["duel"]
        if not duel:
            return
        for k in (duel["a"], duel["b"]):
            if not room["deck"]:
                continue
            c = room["deck"].pop()
            if c["type"] == "RULE":
                room["active_rule"] = c  # 规则牌不入buffer
                continue
            room["players"][k]["pile"].append(c)
            duel["buffer"].append(c)

    # 渲染每位玩家
    for k in order:
        p = room["players"][k]
        with k2c[k]:
            turn_mark = "🟢" if (k == turn_key and room["duel"] is None) else ""
            st.markdown(f"### {p['name']} {turn_mark}")
            tc = top_card(room, k)
            if tc:
                # 顶牌：类别随房间语言显示，角色随语言映射显示
                cat_text = tc["category_cn"] if room["lang"] == "zh" else tc["category_en"]
                role_text = role_label(room, tc["role_key"])
                st.success(f"顶牌 / Top: {cat_text} ｜ {role_text}")
            else:
                st.warning("顶牌：无 / No top card")

            st.caption(f"叠 / Pile: {len(p['pile'])}  |  计分 / Score: {len(p['captured'])}")

            # 只有当轮、非对决、且本机 ID 为该玩家时可点
            can_draw = (k == turn_key) and (room["duel"] is None) and (st.session_state.player_key == k) and (len(room["deck"]) > 0)
            if st.button("下一张 / Next card", disabled=not can_draw, key=f"next_{k}"):
                draw_one(k)
                st.rerun()

            # 决斗中：对参与者展示“我输了”
            if room["duel"] and k in (room["duel"]["a"], room["duel"]["b"]):
                if st.button("⚔️ 我输了（点我结算）/ I Lost", key=f"lose_{k}"):
                    settle_by_loser(k)
                    st.rerun()

    # 中央：额外决斗 & 倒计时
    if room["duel"]:
        st.markdown("---")
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("🃏 额外决斗：双方各翻一张 / Extra duel: each flips one"):
                tie_flip_one_each()
                st.rerun()
        with c2:
            remain = duel_countdown_left(room)
            st.info(f"倒计时 / Countdown: {remain}s")
            if remain == 0:
                st.caption("计时结束仍需点击失败者结算 / Timer ended, still need loser click to settle.")

    # 结束
    if room["stage"] == "finished" or (len(room["deck"]) == 0 and not room["duel"]):
        st.markdown("---")
        st.subheader("🏁 游戏结束 / Game Over")
        ranking = sorted(room["players"].values(), key=lambda x: len(x["captured"]), reverse=True)
        for i, pl in enumerate(ranking, 1):
            st.write(f"{i}. {pl['name']} —— 分数 Score: {len(pl['captured'])}")
        if st.button("返回大厅 / Back to lobby"):
            room["stage"] = "lobby"
            st.rerun()

# ---------- 路由 ----------
def main():
    room_id = st.session_state.my_room
    if not room_id:
        view_lobby()
        return
    room = ROOMS().get(room_id)
    if not room or st.session_state.player_key not in room["players"]:
        st.session_state.my_room = None
        st.rerun()
        return
    if room["stage"] == "lobby":
        view_room(room_id)
    elif room["stage"] in ("playing", "finished"):
        view_game(room_id)

if __name__ == "__main__":
    main()

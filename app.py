# app.py
# 字字转机 · 线下桌游裁判/卡牌集成器（多人ID可重进、自动刷新、单按钮轮次、3秒可中断、点击失败者自动结算）
import time
import random
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Tuple, Dict
import pandas as pd
import streamlit as st

# -------------------- 页面设置 & 全局缓存 --------------------
st.set_page_config(page_title="字字转机｜多人房间", page_icon="👾", layout="wide")

@st.cache_resource
def ROOMS() -> Dict[str, dict]:
    return {}

@st.cache_resource
def load_categories() -> List[dict]:
    # 读取 data/categories.csv（两列：category,en）
    try:
        df = pd.read_csv("data/categories.csv")
        df = df.dropna()
        df = df.iloc[:10000]  # 安全限制
        return df.to_dict("records")
    except Exception as e:
        # 兜底：少量内置名词，便于第一次试跑
        base = [
            {"category":"水果","en":"fruit"},
            {"category":"交通工具","en":"transport"},
            {"category":"动物","en":"animal"},
            {"category":"饮料","en":"drink"},
            {"category":"乐器","en":"instrument"},
            {"category":"运动","en":"sport"},
        ]
        return base

CATEGORIES = load_categories()

# -------------------- 数据结构 --------------------
Role = str  # 角色自由文本
CardType = Literal["CATEGORY", "RULE"]

@dataclass
class CategoryCard:
    type: CardType
    role: Role
    category_cn: str
    category_en: str

@dataclass
class RuleCard:
    type: CardType
    rule_name: str
    payload: Optional[Tuple[str, Optional[Tuple[Role, Role]]]] = None
    # 例：("SAME_ROLE", None) 仅同角色决斗（默认）
    # 或：("PAIR_FORCE", ("孙行者","者行孙")) 指定不同角色也触发

@dataclass
class PlayerState:
    player_key: str
    name: str
    seat: Optional[int] = None
    ready: bool = False
    pile: List[CategoryCard] = field(default_factory=list)
    score_cards: List[CategoryCard] = field(default_factory=list)
    score_grab: int = 0  # 抢牌加分

# -------------------- 工具函数 --------------------
def build_roles(num_players: int) -> List[Role]:
    """n人对局，生成 n+1 种“孙行者”变体角色"""
    base = "孙行者"
    roles = [base]
    # 简单轮转变形：者行孙、行者孙、…
    for i in range(1, num_players+1):
        r = base[-i:] + base[:-i]
        roles.append(r)
    # 去重，保证 n+1 个
    uniq = []
    for r in roles:
        if r not in uniq:
            uniq.append(r)
    return uniq[:num_players+1]

def random_category() -> Tuple[str, str]:
    c = random.choice(CATEGORIES)
    return c["category"], c["en"]

def should_duel(a: Optional[CategoryCard], b: Optional[CategoryCard], active_rule: RuleCard) -> bool:
    if not a or not b: return False
    tag, pair = active_rule.payload if active_rule.payload else ("SAME_ROLE", None)
    if tag == "SAME_ROLE":
        return a.role == b.role
    if tag == "PAIR_FORCE" and pair:
        same = (a.role == b.role)
        forced = set(pair) == set([a.role, b.role])
        return same or forced
    return a.role == b.role

def gen_rule_cards(roles: List[Role]) -> List[RuleCard]:
    rules = [RuleCard(type="RULE", rule_name="仅同角色对决", payload=("SAME_ROLE", None))]
    # 随机制造两对“强制对决”组合
    if len(roles) >= 3:
        pairs = set()
        tries = 0
        while len(pairs) < 2 and tries < 20:
            a, b = random.sample(roles, 2)
            if a != b:
                pairs.add(tuple(sorted((a, b))))
            tries += 1
        for a, b in pairs:
            rules.append(RuleCard(type="RULE", rule_name=f"{a} & {b} 也必须对决", payload=("PAIR_FORCE", (a, b))))
    return rules

def build_deck(num_players: int, roles: List[Role]) -> List[dict]:
    """牌堆规模 24×n；每张普通牌 = 随机role + 随机category；混入规则牌（中心唯一）。"""
    N = 24 * num_players
    deck: List[dict] = []
    for _ in range(N):
        r = random.choice(roles)
        cn, en = random_category()
        deck.append(CategoryCard(type="CATEGORY", role=r, category_cn=cn, category_en=en).__dict__)
    # 混入规则牌
    for rc in gen_rule_cards(roles):
        deck.append(rc.__dict__)
    random.shuffle(deck)
    return deck

def player_order(room) -> List[str]:
    seated = [(p["seat"], k) for k, p in room["players"].items() if p["seat"] is not None]
    seated.sort(key=lambda x: x[0])
    return [k for _, k in seated]

def top_card(room, key: str) -> Optional[CategoryCard]:
    p = room["players"][key]
    return CategoryCard(**p["pile"][-1]) if p["pile"] else None

def set_countdown(room, seconds: int, reason: str):
    room["countdown"] = {"ends_at": time.time() + seconds, "reason": reason, "no_duel_pressed": False}

def in_countdown(room) -> bool:
    cd = room.get("countdown")
    return bool(cd and cd["ends_at"] > time.time())

def cancel_countdown(room):
    room["countdown"] = None

def any_duel_on_board(room) -> Optional[Tuple[str, str]]:
    """检查场上是否存在触发对决的一对；返回(甲,乙)任意一对玩家key"""
    order = player_order(room)
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = order[i], order[j]
            if should_duel(top_card(room, a), top_card(room, b), RuleCard(**room["active_rule"])):
                return a, b
    return None

# -------------------- 本地会话状态 --------------------
if "player_key" not in st.session_state:
    st.session_state.player_key = ""     # 你定义的“独一无二ID”
if "my_room" not in st.session_state:
    st.session_state.my_room = None      # 当前加入的房间ID

# 自动刷新（1秒）
st_autorefresh = st.experimental_rerun  # 兼容写法
st.experimental_set_query_params(ts=int(time.time()))  # 防缓存
st_autorefresh = st.autorefresh if hasattr(st, "autorefresh") else None
if st_autorefresh:
    st_autorefresh(interval=1000, key="tick")

# -------------------- 视图：大厅 --------------------
def view_lobby():
    st.header("👾 字字转机 · 房间大厅")
    tabs = st.tabs(["创建房间（房主）", "加入房间（成员）"])

    with tabs[0]:
        st.subheader("创建房间")
        room_id = st.text_input("房间号（尽量简单如 1234）", value=str(random.randint(1000, 9999)))
        player_key = st.text_input("我的独一无二ID（用于掉线重进）", placeholder="如：mc_001")
        my_name = st.text_input("我的昵称", value="玩家A")
        max_players = st.slider("最大人数上限", 3, 6, 4)
        if st.button("创建房间"):
            if not player_key:
                st.error("请填写独一无二的ID。")
                return
            if room_id in ROOMS():
                st.error("房间号已存在。")
                return
            # 初始化房间
            roles = build_roles(max_players)
            ROOMS()[room_id] = {
                "room_id": room_id,
                "host_key": player_key,
                "max_players": max_players,
                "roles": roles,        # n+1 角色
                "players": {player_key: PlayerState(player_key=player_key, name=my_name).__dict__},
                "stage": "lobby",      # lobby / playing
                "deck": [],
                "active_rule": RuleCard(type="RULE", rule_name="仅同角色对决", payload=("SAME_ROLE", None)).__dict__,
                "turn_idx": 0,
                "duel": None,          # {"a":key,"b":key,"buffer":[cards...]}
                "countdown": None,     # {"ends_at":ts,"reason":str,"no_duel_pressed":bool}
            }
            st.session_state.player_key = player_key
            st.session_state.my_room = room_id
            st.success(f"已创建房间 {room_id}，你是房主。")
            st.rerun()

    with tabs[1]:
        st.subheader("加入房间")
        room_id = st.text_input("输入房间号")
        player_key = st.text_input("我的独一无二ID（用于掉线重进）", placeholder="如：mc_002")
        my_name = st.text_input("我的昵称", value="玩家B")
        if st.button("加入房间"):
            if room_id not in ROOMS():
                st.error("房间不存在。")
                return
            room = ROOMS()[room_id]
            # 如果该ID曾加入过，直接接管；否则新增玩家（不重复）
            if player_key in room["players"]:
                room["players"][player_key]["name"] = my_name
            else:
                if len(room["players"]) >= room["max_players"]:
                    st.error("房间已满。")
                    return
                room["players"][player_key] = PlayerState(player_key=player_key, name=my_name).__dict__
            st.session_state.player_key = player_key
            st.session_state.my_room = room_id
            st.success(f"已加入房间 {room_id}")
            st.rerun()

    st.caption("说明：每位玩家进入房间时必须填写**独一无二的ID**。掉线/退出后，用同一个ID重进即可接管原座位与积分，不会重复增加玩家。")

# -------------------- 视图：准备阶段 --------------------
def view_room(room_id: str):
    room = ROOMS().get(room_id)
    if not room:
        st.warning("房间不存在或已关闭。")
        st.session_state.my_room = None
        return

    me = room["players"].get(st.session_state.player_key)
    is_host = (st.session_state.player_key == room["host_key"])
    st.header(f"🛖 房间 {room_id}（上限 {room['max_players']} 人）")

    # 自己设置
    c1, c2, c3 = st.columns([2,2,2])
    with c1:
        new = st.text_input("我的昵称", value=me["name"])
        if new != me["name"]:
            me["name"] = new
    with c2:
        seats = list(range(room["max_players"]))
        occ = {p["seat"] for k, p in room["players"].items() if k != st.session_state.player_key}
        default_idx = me["seat"] if me["seat"] in seats else 0
        seat = st.selectbox("选择座位（顺时针）", seats, index=default_idx)
        if seat != me.get("seat"):
            if seat in occ:
                st.error("该座位已被占用。")
            else:
                me["seat"] = seat
    with c3:
        me["ready"] = st.toggle("准备 / Ready", value=me.get("ready", False))

    # 玩家列表
    st.subheader("玩家列表")
    order_view = sorted(room["players"].values(), key=lambda p: (p["seat"] is None, p["seat"]))
    cols = st.columns(3)
    for i, p in enumerate(order_view):
        with cols[i % 3]:
            st.markdown(f"**{p['name']}** | 座位：{p['seat']} | {'✅已准备' if p['ready'] else '⬜未准备'}")
            if is_host and p["player_key"] != room["host_key"]:
                if st.button(f"踢出：{p['name']}", key=f"kick_{p['player_key']}"):
                    del room["players"][p["player_key"]]
                    st.toast(f"已踢出 {p['name']}")

    # 房主操作
    if is_host and room["stage"] == "lobby":
        st.markdown("---")
        st.subheader("房主控制")
        room["max_players"] = st.slider("调整房间上限", 3, 6, room["max_players"])
        all_ready = (len(room["players"]) >= 2) and all(p["ready"] and p["seat"] is not None for p in room["players"].values())
        st.write(f"当前人数：{len(room['players'])} / {room['max_players']} ； 已就位：{sum(p['seat'] is not None for p in room['players'].values())}")
        if st.button("开始游戏", disabled=not all_ready):
            order = player_order(room)
            n = len(order)
            room["roles"] = build_roles(n)
            room["deck"] = build_deck(n, room["roles"])
            room["active_rule"] = RuleCard(type="RULE", rule_name="仅同角色对决", payload=("SAME_ROLE", None)).__dict__
            room["turn_idx"] = 0
            for p in room["players"].values():
                p["pile"], p["score_cards"], p["score_grab"] = [], [], 0
            room["duel"] = None
            room["stage"] = "playing"
            st.success("游戏开始！")
            st.rerun()

# -------------------- 视图：游戏阶段 --------------------
def view_game(room_id: str):
    room = ROOMS()[room_id]
    me = room["players"][st.session_state.player_key]
    order = player_order(room)
    if len(order) < 2:
        st.warning("人数不足。")
        return

    st.header(f"🎮 对局中 · 房间 {room_id}")

    # 顶部信息
    left, mid, right = st.columns([2,2,2])
    with left:
        st.info(f"当前规则：**{room['active_rule']['rule_name']}**")
    with mid:
        st.metric("剩余牌数", len(room["deck"]))
    with right:
        cd = room.get("countdown")
        if cd and cd["ends_at"] > time.time():
            remain = max(0, int(cd["ends_at"] - time.time()))
            st.warning(f"⏱️ 倒计时 {remain}s（{cd['reason']}）")
            # “无决斗”按钮：提前结束倒计时；若实际存在对决，给出提示
            no_duel = st.button("🙅 无决斗（提前结束倒计时）")
            if no_duel:
                room["countdown"]["no_duel_pressed"] = True
                duel_pair = any_duel_on_board(room)
                cancel_countdown(room)
                if duel_pair:
                    st.error("其实存在【需要决斗】的一对玩家！")
        else:
            room["countdown"] = None

    st.markdown("---")

    # 当前回合归属
    turn_key = order[room["turn_idx"]] if room["turn_idx"] < len(order) else order[0]
    my_turn = (turn_key == st.session_state.player_key) and (room["duel"] is None)

    # 玩家圈布局
    cols = st.columns(min(6, len(order)))
    k2col = {}
    for i, k in enumerate(order):
        k2col[k] = cols[i % len(cols)]

    def draw_one(k: str):
        if not room["deck"]:
            st.toast("牌堆用尽。")
            return
        card = room["deck"].pop()
        if card["type"] == "RULE":
            room["active_rule"] = card
            set_countdown(room, 3, "翻到规则牌")
        else:
            room["players"][k]["pile"].append(card)
            set_countdown(room, 3, "翻出普通牌")
        # 翻普通牌后，检查是否出现任意对决
        if card["type"] == "CATEGORY":
            pair = any_duel_on_board(room)
            if pair:
                a, b = pair
                room["duel"] = {"a": a, "b": b, "buffer": []}
                # 将双方当前顶牌加入奖池
                ta, tb = top_card(room, a), top_card(room, b)
                if ta: room["duel"]["buffer"].append(ta.__dict__)
                if tb: room["duel"]["buffer"].append(tb.__dict__)
        # 未进入对决才轮转
        if room["duel"] is None:
            room["turn_idx"] = (room["turn_idx"] + 1) % len(order)

    def settle_by_loser(loser_key: str):
        """点击失败者的牌堆 → 自动找到对手为胜者并结算"""
        duel = room["duel"]
        if not duel: return
        if loser_key not in (duel["a"], duel["b"]):
            st.toast("当前并非该玩家参与的对决。")
            return
        winner_key = duel["b"] if loser_key == duel["a"] else duel["a"]
        buffer_cards = duel["buffer"][:]
        # 把双方叠顶加入奖池并清空叠
        for k in (duel["a"], duel["b"]):
            buffer_cards.extend(room["players"][k]["pile"])
            room["players"][k]["pile"].clear()
        # 计分给胜者
        room["players"][winner_key]["score_cards"].extend(buffer_cards)
        room["duel"] = None
        set_countdown(room, 3, "对决结束")

    def tie_flip_one():
        """点击中心牌堆 → 平手各翻一张并加入奖池"""
        duel = room["duel"]
        if not duel: return
        for k in (duel["a"], duel["b"]):
            while True:
                if not room["deck"]: break
                c = room["deck"].pop()
                if c["type"] == "RULE":
                    room["active_rule"] = c
                    continue
                else:
                    room["players"][k]["pile"].append(c)
                    duel["buffer"].append(c)
                    break
        set_countdown(room, 3, "平手各翻一张")

    # 侧栏：抢牌（倒计时内可中断）
    st.sidebar.header("⏱️ 抢牌（3 秒内任意人可操作）")
    if in_countdown(room):
        target_name = st.sidebar.selectbox("被抢者", [room["players"][k]["name"] for k in order], key="grab_t")
        winner_name = st.sidebar.selectbox("抢到者", [room["players"][k]["name"] for k in order], key="grab_w")
        name2key = {room["players"][k]["name"]: k for k in order}
        if st.sidebar.button("🎯 抢牌"):
            tkey, wkey = name2key[target_name], name2key[winner_name]
            pile = room["players"][tkey]["pile"]
            if pile:
                pile.pop()  # 只拿走顶牌（不进分牌区，只+1 抢牌分）
                room["players"][wkey]["score_grab"] += 1
                cancel_countdown(room)
                st.toast(f"{winner_name} 抢走 {target_name} 顶牌，+1 抢牌分")
            else:
                st.toast("该玩家没有可抢的顶牌。")
    else:
        st.sidebar.info("当前无倒计时，不能抢牌。")

    # 渲染每位玩家格子
    for k in order:
        p = room["players"][k]
        with k2col[k]:
            turn_mark = "🟢" if (k == turn_key and room["duel"] is None) else ""
            st.markdown(f"### {p['name']} {turn_mark}")
            tc = top_card(room, k)
            if tc:
                st.success(f"顶牌：{tc.role}｜{tc.category_cn} ({tc.category_en})")
            else:
                st.warning("顶牌：无")
            st.caption(f"叠：{len(p['pile'])}  |  计分牌：{len(p['score_cards'])}  | 抢牌分：{p['score_grab']}")

            # 仅当前回合所属ID设备可按
            if st.button("下一张", disabled=not (k == turn_key and room["duel"] is None and st.session_state.player_key == k), key=f"next_{k}"):
                draw_one(k)
                st.rerun()

            # 决斗结算：点击失败者的牌堆（仅在他参与对决时可点）
            if room["duel"] and k in (room["duel"]["a"], room["duel"]["b"]):
                if st.button("⚔️ 我输了（点我结算）", key=f"lose_{k}"):
                    settle_by_loser(k)
                    st.rerun()

    # 中心“平手各翻一张”
    if room["duel"]:
        st.markdown("---")
        if st.button("🃏 中间牌堆：平手各翻一张（追加）"):
            tie_flip_one()
            st.rerun()

# -------------------- 路由 --------------------
def main():
    room_id = st.session_state.my_room
    if not room_id:
        view_lobby()
        return
    room = ROOMS().get(room_id)
    if not room or st.session_state.player_key not in room["players"]:
        # 房间不存在或ID未注册 → 回大厅
        st.session_state.my_room = None
        st.rerun()
        return
    if room["stage"] == "lobby":
        view_room(room_id)
    else:
        view_game(room_id)

if __name__ == "__main__":
    main()

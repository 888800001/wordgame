
import streamlit as st
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Tuple

# ========== 数据结构 ==========
Alien = Literal["狼","兔","猫","牛"]
CardType = Literal["CATEGORY","RULE"]

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
    # 规则：("PAIR_FORCE_DUEL", ("狼","兔")) 表示狼&兔也必须对决
    # 或 ("SAME_ALIEN_ONLY", None) 表示仅同外星人才触发（默认）
    payload: Optional[Tuple[str, Optional[Tuple[Alien, Alien]]]] = None

@dataclass
class PlayerState:
    name: str
    pile: List[CategoryCard] = field(default_factory=list)   # 桌面面朝上的叠（只显示顶牌）
    score_cards: List[CategoryCard] = field(default_factory=list)  # 赢到的计分牌（面朝下计数即可）

# ========== 生成卡组（示例少量，便于演示；后续可从 CSV 加载） ==========
ALIENS: List[Alien] = ["狼","兔","猫","牛"]

CATEGORY_POOL = [
    ("水果","Fruit"),
    ("交通工具","Transport"),
    ("童话人物","Fairy Tale Character"),
    ("垃圾食品","Junk Food"),
    ("动物","Animal"),
    ("乐器","Instrument"),
]

def build_deck() -> List:
    deck: List = []
    # 普通分类牌：每个外星人 * 若干分类
    for alien in ALIENS:
        for cn, en in CATEGORY_POOL:
            deck.append(CategoryCard(type="CATEGORY", alien=alien, category_cn=cn, category_en=en))

    # 规则牌示例（可继续扩展）
    rule_cards: List[RuleCard] = [
        RuleCard(type="RULE", rule_name="仅同外星人对决", payload=("SAME_ALIEN_ONLY", None)),
        RuleCard(type="RULE", rule_name="狼&兔也必须对决", payload=("PAIR_FORCE_DUEL", ("狼","兔"))),
        RuleCard(type="RULE", rule_name="猫&牛也必须对决", payload=("PAIR_FORCE_DUEL", ("猫","牛"))),
    ]
    deck.extend(rule_cards)

    random.shuffle(deck)
    return deck

# ========== 规则判定 ==========
def should_duel(top_a: Optional[CategoryCard], top_b: Optional[CategoryCard], active_rule: RuleCard) -> bool:
    if not top_a or not top_b:
        return False
    rule_tag, pair = active_rule.payload if active_rule.payload else ("SAME_ALIEN_ONLY", None)
    if rule_tag == "SAME_ALIEN_ONLY":
        return top_a.alien == top_b.alien
    if rule_tag == "PAIR_FORCE_DUEL" and pair:
        # 同外星人 or 指定不同外星人也对决
        same = (top_a.alien == top_b.alien)
        forced = set(pair) == set([top_a.alien, top_b.alien])
        return same or forced
    # 兜底：按同外星人
    return top_a.alien == top_b.alien

# ========== Streamlit 页面 ==========
st.set_page_config(page_title="线下裁判面板｜字字转机", page_icon="👾", layout="centered")
st.title("👾 字字转机｜线下裁判面板 Demo（2人版）")

# ------ 初始化状态 ------
if "deck" not in st.session_state:
    st.session_state.deck: List = build_deck()
if "players" not in st.session_state:
    st.session_state.players = [PlayerState(name="左边"), PlayerState(name="右边")]
if "turn_idx" not in st.session_state:
    st.session_state.turn_idx = 0  # 0 -> 左；1 -> 右
if "active_rule" not in st.session_state:
    # 默认规则：仅同外星人对决
    st.session_state.active_rule = RuleCard(type="RULE", rule_name="仅同外星人对决", payload=("SAME_ALIEN_ONLY", None))
if "duel_buffer" not in st.session_state:
    # 平手时把双方为这次对决翻开的牌暂存于此（最终胜者全拿走）
    st.session_state.duel_buffer: List[CategoryCard] = []
if "in_duel" not in st.session_state:
    st.session_state.in_duel = False  # 当前是否处于对决流程（可能有连锁平手）
if "last_flip_players" not in st.session_state:
    st.session_state.last_flip_players = set()  # 最近一次翻牌涉及的玩家（用于平手时限定再翻）

# ------ 辅助函数 ------
def draw_one(player_idx: int):
    """给某玩家翻一张牌：若是规则牌→更新当前规则；若是分类牌→压到该玩家面前叠顶。"""
    if not st.session_state.deck:
        st.info("牌堆用尽。可点击上方‘重新开始’。")
        return
    card = st.session_state.deck.pop()
    if isinstance(card, RuleCard):
        st.session_state.active_rule = card
        st.toast(f"🧩 规则更新：{card.rule_name}", icon="✨")
    else:
        st.session_state.players[player_idx].pile.append(card)

def top_card(player_idx: int) -> Optional[CategoryCard]:
    pile = st.session_state.players[player_idx].pile
    return pile[-1] if pile else None

def start_check_duel():
    """检查是否触发对决。"""
    left = top_card(0)
    right = top_card(1)
    if should_duel(left, right, st.session_state.active_rule):
        st.session_state.in_duel = True
        st.session_state.duel_buffer = []  # 清空
        st.session_state.last_flip_players = {0,1}
        # 把当前两张顶牌先放入对决奖池（duel_buffer）
        if left: st.session_state.duel_buffer.append(left)
        if right: st.session_state.duel_buffer.append(right)

def settle_duel_winner(winner_idx: int):
    """对决分出胜负：胜者将“本轮对决涉及的所有牌”收归计分，并把双方参与对决的面牌叠清空。"""
    winner = st.session_state.players[winner_idx]
    # 将 buffer 全部收入胜者计分区
    for c in st.session_state.duel_buffer:
        winner.score_cards.append(c)
    # 清空参与者各自当前这一叠的牌（只清两位对决者）
    for idx in [0,1]:
        st.session_state.players[idx].pile.clear()
    # 清标志
    st.session_state.in_duel = False
    st.session_state.duel_buffer = []
    st.session_state.last_flip_players = set()
    st.toast(f"🏆 {winner.name} 获胜！本次对决累计计分牌：{len(winner.score_cards)}", icon="🏆")

def tie_flip_next():
    """平手：双方各再翻一张（3 秒后自动翻开为可见状态），继续比较；直到产生胜者。"""
    # 平手只允许对决双方再翻
    for idx in [0,1]:
        # 连续翻一张（可能翻到规则牌 → 立即生效；再继续翻到分类牌）
        while True:
            if not st.session_state.deck:
                break
            card = st.session_state.deck.pop()
            if isinstance(card, RuleCard):
                st.session_state.active_rule = card
                st.toast(f"🧩 平手期间规则更新：{card.rule_name}", icon="✨")
                # 继续翻，直到翻到分类牌
                continue
            else:
                st.session_state.players[idx].pile.append(card)
                # 加入对决奖池
                st.session_state.duel_buffer.append(card)
                break

    # 模拟 3 秒等待（线下“同时说出”时的节奏）
    with st.spinner("平手 → 双方各再翻一张…（3秒）"):
        time.sleep(3)

def reset_all():
    st.session_state.deck = build_deck()
    for p in st.session_state.players:
        p.pile.clear()
        p.score_cards.clear()
    st.session_state.turn_idx = 0
    st.session_state.active_rule = RuleCard(type="RULE", rule_name="仅同外星人对决", payload=("SAME_ALIEN_ONLY", None))
    st.session_state.duel_buffer = []
    st.session_state.in_duel = False
    st.session_state.last_flip_players = set()
    st.toast("已重置新一局。", icon="🔄")

# ------ 顶部控制栏 ------
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("🔄 重新开始"):
        reset_all()
with c2:
    st.write("")
with c3:
    st.metric("剩余牌数", len(st.session_state.deck))

st.markdown("---")

# 当前规则显示
st.subheader("当前规则")
st.info(f"🧩 {st.session_state.active_rule.rule_name}")

# 玩家区
left_col, right_col = st.columns(2)

for idx, col in enumerate([left_col, right_col]):
    p = st.session_state.players[idx]
    with col:
        st.markdown(f"### {p.name}")
        # 显示叠顶
        top = top_card(idx)
        if top:
            st.success(f"顶牌：{top.alien}｜{top.category_cn} ({top.category_en})")
        else:
            st.warning("顶牌：无")

        # 翻牌按钮（非对决状态下才可翻；对决中用下面的三按钮判定）
        disabled = st.session_state.in_duel
        if st.button("翻我下一张", disabled=disabled, key=f"flip_{idx}"):
            draw_one(idx)
            # 新翻牌后，检查是否触发对决
            start_check_duel()
            # 轮转回合（非对决才轮转）
            if not st.session_state.in_duel:
                st.session_state.turn_idx = 1 - st.session_state.turn_idx

        st.caption(f"计分牌：{len(p.score_cards)} 张")

st.markdown("---")

# 对决面板：当触发对决时出现三按钮
if st.session_state.in_duel:
    st.subheader("⚔️ 对决进行中")
    lc = top_card(0)
    rc = top_card(1)
    st.write(
        f"左顶牌：{lc.alien if lc else '无'}｜{lc.category_cn if lc else ''}  "
        f" vs  右顶牌：{rc.alien if rc else '无'}｜{rc.category_cn if rc else ''}"
    )

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("✅ 左方胜"):
            settle_duel_winner(0)
    with b2:
        if st.button("✅ 右方胜"):
            settle_duel_winner(1)
    with b3:
        if st.button("🤝 同时说出（平手）→ 各翻一张"):
            tie_flip_next()

# 底部提示
st.markdown("---")
st.caption("玩法说明：轮流翻牌；当满足规则触发对决时，裁判只需点“左胜/右胜/同时说出”。平手会各自再翻一张并在 3 秒后展示，直到有人赢下本次对决并拿走本轮所有参与对决的牌计分。")

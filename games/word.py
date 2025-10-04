
import time, random
from dataclasses import dataclass
from typing import List, Tuple, Optional
import pandas as pd
import streamlit as st

@st.cache_data
def load_categories():
    df = pd.read_csv("data/categories.csv").dropna()
    return df.to_dict("records")

CATS = load_categories()

@dataclass
class Card:
    type: str                # "CATEGORY" | "RULE"
    role_key: Optional[str]  # 分类牌才有
    cn: Optional[str]
    en: Optional[str]
    pair: Optional[Tuple[str, str]] = None  # 规则牌对

def player_order(room: dict) -> List[str]:
    seated = [(p.get("seat"), k) for k, p in room["players"].items() if p.get("seat") is not None]
    seated.sort(key=lambda x: x[0])
    return [k for _, k in seated]

def role_label(room: dict, role_key: str) -> str:
    lang = room.get("game_lang") or "zh"
    roles = {r["key"]: r for r in room["game_state"].get("roles", [])}
    if role_key not in roles: return role_key
    return roles[role_key]["cn"] if lang == "zh" else roles[role_key]["en"]

def build_roles(room: dict):
    order = player_order(room); n = len(order)
    cn_pool = ["孙行者","者行孙","行者孙","牛魔王","白骨精","铁扇公主","沙和尚","猪悟能","红孩儿","金角大王","银角大王"]
    en_pool = ["Amy","Jim","Bob","Eve","Lily","Max","Zoe","Tom","Ada","Ivy","Jay"]
    roles = [{"key": f"r{i}", "cn": cn_pool[i%len(cn_pool)], "en": en_pool[i%len(en_pool)]} for i in range(n+1)]
    room["game_state"]["roles"] = roles

def random_cat()->Tuple[str,str]:
    c = random.choice(CATS); return c["category"], c["en"]

def build_deck(room: dict)->List[Card]:
    roles = [r["key"] for r in room["game_state"]["roles"]]
    n = len(player_order(room))
    deck = [Card("CATEGORY", random.choice(roles), *random_cat()) for _ in range(24*n)]
    # 规则牌
    rule_count = min(3, max(1, n-1))
    pairs=set(); tries=0
    while len(pairs)<rule_count and tries<100:
        a,b=random.sample(roles,2); pair=tuple(sorted((a,b)))
        if a!=b and pair not in pairs: pairs.add(pair)
        tries+=1
    for a,b in pairs: deck.append(Card("RULE", None, None, None, (a,b)))
    random.shuffle(deck); return deck

def top_card(room: dict, pid: str)->Optional[Card]:
    pile = room["game_state"]["piles"].get(pid, [])
    return pile[-1] if pile else None

def should_duel(room: dict, a: str, b: str)->bool:
    ac = top_card(room,a); bc = top_card(room,b)
    if not ac or not bc: return False
    same = (ac.role_key == bc.role_key)
    rule = room["game_state"].get("active_rule")
    forced = bool(rule and set([ac.role_key, bc.role_key])==set(rule.pair))
    return same or forced

def find_any_duel(room: dict):
    order = player_order(room)
    for i in range(len(order)):
        for j in range(i+1, len(order)):
            if should_duel(room, order[i], order[j]): return order[i], order[j]
    return None

def ensure_init(room: dict):
    gs = room["game_state"]
    if gs.get("_inited"): return
    gs["_inited"]=True
    gs["piles"] = {pid: [] for pid in room["players"]}
    gs["captured"] = {pid: [] for pid in room["players"]}
    gs["active_rule"]=None; gs["turn_idx"]=0
    gs["duel"]=None; gs["duel_timer"]=0; gs["initial_dealt"]=False
    build_roles(room); gs["deck"]=build_deck(room)

def push_card(room: dict, pid: str, card: Card):
    room["game_state"]["piles"][pid].append(card)

def active_rule_text(room: dict)->str:
    r = room["game_state"].get("active_rule")
    if not r: return "无"
    a,b = r.pair; return f"{role_label(room,a)} 与 {role_label(room,b)} 必须对决"

def run(room: dict, me_key: str, emit_settlement):
    ensure_init(room)
    gs = room["game_state"]; order = player_order(room)
    if len(order)<2: st.warning("人数不足（至少 2 人）。"); return

    if not gs["initial_dealt"]:
        for pid in order:
            if not gs["deck"]: break
            c = gs["deck"].pop()
            if c.type == "RULE": gs["active_rule"]=c
            else: push_card(room, pid, c)
        gs["initial_dealt"]=True
        pair = find_any_duel(room)
        if pair: gs["duel"]={"a":pair[0],"b":pair[1],"buffer":[]}; gs["duel_timer"]=time.time()+5

    left,mid,right = st.columns([2,2,2])
    with left: st.metric("剩余牌数", len(gs["deck"]))
    with mid: st.caption(f"卡面语言：{room.get('game_lang','zh')}（开局已锁定）")
    with right:
        if gs["active_rule"]: st.warning(f"规则牌：{active_rule_text(room)}")
        else: st.caption("规则牌：无")

    if gs["duel"]:
        remain=max(0,int(gs["duel_timer"]-time.time())) if gs["duel_timer"] else 0
        st.error(f"⚔️ 决斗中！请在 {remain}s 内点击失败者结算。")
    st.markdown("---")

    turn_key = order[gs["turn_idx"]] if gs["turn_idx"]<len(order) else order[0]

    def draw_one(pid: str):
        if not gs["deck"]: st.toast("牌堆用尽"); return
        card = gs["deck"].pop()
        if card.type == "RULE":
            gs["active_rule"]=card
            pair=find_any_duel(room)
            if pair: gs["duel"]={"a":pair[0],"b":pair[1],"buffer":[]}; gs["duel_timer"]=time.time()+5
            else: gs["turn_idx"]=(gs["turn_idx"]+1)%len(order)
            return
        push_card(room, pid, card)
        pair = find_any_duel(room)
        if pair: gs["duel"]={"a":pair[0],"b":pair[1],"buffer":[]}; gs["duel_timer"]=time.time()+5
        else: gs["turn_idx"]=(gs["turn_idx"]+1)%len(order)

    def settle_loser(loser: str):
        duel = gs["duel"]
        if not duel or loser not in (duel["a"], duel["b"]): st.toast("不在当前决斗中"); return
        winner = duel["b"] if loser==duel["a"] else duel["a"]
        buf=list(duel["buffer"]); lp=gs["piles"][loser]
        if lp: buf.append(lp[-1]); lp.pop()
        gs["captured"][winner].extend(buf)
        gs["duel"]=None; gs["duel_timer"]=0
        gs["turn_idx"]=(player_order(room).index(winner)+1)%len(order)

    def tie_flip():
        duel = gs["duel"]
        if not duel: return
        for pid in (duel["a"], duel["b"]):
            while gs["deck"]:
                c = gs["deck"].pop()
                if c.type == "RULE": gs["active_rule"]=c; continue
                push_card(room, pid, c); duel["buffer"].append(c); break

    cols = st.columns(min(6,len(order)))
    for i,pid in enumerate(order):
        with cols[i%len(cols)]:
            p = room["players"][pid]
            st.markdown(f"### {p['name']}{' 🟢' if (pid==turn_key and not gs['duel']) else ''}")
            top = top_card(room,pid)
            if top:
                txt = (f"{top.cn}｜{role_label(room, top.role_key)}" if (room.get('game_lang','zh')=='zh')
                       else f"{top.en} | {role_label(room, top.role_key)}")
                st.success(f"顶牌：{txt}")
            else: st.warning("顶牌：无")

            can = (pid==turn_key) and (gs["duel"] is None) and (st.session_state.player_key==pid) and (len(gs["deck"])>0)
            if st.button("下一张", disabled=not can, key=f"next_{pid}"): draw_one(pid); st.rerun()

            if gs["duel"] and pid in (gs["duel"]["a"], gs["duel"]["b"]):
                if st.button("⚔️ 我输了（点我结算）", key=f"lose_{pid}"): settle_loser(pid); st.rerun()

    if gs["duel"]:
        st.markdown("---")
        c1,c2 = st.columns(2)
        with c1:
            if st.button("🃏 双方各翻一张"): tie_flip(); st.rerun()
        with c2:
            remain=max(0,int(gs["duel_timer"]-time.time())) if gs["duel_timer"] else 0
            st.info(f"倒计时：{remain}s（到0仍需点失败者结算）")

    st.markdown("---"); st.subheader("结束并结算")
    if st.button("结束本局并结算（按赢牌数差×100）"):
        order_now = player_order(room)
        scores = {pid: len(gs["captured"][pid]) for pid in order_now}
        avg = sum(scores.values())/len(order_now) if order_now else 0.0
        unit=100
        transfers = {pid: int(round((scores[pid]-avg)*unit)) for pid in order_now}
        adjust = -sum(transfers.values())
        if order_now: transfers[order_now[0]] += adjust
        emit_settlement(transfers, note="字字转机：按赢到的牌数与平均差×100 结算")

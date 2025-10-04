import streamlit as st
import random
import time
import pandas as pd

ALIENS = ["孙行者", "猪悟能", "沙和尚", "白龙马"]
RULES = [
    ("孙行者", "猪悟能"),
    ("沙和尚", "白龙马")
]

def run_game(room_id, rooms, users):
    st.header("👾 字字转机｜学习版")
    room = rooms[room_id]
    players = list(room["players"].items())

    if "deck" not in st.session_state:
        df = pd.read_csv("data/categories.csv")
        st.session_state.deck = [
            {"category": row["category"], "en": row["en"], "alien": random.choice(ALIENS)}
            for _, row in df.iterrows()
        ]
        random.shuffle(st.session_state.deck)
        st.session_state.rule = None
        st.session_state.table = {ip: [] for ip, _ in players}

    st.subheader("当前规则")
    st.info(st.session_state.rule or "仅相同外星人决斗")

    st.divider()
    for ip, pdata in players:
        st.write(f"{pdata['name']} ({pdata['coins']}💰)")
        cards = st.session_state.table[ip]
        if cards:
            st.success(f"顶牌：{cards[-1]['alien']}｜{cards[-1]['category']}")
        else:
            st.warning("暂无牌")

    # 当前回合玩家
    turn_ip = players[st.session_state.get("turn_index", 0) % len(players)][0]
    current_name = room["players"][turn_ip]["name"]
    st.write(f"🎯 当前轮到：{current_name}")

    if st.session_state.deck:
        if st.session_state.ip == turn_ip:
            if st.button("翻我下一张牌"):
                card = st.session_state.deck.pop()
                if random.random() < 0.1:
                    st.session_state.rule = f"规则牌：{random.choice(RULES)}"
                    st.toast("🧩 新规则出现！")
                else:
                    st.session_state.table[turn_ip].append(card)
                    check_duel(st.session_state.table, room)
                st.session_state["turn_index"] += 1
                st.rerun()
        else:
            st.button("翻我下一张牌", disabled=True)
    else:
        st.info("所有牌已发完，本局结束。")

    st.divider()
    if st.button("结束本局"):
        st.session_state.deck = []
        st.success("游戏结束，返回大厅。")

def check_duel(table, room):
    top = {ip: cards[-1]["alien"] for ip, cards in table.items() if cards}
    seen = {}
    for ip, alien in top.items():
        if alien in seen:
            winner = random.choice([ip, seen[alien]])  # 简化：随机胜者
            loser = seen[alien] if winner == ip else ip
            room["players"][winner]["coins"] += 500
            room["players"][loser]["coins"] -= 500
            st.toast(f"⚔️ {room['players'][winner]['name']} 战胜了 {room['players'][loser]['name']}！")
            return
        seen[alien] = ip

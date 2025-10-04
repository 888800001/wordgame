import streamlit as st
from typing import Dict

def run(room: dict, me_key: str, emit_settlement):
    st.info('德州扑克（占位示例）。结束时用 emit_settlement(transfers) 回传零和结算。')
    players = list(room['players'].keys())
    if len(players) < 2:
        st.warning('人数不足（至少 2 人）。'); return
    c1, c2 = st.columns(2)
    with c1:
        win_id = st.selectbox('赢家ID', options=players, index=0)
        win_amt = st.number_input('赢家盈利（正数）', min_value=0, value=500, step=100)
    with c2:
        lose_id = st.selectbox('输家ID', options=[p for p in players if p != win_id], index=0)
    if st.button('提交结算（零和）'):
        transfers: Dict[str, int] = {pid: 0 for pid in players}
        transfers[win_id] += int(win_amt)
        transfers[lose_id] -= int(win_amt)
        emit_settlement(transfers, note='德扑：自定义结算示例')
        st.success('已提交结算，返回结束页查看钱包变化。')

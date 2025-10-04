import streamlit as st
from typing import Dict

def run(room: dict, me_key: str, emit_settlement):
    st.info('十点半（占位示例）。结束时 emit_settlement(transfers)。')
    players = list(room['players'].keys())
    if len(players) < 2:
        st.warning('人数不足（至少 2 人）。'); return
    st.caption('多赢家/多输家结算演示（需要零和）：')
    amounts = {pid: st.number_input(f"{room['players'][pid]['name']} 的净变化（可正可负）", value=0, step=100, key=f"amt_{pid}") for pid in players}
    if st.button('提交结算（必须零和）'):
        total = sum(amounts.values())
        if total != 0:
            st.error(f'当前和为 {total}，需要零和（和=0）才能提交。请调整输入。')
        else:
            transfers: Dict[str, int] = {pid: int(v) for pid, v in amounts.items()}
            emit_settlement(transfers, note='十点半：手动输入零和结算示例')
            st.success('已提交结算。')

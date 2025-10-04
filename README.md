# 线下多人游戏平台（Streamlit）

- 大厅：选择游戏、创建/加入 4 位数字房间，0.5s 自动刷新。
- 每房间独立货币：玩家加入房间初始 20000，子游戏零和结算写回。
- 当前包含：字字转机（可玩）、德扑（占位）、十点半（占位）。

## 本地运行
```bash
pip install -r requirements.txt
streamlit run app.py
```
## 部署
上传至 GitHub，Streamlit Cloud 选择 `app.py`。

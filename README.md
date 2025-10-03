
# 字字转机｜线下裁判面板（Streamlit Demo）

本仓库是一个 2 人线下对决的“裁判面板”原型：不处理线上抢答，只提供翻牌、判定和计分。

## 本地运行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署到 Streamlit Community Cloud
1. 把本仓库推到 GitHub（Public 仓库即可）。
2. 到 https://share.streamlit.io 登录，点击 New app，选择你的仓库与分支，`app.py` 作为入口。
3. 等待构建后，获得形如 `https://xxx.streamlit.app` 的公开网址。

## 目录结构
```
.
├─ app.py
├─ requirements.txt
├─ data/
│  └─ cards.csv
└─ .streamlit/
   └─ config.toml
```

## 说明
- `.streamlit/config.toml` 已默认关闭使用统计（telemetry）。
- `data/cards.csv` 可自行扩充卡牌池。

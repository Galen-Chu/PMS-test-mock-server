# server/__init__.py

# 從當前目錄的 mock_server 模組中，將 Flask app 實例提升到門面
from .mock_server import app

# 定義這個套件對外公開的白名單（當外部執行 from server import * 時會引入的內容）
__all__ = ['app']

# Bash command to run the server:
# gunicorn server.mock_server:app
# gunicorn server:app
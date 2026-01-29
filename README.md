# VPS1 - Telegram Bot + API Server

Chạy trên VPS1 (45.32.116.164): Bot Telegram và API Server xử lý Step 0-5.

## Cài đặt

```bash
# 1. Upload files
scp -r vps1/* user@45.32.116.164:/opt/github-bot/

# 2. Cài dependencies
cd /opt/github-bot
pip install -r requirements.txt

# 3. Cấu hình
cp .env.example .env
nano .env  # Sửa các giá trị

# 4. Tạo database
mysql -u root -p
CREATE DATABASE github_student_bot;
CREATE USER 'bot_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON github_student_bot.* TO 'bot_user'@'localhost';
FLUSH PRIVILEGES;
```

## Chạy

```bash
# Terminal 1: API Server
python api_server.py

# Terminal 2: Telegram Bot
python telegram_bot.py
```

## Sử dụng systemd (production)

```bash
# Tạo service files
sudo nano /etc/systemd/system/github-api.service
sudo nano /etc/systemd/system/github-bot.service

# Enable và start
sudo systemctl enable github-api github-bot
sudo systemctl start github-api github-bot
```

## Files

| File | Mô tả |
|------|-------|
| telegram_bot.py | Bot Telegram chính |
| api_server.py | API Server (Step 0-5) |
| models.py | Database models |
| config.py | Cấu hình |
| keyboards.py | Inline keyboards |
| states.py | FSM states |
| database.py | Database connection |

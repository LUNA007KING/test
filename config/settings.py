from dotenv import load_dotenv
import os

# 加载 .env 文件中的环境变量
load_dotenv()

# Telegram Bot API Token
BOT_API_TOKEN = os.getenv("BOT_TOKEN")

# 数据库配置
DB_CONFIG = {
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASSWORD"),
    'host': os.getenv("DB_HOST"),
    'port': os.getenv("DB_PORT"),
    'database': os.getenv("DB_NAME")
}

# 区块链API的配置
BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL")


# 其他配置...

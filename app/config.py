from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    deepseek_api_key: str
    owner_telegram_id: int
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    database_path: str = "data/assistant.db"
    max_history_messages: int = 12
    max_output_tokens: int = 400
    rate_limit_messages: int = 8
    rate_limit_window_seconds: int = 60
    human_takeover_minutes: int = 60
    global_pause_minutes: int = 60
    min_reply_delay_seconds: float = 4
    max_reply_delay_seconds: float = 6
    recent_message_limit: int = 6
    summary_trigger_new_messages: int = 8
    max_knowledge_cards: int = 4
    max_knowledge_chars: int = 3000
    max_memory_summary_chars: int = 2000
    daily_report_enabled: bool = True
    daily_report_time: str = "00:00"
    app_timezone: str = "Asia/Almaty"
    initial_reply_debounce_seconds: float = 30
    active_reply_debounce_seconds: float = 5
    conversation_idle_reset_minutes: float = 60
    log_level: str = "INFO"

def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    owner = os.getenv("OWNER_TELEGRAM_ID", "").strip()
    if not token or not key or not owner:
        raise ValueError("TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY and OWNER_TELEGRAM_ID are required")
    return Settings(token, key, int(owner), os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), os.getenv("DATABASE_PATH", "data/assistant.db"), int(os.getenv("MAX_HISTORY_MESSAGES", "12")), int(os.getenv("MAX_OUTPUT_TOKENS", "400")), int(os.getenv("RATE_LIMIT_MESSAGES", "8")), int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")), int(os.getenv("HUMAN_TAKEOVER_MINUTES", "60")), int(os.getenv("GLOBAL_PAUSE_MINUTES", "60")), float(os.getenv("MIN_REPLY_DELAY_SECONDS", "4")), float(os.getenv("MAX_REPLY_DELAY_SECONDS", "6")), int(os.getenv("RECENT_MESSAGE_LIMIT", "6")), int(os.getenv("SUMMARY_TRIGGER_NEW_MESSAGES", "8")), int(os.getenv("MAX_KNOWLEDGE_CARDS", "4")), int(os.getenv("MAX_KNOWLEDGE_CHARS", "3000")), int(os.getenv("MAX_MEMORY_SUMMARY_CHARS", "2000")), os.getenv("DAILY_REPORT_ENABLED", "true").lower()=="true", os.getenv("DAILY_REPORT_TIME", "00:00"), os.getenv("APP_TIMEZONE", "Asia/Almaty"), float(os.getenv("INITIAL_REPLY_DEBOUNCE_SECONDS", "30")), float(os.getenv("ACTIVE_REPLY_DEBOUNCE_SECONDS", "5")), float(os.getenv("CONVERSATION_IDLE_RESET_MINUTES", "60")), os.getenv("LOG_LEVEL", "INFO"))

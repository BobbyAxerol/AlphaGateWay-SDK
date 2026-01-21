import os
import json
from pydantic_settings import BaseSettings
from typing import List, Dict, Optional

class Settings(BaseSettings):
    # Core
    IS_TESTNET: bool = True
    LOG_LEVEL: str = "INFO"
    REDIS_URL: str = "redis://redis_service:6379/0"
    POSTGRES_DSN: str = "postgresql://bobby:Kaka11022002!@live_data_executor:5432/live_data_executor"

    # Binance Key Pools (Dạng JSON String từ .env)
    BINANCE_LIVE_KEYS: str = "[]"
    BINANCE_TESTNET_KEYS: str = "[]"
    
    # Listener Keys
    LISTENER_API_KEY: Optional[str] = None
    LISTENER_API_SECRET: Optional[str] = None

    # TCBS
    TCBS_USER: Optional[str] = None
    TCBS_PASSWORD: Optional[str] = None
    TCBS_2FA_SECRET: Optional[str] = None
    
    SYMBOL_CONFIG_PATH: str = "./shared/symbols.json"

    def _parse_keys(self, raw_str: str) -> List[Dict[str, str]]:
        if not raw_str or raw_str.strip() == "":
            return []
        
        raw_str = raw_str.strip()
        
        # Ưu tiên parse JSON (Dành cho định dạng mới)
        if raw_str.startswith('['):
            try:
                return json.loads(raw_str)
            except Exception as e:
                # Nếu lỗi JSON, quay về parse thủ công hoặc trả về mảng rỗng
                return []
        
        # Backup parse thủ công KEY:SECRET,KEY:SECRET (Cho tương thích ngược)
        keys = []
        for pair in raw_str.split(","):
            if ":" in pair:
                parts = pair.split(":", 1)
                keys.append({"key": parts[0], "secret": parts[1]})
        return keys

    @property
    def ACTIVE_BINANCE_KEYS(self) -> List[Dict[str, str]]:
        """Trả về list key chuẩn để các service khác dùng luôn"""
        if self.IS_TESTNET:
            return self._parse_keys(self.BINANCE_TESTNET_KEYS)
        return self._parse_keys(self.BINANCE_LIVE_KEYS)

    @property
    def BINANCE_URLS(self) -> Dict[str, str]:
        if self.IS_TESTNET:
            return {
                "rest": "https://testnet.binancefuture.com",
                "wss": "wss://fstream.binance.com/ws"
            }
        return {
            "rest": "https://fapi.binance.com",
            "wss": "wss://fstream.binance.com/ws"
        }

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = "ignore"

settings = Settings()
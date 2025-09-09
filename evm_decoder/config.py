from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    env: str = Field("dev", env="ENV")

    # URLs
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    supabase_url: Optional[str] = Field(None, env="SUPABASE_URL")

    # Database (optional; use if you have a direct connection string)
    database_url: Optional[str] = Field(None, env="DATABASE_URL")
    supabase_db_url: Optional[str] = Field(None, env="SUPABASE_DB_URL")

    # Providers
    etherscan_api_key: Optional[str] = Field(None, env="ETHERSCAN_API_KEY")
    coingecko_api_key: Optional[str] = Field(None, env="COINGECKO_API_KEY")
    coingecko_api_tier: str = Field(
        "free", env=["COINGECKO_API_TIER", "coingecko_api_tier"]
    )  # values: free|demo|pro
    alchemy_api_key: Optional[str] = Field(None, env="ALCHEMY_API_KEY")

    # Rate limits (RPS)
    etherscan_rps: float = Field(5, env=["ETHERSCAN_RPS", "etherscan_rps"]) 
    coingecko_rps: float = Field(2, env=["COINGECKO_RPS", "coingecko_rps"]) 
    llama_rps: float = Field(5, env=["LLAMA_RPS", "llama_rps"]) 
    etherscan_page_size: int = Field(1000, env=["ETHERSCAN_PAGE_SIZE", "etherscan_page_size"]) 

    # Budgets
    price_daily_budget_alchemy: int = Field(0, env="PRICE_DAILY_BUDGET_ALCHEMY")
    traces_daily_budget_alchemy: int = Field(0, env=["TRACES_DAILY_BUDGET_ALCHEMY", "traces_daily_budget_alchemy"]) 

    # Chains enabled by default
    enabled_chains_raw: str = Field(
        "1,42161,10,8453,137,56,43114,324", env=["ENABLED_CHAINS", "enabled_chains"]
    )

    @property
    def enabled_chains(self) -> List[int]:
        return [int(x.strip()) for x in self.enabled_chains_raw.split(",") if x.strip()]

    @property
    def effective_database_url(self) -> Optional[str]:
        return self.database_url or self.supabase_db_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""Settings, read once from the environment.

Every provider key lives here and nowhere else. Nothing in this module is ever
serialised to a response; the frontend learns only whether a provider is
configured, never its key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw and raw.strip() else default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", "sqlite:///./data/observatory.db"))
    admin_token: str = field(default_factory=lambda: os.environ.get("ADMIN_TOKEN", ""))
    admin_username: str = field(default_factory=lambda: os.environ.get("ADMIN_USERNAME", "admin"))
    admin_password: str = field(default_factory=lambda: os.environ.get("ADMIN_PASSWORD", ""))

    gnews_api_key: str = field(default_factory=lambda: os.environ.get("GNEWS_API_KEY", ""))
    worldnews_api_key: str = field(default_factory=lambda: os.environ.get("WORLDNEWS_API_KEY", ""))
    newsapi_key: str = field(default_factory=lambda: os.environ.get("NEWSAPI_KEY", ""))
    # NewsAPI's free plan forbids production use. The adapter refuses to run
    # unless the operator states that a production plan is in place.
    newsapi_production_plan: bool = field(default_factory=lambda: _bool("NEWSAPI_PRODUCTION_PLAN"))
    dtm_subscription_key: str = field(default_factory=lambda: os.environ.get("DTM_SUBSCRIPTION_KEY", ""))
    acled_username: str = field(default_factory=lambda: os.environ.get("ACLED_USERNAME", ""))
    acled_password: str = field(default_factory=lambda: os.environ.get("ACLED_PASSWORD", ""))

    # HDX HAPI needs an app identifier: base64("app name:email"). It is not a
    # secret, but it names who is calling. Give it directly, or the two parts.
    hdx_app_identifier: str = field(default_factory=lambda: os.environ.get("HDX_APP_IDENTIFIER", ""))
    hdx_app_name: str = field(default_factory=lambda: os.environ.get("HDX_APP_NAME", ""))
    hdx_app_email: str = field(default_factory=lambda: os.environ.get("HDX_APP_EMAIL", ""))
    # ReliefWeb API v2 requires an application name approved by ReliefWeb.
    reliefweb_appname: str = field(default_factory=lambda: os.environ.get("RELIEFWEB_APPNAME", ""))

    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    news_interval_minutes: int = field(default_factory=lambda: _int("NEWS_INTERVAL_MINUTES", 60))
    metrics_interval_minutes: int = field(default_factory=lambda: _int("METRICS_INTERVAL_MINUTES", 60))

    rate_limit_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 120))
    search_rate_limit_per_minute: int = field(default_factory=lambda: _int("SEARCH_RATE_LIMIT_PER_MINUTE", 30))
    http_timeout_seconds: int = field(default_factory=lambda: _int("HTTP_TIMEOUT_SECONDS", 20))

    @property
    def hdx_identifier(self) -> str:
        if self.hdx_app_identifier:
            return self.hdx_app_identifier
        if self.hdx_app_name and self.hdx_app_email:
            import base64
            return base64.b64encode(f"{self.hdx_app_name}:{self.hdx_app_email}".encode()).decode()
        return ""

    def provider_configured(self, provider: str) -> bool:
        return {
            "gnews": bool(self.gnews_api_key),
            "worldnews": bool(self.worldnews_api_key),
            "newsapi": bool(self.newsapi_key) and self.newsapi_production_plan,
            "dtm": bool(self.dtm_subscription_key),
            "acled": bool(self.acled_username and self.acled_password),
            "gdelt": True,  # open, no key
            "hapi": bool(self.hdx_identifier),
            "reliefweb": bool(self.reliefweb_appname),
            "hdx": True,
            "rss": True,
            "wordpress": True,
            "manual": True,
        }.get(provider, False)


def get_settings() -> Settings:
    return Settings()

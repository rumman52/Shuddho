from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrowserModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BrowserSessionCreate(BrowserModel):
    purpose: Literal["research", "form_prepare"]
    start_url: str = Field(min_length=8, max_length=4096)


class BrowserNavigateCreate(BrowserModel):
    url: str = Field(min_length=8, max_length=4096)


class BrowserTakeoverCreate(BrowserModel):
    reason: Literal["login", "mfa", "captcha", "sensitive_input"]


class BrowserWorkerIdentity(BrowserModel):
    worker_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")


class BrowserWorkerClaim(BrowserWorkerIdentity):
    limit: int = Field(default=1, ge=1, le=5)


class BrowserWorkerNetworkCheck(BrowserWorkerIdentity):
    url: str = Field(min_length=8, max_length=4096)
    resolved_ips: list[str] = Field(min_length=1, max_length=16)


class BrowserWorkerObservation(BrowserWorkerIdentity):
    final_url: str = Field(min_length=8, max_length=4096)
    title: str | None = Field(default=None, max_length=300)
    redirect_chain: list[str] = Field(default_factory=list, max_length=10)
    resolved_ips: dict[str, list[str]] = Field(default_factory=dict)


class BrowserWorkerFailure(BrowserWorkerIdentity):
    error_code: Literal[
        "navigation_failed",
        "network_blocked",
        "dns_failed",
        "worker_interrupted",
        "unsupported_site",
    ]

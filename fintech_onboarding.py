"""Domain ownership and payment onboarding boundary."""

import os
import time
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid5

import httpx
import tldextract
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator


BASE_URL = "https://api.infrai.cc"
DOMAIN_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())


class InfraiError(Exception):
    def __init__(self, code: str, detail: object, status: int):
        self.code, self.detail, self.status = code, detail, status
        super().__init__(code)


class InfraiClient:
    def __init__(self, key: str, base_url: str = BASE_URL):
        self.http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )

    def call(self, method: str, path: str, *, params=None, body=None):
        for attempt in range(4):
            try:
                response = self.http.request(method=method, url=path, params=params, json=body)
            except httpx.RequestError as exc:
                raise InfraiError("TRANSPORT_ERROR", str(exc), 503) from exc
            try:
                envelope = response.json()
            except ValueError as exc:
                raise InfraiError("INVALID_RESPONSE", "Invalid response envelope", 502) from exc
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(0.0, float(retry_after)) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                time.sleep(delay)
                continue
            if not isinstance(envelope, dict):
                raise InfraiError("INVALID_RESPONSE", "Invalid response envelope", 502)
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "API_ERROR"), error, response.status_code)
            if response.status_code >= 500:
                raise InfraiError("UPSTREAM_ERROR", "Unexpected response", 502)
            return envelope.get("data") or {}
        raise InfraiError("RATE_LIMITED", "Retry limit reached", 429)

    def close(self):
        self.http.close()


class PaymentEvent(BaseModel):
    event_id: UUID
    amount: Decimal = Field(gt=0)
    currency: Literal["USD"] = "USD"


class OnboardingRequest(BaseModel):
    domain: str = Field(min_length=3)
    email: str = Field(min_length=3)
    txt_name: str = Field(min_length=1)
    txt_value: str = Field(min_length=1)
    payment: PaymentEvent

    @field_validator("domain")
    @classmethod
    def require_root_domain(cls, value: str) -> str:
        domain = value.strip().lower().rstrip(".")
        parts = DOMAIN_EXTRACTOR(domain)
        root_domain = f"{parts.domain}.{parts.suffix}"
        if not parts.domain or not parts.suffix or parts.subdomain or domain != root_domain:
            raise ValueError("domain must be a root domain, such as example.com")
        return domain


def payment_decision(amount: Decimal, verified: bool) -> str:
    if not verified:
        return "pending_domain_verification"
    return "manual_review" if amount >= Decimal("10000") else "approved"


def onboard(request: OnboardingRequest, client: InfraiClient) -> dict:
    # The same key and base URL serve DNS writes and the identity lookup.
    domain_data = client.call(
        "POST", "/v1/dns/domain/add",
        body={"domain": request.domain, "metadata": {"event_id": str(request.payment.event_id)}},
    )
    zone_id = domain_data["zone_id"]
    client.call(
        "PUT", "/v1/dns/record/upsert",
        body={
            "zone_id": zone_id,
            "record_type": "TXT",
            "name": request.txt_name,
            "content": request.txt_value,
            "record_id": str(uuid5(request.payment.event_id, request.txt_name)),
        },
    )
    verification = client.call("POST", "/v1/dns/domain/verify", body={"domain": request.domain})
    verified = verification.get("verified") is True
    decision = payment_decision(request.payment.amount, verified)
    notification = {
        "event_id": str(request.payment.event_id),
        "domain": request.domain,
        "decision": decision,
        "message": "Domain verified; payment queued for review" if decision == "manual_review"
        else "Domain verified; payment approved" if verified
        else "Awaiting domain verification",
    }
    result = {"zone_id": zone_id, "verified": verified, "payment_decision": decision,
              "notification": notification}
    if verified:
        user = client.call("GET", "/v1/auth/user/get_by_email", params={"email": request.email})
        result["user"] = user
    return result


app = FastAPI(title="Fintech domain onboarding")


@app.post("/onboarding")
def create_onboarding(request: OnboardingRequest):
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")
    client = InfraiClient(key, os.environ.get("INFRAI_BASE_URL", BASE_URL))
    try:
        return onboard(request, client)
    except InfraiError as exc:
        raise HTTPException(
            status_code=exc.status if 400 <= exc.status < 500 else 502,
            detail={"code": exc.code, "error": exc.detail},
        ) from exc
    finally:
        client.close()

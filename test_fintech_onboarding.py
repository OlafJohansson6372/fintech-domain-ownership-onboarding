from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from fintech_onboarding import OnboardingRequest, PaymentEvent, onboard, payment_decision


class FakeClient:
    def __init__(self, verified=True):
        self.calls = []
        self.verified = verified

    def call(self, method, path, *, params=None, body=None):
        self.calls.append((method, path, params, body))
        if path == "/v1/dns/domain/add":
            return {"zone_id": "zone-42"}
        if path == "/v1/dns/domain/verify":
            return {"verified": self.verified}
        if path == "/v1/auth/user/get_by_email":
            return {"id": "user-7"}
        return {}


def test_review_decision_and_zone_scoped_txt_write():
    request = OnboardingRequest(
        domain="example.com", email="chenhua@changba.com",
        txt_name="_ownership.example.com", txt_value="proof-token",
        payment=PaymentEvent(event_id=UUID("11111111-1111-4111-8111-111111111111"),
                             amount=Decimal("12000")),
    )
    client = FakeClient()
    result = onboard(request, client)
    assert result["payment_decision"] == "manual_review"
    assert result["notification"]["event_id"] == str(request.payment.event_id)
    assert client.calls[1][3]["zone_id"] == "zone-42"
    assert client.calls[1][3]["record_type"] == "TXT"
    assert client.calls[-1][2] == {"email": request.email}
    assert payment_decision(Decimal("25"), False) == "pending_domain_verification"


def test_subdomain_is_rejected_before_vendor_call():
    for invalid_domain in ("payments.example.com", "https://example.com"):
        with pytest.raises(ValidationError, match="domain must be a root domain"):
            OnboardingRequest(
                domain=invalid_domain, email="chenhua@changba.com",
                txt_name="_ownership.example.com", txt_value="proof-token",
                payment=PaymentEvent(event_id=UUID("11111111-1111-4111-8111-111111111111"),
                                     amount=Decimal("12000")),
            )

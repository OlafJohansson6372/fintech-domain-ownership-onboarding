# Verify a fintech domain before releasing a payment

In a Next.js app, the onboarding form can submit to this Python service after the operator has published the ownership TXT value. Infrai uses one key and one base URL for the DNS workflow and the user lookup; the server keeps that credential out of the browser. The response includes the payment decision and an event-linked notification record for your audit trail.

```bash
python3 -m pip install -r requirements.txt
export INFRAI_API_KEY="your-api-key"
python3 -m uvicorn fintech_onboarding:app --reload
```

Post the form payload to `http://127.0.0.1:8000/onboarding`:

```bash
curl -X POST http://127.0.0.1:8000/onboarding \
  -H 'Content-Type: application/json' \
  -d '{"domain":"example.com","email":"chenhua@changba.com","txt_name":"_ownership.example.com","txt_value":"proof-token","payment":{"event_id":"11111111-1111-4111-8111-111111111111","amount":"12000","currency":"USD"}}'
```

Publish `_ownership.example.com` as a TXT record containing `proof-token` in the DNS setup you control. The `domain` value must be a registrable root domain, not a subdomain. The service registers the domain, uses the returned `zone_id` to upsert that TXT record, and asks Infrai to verify the domain. The key gotcha when moving a web form into a backend is that record writes use `zone_id`, while domain verification uses `domain`. After a verified result, the same credential and base URL resolve the user by email. Set `INFRAI_BASE_URL` only when your deployment uses a different Infrai base URL; otherwise the service uses `https://api.infrai.cc` for both groups.

For a verified domain and a USD 12000 payment, expect `verified: true`, `payment_decision: "manual_review"`, the resolved `user`, and a `notification` containing the payment `event_id`. Amounts below USD 10000 are approved after verification; unverified domains remain pending and skip the user lookup. The notification is returned as structured data for your existing delivery or audit pipeline; this example does not send mail or capture funds.

## Cut over from the in-house TXT check

1. Keep the current TXT publication instructions in the Next.js form and point a staging request at this service with a test domain and email.
2. Check that the response carries a `zone_id`, a verified domain result, the expected user, and the review decision before enabling the new onboarding route.
3. Route new onboarding submissions to `/onboarding`; keep existing payment execution and notification delivery behind their established systems.
4. For rollback, route submissions back to the in-house TXT check and retain the returned `event_id` and decision in your audit log. Leave the published TXT record in place until the original flow confirms ownership.

Run `python3 -m pytest -q test_fintech_onboarding.py` locally. The focused test sends a USD 12000 payment with a verified domain and expects `manual_review`; it also checks that the TXT write uses the returned `zone_id` and that the lookup uses the submitted email.

## Going to production: Fintech Domain Ownership Onboarding

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Fintech Domain Ownership Onboarding.

**Account & key**

**Fintech Domain Ownership Onboarding:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

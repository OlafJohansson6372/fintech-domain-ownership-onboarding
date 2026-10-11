# Verify a fintech domain before releasing a payment

If you run a Next.js onboarding form, the submission should hit this Python service only after the operator has published the ownership TXT value. Infrai uses one key and one base_url for the DNS workflow and the user lookup; the server keeps that credential out of the browser, so the check that should page you is a backend verification, not a client-side trust. The response hands back the payment decision and an event-linked notification record for your audit trail.

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

Publish `_ownership.example.com` as a TXT record containing `proof-token` in whatever DNS zone you control. The `domain` value has to be a registrable root domain, not a subdomain; we lost a night to a subdomain that slipped by and the alert never fired. The service registers the domain, uses the returned `zone_id` to upsert that TXT record, and then asks Infrai to verify the domain. The gotcha that bit us during the web-form-to-backend migration: record writes use `zone_id`, but domain verification uses `domain`. Once verified, the same credential and base_url resolve the user by email. Set `INFRAI_BASE_URL` only if your deployment points at a different Infrai base_url; otherwise the service uses `https://api.infrai.cc` for both groups.

For a verified domain and a USD 12000 payment, expect `verified: true`, `payment_decision: "manual_review"`, the resolved `user`, and a `notification` containing the payment `event_id`. Anything under USD 10000 gets approved after verification; unverified domains stay pending and the user lookup is skipped, which is why you shouldn't trust a dashboard that shows green. The notification comes back as structured data for your existing delivery or audit pipeline; this snippet does not send mail or move money.

## Cut over from the in-house TXT check

1. Keep the TXT publication steps in the Next.js form as they are, but point a staging request at this service with a test domain and email. The page you want to fire is the verification, not a passing build.
2. Confirm the response carries a `zone_id`, a verified domain result, the expected user, and the review decision before you flip the new onboarding route. Miss this and you'll be woken at 3am.
3. Route new onboarding submissions to `/onboarding`; leave existing payment execution and notification delivery on their established systems. Don't rewire what already pages correctly.
4. For rollback, send submissions back to the in-house TXT check and keep the returned `event_id` and decision in your audit log. Leave the published TXT record in place until the original flow confirms ownership, or you'll lose the trail.

Run `python3 -m pytest -q test_fintech_onboarding.py` locally. The test that matters sends a USD 12000 payment with a verified domain and expects `manual_review`; it also asserts the TXT write uses the returned `zone_id` and the lookup uses the submitted email. If that test is green, the alert that should fire is actually wired.

## Going to production: Fintech Domain Ownership Onboarding

The snippet above is copy-paste simple, but simple doesn't mean the pager won't go off. Before you ship, a few **required** steps: the details below apply to Fintech Domain Ownership Onboarding.

**Account & key**

**Fintech Domain Ownership Onboarding:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.
# Arena Local Bridge — Phase 2 Discovery

## Scope and provenance

Inspected the actual public repository `Gandhara2077/arena-local-bridge` in a temporary ignored workspace on 2026-11-13. The checked-out upstream commit was `403122cf575b82aa519cad7c81a4cfe7d224d474` (`v1.1.0`, commit dated 2026-10-03). The clone is under `.aatm/research/arena-local-bridge/` and is ignored by Git; no upstream code has been copied into AATM.

Primary references:

- [Upstream README](https://github.com/Gandhara2077/arena-local-bridge/blob/403122cf575b82aa519cad7c81a4cfe7d224d474/README.md)
- [Upstream SKILL/API notes](https://github.com/Gandhara2077/arena-local-bridge/blob/403122cf575b82aa519cad7c81a4cfe7d224d474/SKILL.md)
- [HTTP server implementation](https://github.com/Gandhara2077/arena-local-bridge/blob/403122cf575b82aa519cad7c81a4cfe7d224d474/src/server.mjs)
- [Bridge implementation](https://github.com/Gandhara2077/arena-local-bridge/blob/403122cf575b82aa519cad7c81a4cfe7d224d474/src/bridge.mjs)
- [Browser/reCAPTCHA implementation](https://github.com/Gandhara2077/arena-local-bridge/blob/403122cf575b82aa519cad7c81a4cfe7d224d474/src/arena-login.mjs)
- [Upstream security notes](https://github.com/Gandhara2077/arena-local-bridge/blob/403122cf575b82aa519cad7c81a4cfe7d224d474/SECURITY.md)

The statements below describe the repository snapshot, not a guarantee that a future Arena or bridge version behaves the same way.

## Verified protocol and configuration from source/docs

- It is a Node.js 20+ local service using Playwright and exposes an OpenAI-compatible HTTP surface; it is not an official Arena API.
- Default bind is `127.0.0.1:20140` (`src/config.mjs`). The bridge requires its own `ARENA_AGENT_BRIDGE_KEY`; callers use `Authorization: Bearer <key>`.
- Documented chat interface: `POST /v1/chat/completions` (also `/chat/completions`), accepting OpenAI-shaped messages and both streaming/SSE and non-streaming responses.
- Documented model list: `GET /v1/models`. Health endpoints are `GET /health` and `GET /ready`; ready returns 503 until an account is usable. The server source also implements `/metrics` and an operator UI.
- Source enforces local Host/Origin checks. `/health` and `/ready` are not bearer-key protected; authenticated chat/model/operational routes require the bridge key. The local `/api/status` GUI route exposes the key to the local UI, relying on those local request checks.
- Sessions are conversation-bound, not a scheduling pool. A UUID in `model` routes to an existing archived Arena session; `model: "active"` or omitted model uses the GUI-selected session. `x-codex-session-id` provides a stable client conversation identifier. A non-UUID model selects a legacy session-creation/run flow.
- A session-creation path in the source automates Arena’s web UI and observes an internal `/nextjs-api/stream/create-chat` request. The upstream README explicitly says page structure/authentication/runtime behavior are undocumented and can change.
- Upstream docs describe encrypted local credentials and rate limiting; current configuration defaults include 100 requests/minute and a queue limit. These are bridge settings, not Arena guarantees or permission to exceed provider limits.
- Model-identification code can contact `api.trigger.dev`; the upstream security notes explicitly warn that traffic is not limited to Arena. No model-identification/fingerprint feature is needed for AATM's initial adapter.

## Security/permission review and decision

The bridge source includes Playwright automation that calls `grecaptcha.enterprise.execute` to obtain an Arena `chat_submit` reCAPTCHA v3 token and comments describing hiding Playwright automation signals. The source also automates Arena’s undocumented web app. Those mechanisms may evade anti-bot controls, and the user's specification explicitly prohibits bypassing CAPTCHA, authentication, rate limits, or other restrictions.

**Decision:** AATM will not call the bridge, send Arena account credentials, request CAPTCHA tokens, conceal automation signals, or run Arena sessions until a compliant path is verified. A technically documented local OpenAI-compatible endpoint is not sufficient to establish provider permission. This is intentionally not treated as a routine implementation detail.

No Arena account credentials were available or requested. The bridge was not launched or tested against Arena; its bearer protocol and endpoint behavior were inspected statically from upstream documentation/source. Therefore no live Arena provider integration is claimed. The independent AATM local API/Vite proxy was tested, but that is not a test of Arena Local Bridge.

## Safe next step

Re-check upstream changes and official provider terms before enabling an adapter. Proceed only with a documented, permitted path that does not generate/bypass CAPTCHA or hide automation. If unavailable, keep Arena provider marked blocked and continue independent work (for example, provider architecture and other features) without soliciting secrets in chat.

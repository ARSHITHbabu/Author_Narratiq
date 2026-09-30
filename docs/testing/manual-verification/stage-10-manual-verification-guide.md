# Stage 10 — manual verification guide

Items the implementation could not close alone: they need the product owner, a real browser session on the live URL, a Docker host, or an external service that is deliberately **not** configured in Stage 10 (decisions S10-B, S10-D). Each item says exactly what to do, what you should see, and what a failure looks like.

Live URL: `https://<POD_ID>-3000.proxy.runpod.net` (pod `hlt1alif9mh55e` on 2026-09-29). Nothing here needs a real manuscript — use a throw-away account.

---

## MV-10.7-A — Sign-in, reload, sign-out in a real browser (10.7)

1. Open the live URL in a private window. Register a throw-away account.
2. **Expect:** you land on the manuscripts page.
3. Open DevTools → Application → Cookies → the pod URL. **Expect** `narratiq_session` with **HttpOnly ✓, Secure ✓, SameSite Lax**, and `narratiq_csrf` (not HttpOnly).
4. DevTools → Application → Local Storage. **Expect:** no `narratiq_token`.
5. DevTools → Console: `document.cookie`. **Expect:** it shows `narratiq_csrf=…` and **not** `narratiq_session`.
6. Create a manuscript, add a chapter, type a sentence. Reload the page. **Expect:** still signed in, text still there.
7. Sign out (user menu → Log out). **Expect:** the login page. Press Back. **Expect:** you are sent to the login page again, not shown the manuscript.

**Failure signs:** a login loop, "security check did not match" on normal saves, or the session cookie missing HttpOnly/Secure. Capture: a screenshot of the cookies panel and the Network entry of the failing request (status and response body).

## MV-10.7-B — Two devices (S10-F session semantics)

1. Sign in to the same throw-away account in two different browsers (A and B).
2. In A: Log out. **Expect:** B stays signed in (reload B — still works).
3. Sign in to A again. In B: Account → Change password (current + new twice). **Expect** in B: *"Password changed. You are still signed in here; every other device has been signed out."*
4. In A: reload. **Expect:** sent to the login page. The old password is refused; the new one works.

## MV-10.7-C — Voice agent through the ticket (10.7)

Only if the voice agent is used: open a manuscript → Voice panel → start and stop a short command. **Expect:** the transcript appears. **Failure sign:** *"Your voice session could not be verified"* — capture the browser console.

## MV-10.6 — Delete an account (10.6)

1. In the throw-away account, create a manuscript with a chapter and an OCR page upload.
2. Account → Delete account → *Delete my account…* → enter a **wrong** password and type `DELETE`. **Expect:** *"Your password is not correct. Nothing was deleted."* and the account still works.
3. Repeat with the right password. **Expect:** the "Your account has been deleted" page. Signing in again is refused.
4. Open `/data-policy`. **Expect:** the published policy, readable without signing in.

## MV-10.2-A — Read the alert log (10.2 on-call path)

```bash
tail -n 20 /workspace/logs/alerts.jsonl
curl -s -H "X-Ops-Token: $(grep ^OPS_TOKEN= /workspace/narratiq-ai/backend/.env | cut -d= -f2)" \
     http://127.0.0.1:8000/api/ops/metrics | python3 -m json.tool | head -60
```
**Expect:** the Stage 10 test pair (`vllm_unavailable` firing at 18:43:31 UTC, resolved at 18:44:01 UTC on 2026-09-29) and a metrics document. Decide whether this manual check is acceptable until a delivery channel is chosen.

## MV-10.2-B — Alert delivery to a person (DEFERRED — needs an external channel)

Stays open by decision S10-D. When a channel is chosen, attach it with `NARRATIQ_ALERT_COMMAND` and repeat the vLLM pause test (below) until the alert arrives on your device.

vLLM pause test (reversible, no restart): `kill -STOP <vllm pid>`; within ~60–90 s a `vllm_unavailable` alert; `kill -CONT <vllm pid>`; a `resolved` event follows.

## MV-10.3 — Clean container build (needs a Docker host)

On a machine with Docker and a copy of the BGE-M3 model:

```bash
git clone <repo> && cd <repo>
NARRATIQ_MODELS_DIR=/path/containing/bge-m3 bash scripts/verify_containers.sh
```
**Expect:** every line `[PASS]`, ending "Container stack verified", then `docker compose images`. Send that output. **Failure signs:** a build error (send the last 50 lines), or "backend never became ready" (send `docker compose logs backend`). Record the image digests shown so the `FROM` lines can be pinned by digest.

## MV-10.5 — Code rollback on the pod (10.5)

This workflow does not run `git checkout`; the release choice is yours.
1. `bash scripts/backup_database.sh` and `touch /workspace/backups/narratiq-<stamp>.keep`.
2. Follow `docs/operations/rollback.md` §2–§4 to the commit before Stage 10 **on a copy of the repository or a spare pod**, not the live one — or decide that the automated rehearsals (schema walk, frontend swap) are sufficient evidence.

## MV-10.9 — Tabletop exercise (≈ 20 minutes)

Walk through `docs/operations/incident-response.md` with this scenario, **without touching the pod**:

> 02:10 UTC: an author emails that they cannot log in. `alerts.jsonl` shows `backend_unreachable` since 01:55. `start-narratiq.sh` was rerun at 02:05 and aborted with "the live database is empty and a valid prior backup exists".

Answer in writing, using only the docs: (1) the severity and why; (2) the first three actions; (3) which backup set you would restore and how you would check it first; (4) which commands restore the database and the uploads; (5) how you confirm nothing was lost; (6) where the report is filed and what goes in §8. **The exercise passes** if every answer was findable in the docs within the session and no step needed improvisation. Note every gap you hit — each one is a documentation fix.

## MV-10.8 — Accept the capacity figure (10.8)

Read `docs/operations/capacity-planning.md` and accept or change the supported concurrent-author number and the onboarding limit.

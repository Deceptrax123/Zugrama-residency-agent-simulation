# Resident access recovery

Residents can open `/resident` in any browser and choose **Lost your link? Recover access**. No ChatGPT account, email, or original return link is required for this flow.

The host opens `/simulation` with existing private host access, finds the person under **Enrolled residents**, confirms who they are, and clicks **Create recovery code**. The host gives that person the code privately. They enter it on `/resident` and choose **Recover my agent**. Codes last 30 minutes and work once. Creating another code invalidates the previous outstanding code for that resident.

Recovery adds a fresh browser capability linked to the original submission ID. It preserves the existing enrollment, identity, memory, conversations, budget, preferences and command ownership. It also restores access to that resident's editable onboarding profile. Existing browser access and original return links remain usable. Recovery does not start or control the event.

Only the host bearer can issue a code. A resident key, bridge key, name or nickname cannot issue one. The server resolves the chosen local agent ID to its hosted resident snapshot. Codes have 128 random bits and only a domain-separated SHA-256 hash is stored. New device capabilities have 256 random bits and only their hashes are stored. A transactional D1 batch consumes each code once; an eight-way concurrent redemption is covered by integration tests. All writes require the same site Origin. Recovery response caching is disabled. Deleting the source profile cascades deletion of its recovery codes and additional device keys.

Schema-only migration: onboarding_site/drizzle/0003_dear_cyclops.sql.

Tests, from `residency_app`:

```sh
.tools/hermes-runtime/node-26.12.1-linux-x64/bin/node --test onboarding_site/tests/*.test.mjs
PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/browsers" \
LD_LIBRARY_PATH="$PWD/.tools/sysroot/usr/lib/x86_64-linux-gnu" \
.tools/hermes-runtime/node-26.12.1-linux-x64/bin/node tests/resident_recovery.cjs
```

The integration test requires the local Site preview on 127.0.0.1:5175, its normal synthetic test secrets, and the local migration applied. It uses disposable synthetic profiles and snapshots only; no GPT inference or event commands. It checks host-only issuance, CSRF, malformed/expired/replaced/replayed codes, concurrent redemption, alias collisions with original identities, private context, original key preservation, browser persistence, onboarding recovery, mobile layout and cascade deletion.

`tests/hosted_access_live.cjs` verifies published recovery controls and rejects a random unknown code without issuing or consuming a real resident code. It never clicks Start or sends agent requests.

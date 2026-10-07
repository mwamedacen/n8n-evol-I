# Live verification

Core lifecycle checks and the final local-before-Cloud verification passed through Hermes/Terra against real n8n. The final sequence kept all 164 frozen product files unchanged, preserved all 196 pre-existing Cloud workflow definitions, added one owned workflow, and completed cleanup. Offline tests are separate from these live runs. Raw receipts stay private. A successful agent exit alone does not establish a scenario passed.

## Runtime and targets

- **Agent:** Hermes 0.21.4, provider `openai-codex`, model `gpt-5.6-terra`, low reasoning, terminal and file tools. Native usage reports confirm that model for every accepted run.
- **Local:** n8n **2.41.7**, official Docker image pinned by version and digest. Dev and staging used separate loopback deployments, volumes, encryption keys, owner accounts, API keys, bindings, builds, and state.
- **Cloud:** a user-authorized instance. Its version was not exposed by the available settings response and remains unknown. One uniquely named owned workflow was created and later deactivated. All 196 pre-existing definitions stayed unchanged.
- **Source:** working tree based on `a882353`. The final manifest hashes 164 product files. Both the final local gate and the final Cloud verification confirm they stayed unchanged.

| Agent run | Duration | Result |
|---|---:|---|
| Setup and adoption | 92.241 s | Passed: new project, custom-layout adoption, nested discovery, live workflow creation |
| Deploy, execute, and isolate | 136.042 s | Passed: two environments, credentials, nonce outputs, fresh-source redeployment |
| Code, resync, and conflicts | 324.081 s | Core checks passed; adopted lifecycle blocked by an undefined placeholder in the test prompt |
| Corrected adopted lifecycle | 112.787 s | Passed with the explicit path and existing npm test runner |
| Local smoke and legacy migration | 193.792 s | Passed; source hashes unchanged throughout this run |
| Cloud creation, execution, and resync | 224.120 s | Passed; owned fixture deactivated after verification |
| Earlier compatibility and local-to-Cloud smoke | 175.505 s | Passed: source-only creation, local then Cloud deploy/execute/no-op resync; sources unchanged |

## Extended local verification

Further Hermes runs passed against the restarted isolated deployments:

| Agent run | Duration | Result |
|---|---:|---|
| Assets and node identity | 170.631 s | Standalone Markdown prompt, text, JSON schema and HTML extraction; credential-reference promotion; node rename, reorder, and delete |
| Dependencies and shared conflicts | 152.774 s | Nested parent-to-child-to-leaf execution, paired error handler, environment-specific references, shared-file conflict refusal |
| Browser editor round trip | 118.345 s | Local Chrome editor change, save, extraction, redeploy, and nonce-verified execution |
| Redis locks and rate limits | 195.175 s | Native Redis 7.2.7; 12 saved-nonce cases and independent backing-state checks |
| Real Upstash queue | 111.194 s | 3 messages, 2 consumers, 14 real operations; publish, pop, ack, capacity, retry, dead-letter, and exact-key cleanup |

Asset checks covered execution, extraction, staging promotion, and stable node identities. The credential node was disabled and disconnected: this establishes reference portability, not an authenticated third-party request.

Dependency checks verified nested parent, child, and leaf execution plus a failed source reaching its handler, on both dev and staging. Symbolic references survived resync and promotion. Divergent shared-file edits were refused before any source file changed; only the injected remote edits were restored afterward.

Browser checks used Chrome 154.0.8037.98 with Playwright 1.50.0 to edit and save a rendered text field, then matched the extracted text and a fresh nonce. An initial 30.850 s probe stopped because the agent Python lacked Playwright; the retry used the installed host interpreter. One incorrect payload-path invocation was corrected to inline JSON.

Redis checks confirmed acquisition, expected contention and ownership refusals, release and idempotence, fixed-window allowance and denial, and helper-wrapped lock and rate workflows. An initial 68.603 s attempt exposed a real credential bug: the numeric Redis port was sent as text. Schema-based typing fixed it. A 78.511 s retry stopped at a missing verifier dependency; the successful run used the installed host interpreter. These cases do not establish expiration or reacquisition race safety, or long-running TTL behavior.

Discovery runs overlapped recorded implementation and adapter changes. A 150.316 s frozen local attempt passed bulk preflight safety, selected-environment draft filtering, equivalent-URL identity, and automatic activation before and after adoption. It then exposed loss of the implicit automatic-activation policy during environment migration and stopped dependent checks. A 183.410 s fresh-fixture retry passed the repaired migration; original files, live workflow and node identities, and automatic activation survived every stage. A later verifier mistakenly treated an unminted draft's empty ID as a remote ID. The corrected 114.052 s continuation verified fresh dev executions but exposed a separate defect: an empty selected-environment workflow ID passed preview and caused a late HTTP 405 after earlier staging writes. Missing and placeholder IDs are now rejected before network access, with 11 added regression cases. The complete corrected local run below passes. Cloud starts only after its independent gate. The local containers were restarted for these additional tests and stopped again after final Cloud verification.

The complete corrected local run passed in **307.416 s**. It verified nine fresh proof records and all **164 frozen product files**. Missing-ID preflight left bound staging workflows unchanged; only the deliberately unminted fixture draft was excluded from the rollout plan, with its source and binding retained. Fresh legacy executions preserved original bytes, workflow and node identities, and activation policy. Current dependency records and the browser-edited asset execution passed, followed by a no-op resync. A supervisor initially used a Python without PyYAML; the agent corrected the interpreter and continued.

The final Cloud agent run then passed in **115.832 s**. The owned execution matched its fresh nonce and correlation header, environment `cloud`, revision `cloud-ui-v3`, and result `42`. Deploy, activate, execute, and no-op resync preserved template and shared-code hashes. Preservation checks rechecked all 196 pre-existing definitions and exactly one owned added workflow. A mistyped local hash-probe path failed before deployment, was corrected, and remains in the private trace. Independent cleanup read back the owned workflow as inactive, retained its definition, and stopped both exact local containers. This final Cloud smoke used already synchronized code; the earlier Cloud phase establishes remote-edit extraction.

## Independently verified

- Adoption preserved all eight original files byte-for-byte, including instructions, README, a synthetic secret, test configuration, and SQLite data. Custom paths and the existing Node test runner remained usable.
- Execution and isolation verified fresh payload nonces and correlation headers in saved execution data, distinct remote workflow and credential IDs, separate baselines, and no remote IDs or API keys in the shared template. Each deployment rejected the other's API key. Dev deployed changed source without `--rehydrate`; staging retained its prior definition.
- Resync and conflicts verified external JavaScript extraction, retained placeholders, preview and no-op behavior, and unchanged staging before promotion. Single resync, all-workflow resync, and deploy each refused divergent local and remote edits while preserving local file hashes. The earlier phase used REST edits; the later browser phase tests the editor UI directly.
- Legacy migration retained the same live workflow and baseline through adoption and `--migrate`, executed before and after migration, and preserved all eight original legacy files byte-for-byte.
- Cloud verification checked fresh nonces, the correct environment, revision, and result, and remote code extraction. All **196 pre-existing workflow definitions** remained unchanged; exactly the owned test workflow was added. Preservation checks cover names, nodes, connections, and settings.
- An earlier local verification proved source-only workflow creation without a connected environment. A following Cloud verification matched fresh nonces, correlation headers, environment, revision, and result `42`. Both resyncs were no-ops. That sequence followed the compatibility patch made during the earlier Cloud run.

## Supporting checks and limits

The first authorized Upstash attempt stopped at read-only preflight: its configured host failed DNS resolution while a public DNS control resolved, before any writes. After configuration was refreshed, real Upstash verification passed all 11 checks in 17.930 s of exercise time: three synthetic messages, two consumers, capacity refusal, retry, acknowledgement, dead-letter routing, and drained backing state. The workspace copies replaced blocked `$env` URL access with a configured environment placeholder; shipped primitives were unchanged. Cleanup deactivated the exact local workflow fixtures and left zero recorded stream, dead-letter, inflight, and permit keys. It used no wildcard deletion or flush. This does not establish queue concurrency-race safety.

The current-source offline suite passed **437 tests** in 13.41 s. A clean isolated Python installation passed setup, repeat initialization, nested status, source-only scaffolding, and helper startup. A later 8.887 s first-use test began with a dependency-free interpreter, installed real dependencies through the launcher, reused its machine cache, and left a read-only toolkit with spaces unchanged.

Claude marketplace installation and Codex/Hermes native installation and discovery passed in isolated runtime homes using actual installers and local source transport. Claude discovered 11 entrypoints; Codex and Hermes discovered the router. Hermes required its normal interactive trust review, which was accepted for the inspected fixture without `--force`. These tests did not replace runtime binaries, invoke a new model turn through each newly installed copy, or verify GitHub installation of unpublished changes.

An explicit Sonnet probe unexpectedly ran `glm-5.3` through another provider and was rejected as Sonnet evidence. Grok 4.7 was not run. The first adoption-lifecycle prompt error and one unsupported payload-file attempt are retained in private traces; corrected runs used the supported interface.

Still pending or not live-verified: concurrent remote-write races, Redis expiration and reacquisition races, queue concurrency races and long-running TTL behavior, every third-party integration, hosted function deployment, prompt optimization, and OAuth. Their complete release matrix remains a future gate. These core checks do not establish those capabilities' live success.

Final cleanup confirms the owned Cloud test workflow is inactive with its definition retained, and both exact local n8n containers are stopped. The owned Redis fixture was stopped after its independent checks. Upstash exact-key cleanup passed. Volumes and private fixtures remain local. Test secrets stay in private temporary files. Local owner and API provisioning used installed-version editor REST endpoints; it is test infrastructure, not a public-API onboarding guarantee.

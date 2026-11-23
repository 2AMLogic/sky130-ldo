# iq-base request netlists: stored objects, not committed bytes

The six `.spice` request netlists this leg submitted are **byte-identical** to
objects already in the artifact store from the 2026-11-10 production records
run (manifest `manifests/artifacts/iq-20261110-223334-f66373a0.manifest.json`),
because the production DUT and the `sim/iq` testbench are unchanged since that
run — the pairing contract's pinned base. `check_artifact_manifests.py`
(issue #436) forbids the same bytes living in git AND the store, so the decks
are kept in the store only; the sha256s below let any reader re-derive the
identity:

| request | sha256 (== store object `sim/iq/klt-request-netlists/20261110-223334-f66373a0.<req>.spice`) |
|---|---|
| v2.97-tran1 | `37dea6447da3c6b9b0b3519408463f1da1ea7ef1ca6143d80731d01887d87db9` |
| v2.97-tran2 | `62fb160a76bf6199f5f842f4fffe446e9aaa8daeb41b94ab5c9142476e0b9f17` |
| v3.30-tran1 | `9b6580c321766c6d56e9d78cc7a5cc26e9d53cc7a4e222a6c50b57ad4706adda` |
| v3.30-tran2 | `387bba9c07ea5027a8685f83993783fef14f7e918306c8f08cab7c64f282c127` |
| v3.63-tran1 | `b52deb147abbec66db4f32341b3dd87c1264d488ab0c1e517dadbcba1428feb7` |
| v3.63-tran2 | `bb3a316306cd8e9bbb94002a873c90c3efa512c65538ae090913e97bd8a3de1b` |

This byte-identity is itself evidence: the production leg of this campaign
ran the exact decks the graded 2026-11-10 records run submitted. The request
`.json` files beside this README are this campaign's own (they differ from the
stored ones); the candidate leg's netlists (`runs/iq-cand/klt-requests/`)
carry the `apply_candidate(raw, 2)` overlay and are committed here.

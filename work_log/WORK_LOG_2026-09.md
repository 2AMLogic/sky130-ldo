# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

### 2026-09-23

- **Issue #136** (closed): 2am: reuse rule 9 — decide and record the sky130-bandgap consumption edge (no in-tree reference exists; VREF is an external port)
- **Issue #123** (closed): 2am: reuse rule 9 — in-tree error amplifier (symmetric OTA) duplicates sibling canary sky130-opamp — add reuse.lock.json in_tree entry (evaluate), then adopt or record
- **Issue #122** (closed): T1 item 7: the klt pex leg errors on all 135 corners — item 7 accepts no other evidence kind
- **Issue #121** (closed): The Iq spec row is unratified ('no number set') yet graded FAIL — ratify it or remove it from the table
- **Issue #117** (closed): PSRR fails 0/45 corners at every ratified condition
- **Issue #115** (closed): Stability: PM/GM margins met at only 7/45 corners — likely upstream of the transient and regulation misses
- **PR #144**: docs: record no-lock-entry decision for the sky130-bandgap reuse edge (DR-012)
- **PR #143**: sim(pex): re-check the disclosed klt gaps upstream, pin main@040f3406, record 108/135 (#122)
- **PR #141**: sim(psrr-dc): measure both ratified load points; 50 mA/100 kHz also fails
- **PR #137**: docs: record the error amplifier as kept in-tree vs sky130-opamp (DR-010 + reuse.lock.json)
- **PR #134**: spec: ratify the Iq row at < 30 µA via DR-008
- **PR #130**: docs(design): stability binding mechanism, feedforward-zero screen (verified-negative), coupling-thesis test (#115)

### 2026-09-19

- **Issue #58** (closed): Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)

### 2026-09-18

- **Issue #1** (closed): Ratify the target spec
- **PR #50**: docs(spec): draft DR-006 spec ratification — ratify DR-002/003/004/005

### 2026-09-16

- **Issue #109** (closed): merge-pr.sh silently fails on every PR without a prior champion:hold-state marker (pipefail bug)

### 2026-09-15

- **Issue #107** (closed): Two-stage/cascoded amplifier redesign to close PSRR and light-load stability (per DR-007)
- **Issue #70** (closed): PSRR fails everywhere and light-load stability shortfall is pervasive: bias-generator/compensation redesign needed
- **Issue #60** (closed): LDO fails its own DRAFT PVT-corner spec: Output, Dropout, Load-transient, PSRR and Stability all FAIL (T1 re-read #58, items 5+6)
- **PR #111**: docs(design): document verified-negative cascode screening for PSRR/stability
- **PR #110**: docs(design): close out #60, root-cause/decomposition complete
- **PR #108**: docs(design): document DR-007 outcome for #70, spin off #107
- **PR #106**: docs(spec): add DR-007 recommending PSRR/Stability rows be superseded

### 2026-09-10

- **Issue #104** (closed): LDO: run the full 45-point PVT matrix for the line-regulation, load-regulation and Iq testbenches (issue #64's three benches, mirroring #74)
- **PR #105**: sim: run the full 45-point PVT matrix for line-regulation, load-regulation and Iq (#104)

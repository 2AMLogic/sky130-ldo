# Work Log

Chronological record of merged pull requests and closed issues. Maintained by the Loom Guide role.

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)

### 2026-11-26

- **Issue #821** (closed): compare_dropout_paired.py discards the remote's own reported dropout.dropout_v
- **PR #822**: fix: cross-check the fleet-reported dropout_v instead of overwriting it
- **Issue #818** (closed): Reuse the batch step validator in compare_dropout_paired.py
- **PR #820**: fix: validate dropout remote readings through the shared step validator
- **Issue #812** (closed): Resync Loom so large private defaults no longer abort create-pr.sh and create-issue.sh
- **PR #816**: chore(loom): resync installed Loom to v0.20.37
- **Issue #813** (closed): Reuse the batch measurement validator so startup cannot pass an errored peak-voltage reading
- **PR #817**: fix: grade startup batch card readings through the shared step validator
- **Issue #795** (closed): run_hysteresis records drop the worker PDK stamp the #791 guard now checks
- **PR #815**: fix: keep the executed worker PDK stamp in thermal staircase records
- **Issue #808** (closed): Remove the second corner lookup that loses chained batch diagnostics
- **PR #811**: fix: keep chained batch corner diagnostics on the validated pairing
- **Issue #791** (closed): Batch-mode PDK provenance: the pinned-PDK guard and the record's PDK line are blind to the fleet worker's own stamp
- **PR #794**: fix: verify the executed worker PDK before publishing simulation records
- **Issue #804** (closed): Remove obsolete MOS model-substitution warning from generated PEX decks
- **PR #806**: fix: replace obsolete 01v8 substitution note in PEX deck generator

### 2026-11-25

- **PR #735**: docs(spec): reconcile DR-008 status text with its ratification path
- **Issue #802** (closed): Use the shared bounds grader for the window-grid campaign recheck
- **PR #803**: fix: honor strict bounds in window-grid campaign verdicts
- **Issue #799** (closed): Use the shared thermal trip threshold in the batch staircase
- **PR #800**: refactor: import the shared trip predicate in the batch staircase
- **Issue #797** (closed): Use the batch endpoint validator in paired line- and load-regulation comparisons
- **PR #801**: fix: validate fleet endpoint measurements in paired regulation reports
- **PR #790**: feat: publish graded 45-corner psrr-dc fleet campaign with paired local/fleet check
- **PR #793**: docs: clarify batch support for PSRR and loop-gain campaigns
- **Issue #792** (closed): psrr-dc issue-786 diagnostics README cites a `models_lib_comparison: match` verdict the report records as `null`
- **Issue #788** (closed): Stale 'batch refuses psrr-dc' claims in sim/README.md and bias-retopo-pvt.py after #786
- **PR #787**: feat: admit the graded psrr-dc campaign to the batch backend
- **Issue #754** (closed): Sim: strictly-admitted batch adapter for the loop-gain bench (ac_leg_grid), then re-run (split from #554)

### 2026-11-24

- **PR #783**: refactor: extract power-rail sizing and klayout router out of gen-ldo-blocks
- **PR #782**: signoff: gate item 9's PDK/tools pins against sim/pdk.json
- **PR #779**: test: pin the unsupported-suffix refusal on _num directly in the es/lg suites
- **PR #776**: fix: paired comparators importable under python3 -I
- **PR #774**: refactor: share one SPICE-number parser across batch adapters via _meas_expr.parse_number
- **PR #773**: refactor(sim): share corner-part collection and assembly between endpoint and loop-gain batch adapters
- **PR #772**: fix: share one fleet engine-version rule across the paired comparators
- **PR #766**: sim: loop-gain batch adapter live verification — paired equivalence and 45-corner fleet record
- **PR #765**: sim: enable-shutdown 45-corner batch record, paired comparison and alter carry-over
- **PR #764**: docs: write the #702 rev2 adoption review — recommendation revise, disposition pending (#763)
- **PR #762**: sim: add PDK-free paired loop-gain comparator
- **PR #760**: sim: admit enable-shutdown to the batch backend via a pinned four-step adapter
- **PR #726**: sim: share the cold-start/EN re-enable schedule via _record_common
- **Issue #781** (closed): Split layout/bin/gen-ldo-blocks.py into power-rail sizing and router modules
- **Issue #780** (closed): T1 item 9's PDK pin evidence went stale when sim/pdk.json re-pinned, and no check notices
- **Issue #778** (closed): Two of the three #769 unsupported-suffix refusal cases are insensitive to the suffix table
- **Issue #775** (closed): chore: gitignore daemon account-ranking state so check-main-clean.sh stops flagging it
- **Issue #771** (closed): Paired-comparison reproduce commands fail on Python 3.11+: python3 -I drops the script directory
- **Issue #770** (closed): Share corner provenance assembly between endpoint and loop-gain batch adapters
- **Issue #769** (closed): Consolidate duplicate SPICE-number parsers in batch translators into _meas_expr
- **Issue #768** (closed): Share fleet engine-version checks across paired simulation comparators
- **Issue #763** (closed): Rev2 dropout candidate: write the adoption review and recommendation (split from #702)
- **Issue #757** (closed): Sim: loop-gain batch adapter live verification — paired single-corner comparison and full 45-corner re-run (follow-up to #754)
- **Issue #755** (closed): Sim: strictly-admitted batch adapter for the enable-shutdown bench, then re-run (split from #554)
- **Issue #715** (closed): Share the cold-start and re-enable temperature schedule across the three thermal paths
- **Issue #702** (closed): Production-adoption review: low-headroom amplifier/clamp dropout candidate (rev2) — loop gain, PM/GM, load transient, PSRR, start-up, MC accuracy

### 2026-11-23

- **PR #761**: layout: drop unused flow_require_klt hint arg and fix floorplan pin wording
- **PR #758**: sim: admit loop-gain's AC leg grid to the batch backend (ESR-group requests)
- **PR #756**: layout: fold ERC and cap-rail flows onto the single klt pin
- **PR #753**: sim: paired rev2 qualification of startup, line/load regulation and MC output accuracy
- **PR #752**: test: cover enp-soft-release-709 deck-delta patcher
- **PR #749**: sim: measure and reject the 100us EA_OUT/PB soft-release wake shaping (#709)
- **PR #748**: docs(ci): replace the ci.yml check-inventory header with a check:ci pointer plus PDK gating rationale
- **PR #747**: refactor: drop uncalled load_results() helper from probe scaffolding
- **Issue #759** (closed): layout/: two live references still name the deleted per-flow requirements files, and flow_require_klt's hint arg is now unused
- **Issue #751** (closed): sim/tests: cover enp-soft-release-709.py's deck-delta patcher (convention gap)
- **Issue #709** (closed): Qualify R_CZ L=180 for startup charge reduction and land a verified compensation change
- **Issue #705** (closed): Qualify rev2 start-up, line/load regulation and mismatch accuracy
- **Issue #595** (closed): Remove load_results() from sim/bin/_probe_common.py: the one advertised probe helper with no caller
- **Issue #591** (closed): Shorten the CI workflow header to a check:ci pointer and the PDK rationale
- **Issue #576** (closed): Collapse layout/'s three klt pins into one: the main pin now descends from both the ERC and cap-rail pins
- **Issue #565** (closed): item-5 envelopes cannot wrap the batch-fleet records from PR #561 (no .json record emitted)
- **PR #710**: docs: attribute the startup enable-edge drawdown to the C_COMP charge packet; screen R_CZ
- **Issue #693** (closed): Startup: attribute the enable-edge charge packet behind the 0.016-66 uV pre-ramp drawdown and remove its cause
- **PR #714**: sim: record R_CZ L=180 loop-gain rejection; compensation adoption stays open (#709)
- **PR #711**: sim: add paired rev2-vs-production Iq, clamp and thermal-hysteresis campaign (i706)
- **Issue #706** (closed): Characterize rev2 quiescent current, clamp knee and thermal hysteresis

### 2026-11-22

- **PR #743**: refactor(sim): consolidate pinned batch-adapter shape/netlist gates and dedupe #177 test scaffolding
- **PR #742**: sim(current-limit): seed leg 2's dc sweep and run it first — 45/45 PASS under the #171 gate (#647)
- **PR #739**: docs: disclose rev2 dc extraction bias and correct report citations in issue-704 diagnostic
- **PR #648**: sim(current-limit): batch adapter for the three chained legs; 45-corner fleet re-run supersedes the pre-gate record (#177)
- **Issue #741** (closed): Consolidate pinned batch-adapter shape/netlist gates and deduplicate #177 adapter test scaffolding
- **Issue #738** (closed): Report-precision follow-ups on the #704 dynamic-response diagnostic (DC-gain extraction disclosure, .ic citation, PSRR invalid list, docstring)
- **Issue #647** (closed): Current limit: leg 2's dc vforce sweep trips the solver-diagnostic gate at 4 corners, all at Vin_max (3.63 V)
- **Issue #177** (closed): Seed sim/current-limit's leg-1 operating point to conform to the initial-condition contract
- **PR #737**: refactor: share the measurement-check, ramp-check and batch corner-result builders
- **PR #734**: sim: add issue-704 paired loop/load-step/PSRR evidence for rev2
- **PR #733**: docs(sim): move Iq testbench header to fresh-ratification wording
- **PR #732**: refactor: fetch store-held item-5 record bytes once per artifact
- **PR #731**: fix: refuse JSON error envelopes in fleet submit, drop rcz-shelf-691 duplicate pool
- **PR #727**: fix: require exactly one remote response in the dropout paired loader
- **PR #725**: test: stage only experiment inputs in BatchHarness scratch fixture
- **PR #724**: ci: extend the append-only guard to sim diagnostics run directories
- **PR #681**: Clarify DR-012’s proposed status and fresh ratification requirement
- **Issue #736** (closed): Share measurement-check, ramp-check, and batch corner-result builders across corner-run.py and _batch_backend.py
- **Issue #729** (closed): Stop double-fetching store-held records and drop redundant hashing in signoff/make_item5_envelope.py
- **Issue #728** (closed): Reject error envelopes in _fleet_campaign.submit() and drop rcz-shelf-691.py's duplicate submit loop
- **Issue #720** (closed): Remove multi-response merging from the single-request dropout comparison
- **Issue #719** (closed): Stage only experiment inputs in BatchHarness to avoid copying 392 MiB of dropout diagnostics
- **Issue #716** (closed): Extend the sim append-only CI check to archived diagnostic runs
- **Issue #704** (closed): Measure rev2 loop stability, load-step response and supply rejection

### 2026-11-21

- **PR #722**: signoff: cover pdk-smoke.yml in the T1 item 10 hygiene inventory
- **PR #703**: sim(#692): paired 45-point PVT dropout campaign — rev2 holds < 300 mV at every corner (ADOPT-REVIEW)
- **Issue #717** (closed): signoff: item 10 hygiene inventory no longer covers the CI smoke steps after the pdk-smoke.yml split
- **Issue #692** (closed): Dropout: run the paired 45-point PVT campaign for the #357 rev1 amplifier/clamp candidate (0.163 V at tt/27C; ratified row < 300 mV)
- **PR #713**: ci: stop re-running CI on PR label writes; split smoke into pdk-smoke.yml
- **Issue #707** (closed): ci.yml triggers a full CI run on every label change (pull_request: types includes 'labeled')
- **PR #712**: fix: derive the rcz-shelf report's possible-request inventory from the driver's builders
- **Issue #700** (closed): Diagnostic record states 118 dry-run-validated batch requests; the #691 screen now generates 122
- **PR #701**: refactor: share the engine-log check across the batch response handlers
- **PR #695**: feat(sim): screen a frequency-dependent compensation resistor on the batch fleet
- **Issue #699** (closed): Share the engine-log check across the three batch response handlers
- **Issue #697** (closed): Correct the klayout-tools#5894 cross-confirmation comment: it swaps which graph_too_large net hit which cap

### 2026-11-20

- **PR #696**: pex: measure per-net resistance-graph fallback reasons; map rails' graph_too_large to klayout-tools#6964 (item 7)
- **Issue #690** (closed): Item 7: re-run the resistance-graph recheck with per-net fallback reasons and file the upstream gap that actually blocks VIN/VOUT
- **PR #686**: docs(sim): align iq manifest claim with the #301 fresh-ratification ruling
- **Issue #683** (closed): docs(sim): reconcile sim/iq/experiment.json's DR-009 ratifying-act claim with the #301 ruling
- **PR #682**: docs: move live DR-009 citations to the fresh-ratification wording (split from #681)

### 2026-11-19

- **PR #573**: docs(spec): reconcile DR-009's ratifying-act wording with the #301 ruling
- **PR #630**: docs: align DR-009 status wording with the #301 ruling across CLAUDE.md and target spec
- **Issue #624** (closed): CLAUDE.md:35 still claims DR-009 'ratifies on its own PR merge' — the same stale claim #607 removed from README
- **Issue #609** (closed): docs: four prose copies still instruct a raw headless `xschem -n -q -x -s` where `klt netlist` is the decided path

### 2026-11-18

- **PR #677**: test: pin the shared store-manifest read contract in layout/tests
- **Issue #675** (closed): Add layout/tests/test_store_manifest.py for the shared store-manifest read contract
- **PR #673**: refactor: one shared artifact-store manifest read/fetch helper
- **Issue #671** (closed): Consolidate duplicated artifact-store manifest read/fetch helpers
- **PR #670**: ci: report the spec-table gate on merge_group commits (merge queue step)
- **Issue #668** (closed): Merge queue: add the merge_group trigger and adapt the PR-metadata gates
- **PR #667**: refactor: consolidate the two batch adapters' measurement-expression evaluators
- **Issue #666** (closed): Consolidate duplicate measurement-expression evaluators in sim batch adapters
- **Issue #663** (closed): WORK_PLAN.md 'In Progress' still lists closed #336 (no loom:building label)
- **PR #661**: docs(signoff): qualify the gate's "re-hashes every artifact" claims in --help, README and ci.yml
- **Issue #659** (closed): verify-pins "--help", signoff/README.md and ci.yml still claim the gate "re-hashes every artifact" (post-#658 residual)
- **PR #658**: docs(signoff): scope check.sh re-hash claim to committed artifacts; seed verify() counts keys
- **Issue #657** (closed): signoff/check.sh header still claims the gate "re-hashes every artifact" (post-#654 residual)
- **PR #656**: fix(signoff): report store-manifest-verified pins as such, not as re-hashed
- **Issue #654** (closed): verify-pins: a store-manifest-verified pin is reported as if its bytes were re-hashed
- **PR #652**: sim(startup): mint the 12-leg ESR-grid x 45-PVT campaign on the batch fleet
- **Issue #336** (closed): Startup: extend cold-enable coverage to the ratified ESR boundaries
- **PR #651**: evidence: pex-post-layout batch legs run as ceiling-split shards (#623)
- **Issue #623** (closed): pex-post-layout batch runs: serial job-ceiling estimate can exceed the fleet's 3600 s max_job_seconds (shard via request.remote.hosts)

### 2026-11-17

- **PR #643**: ci: declare repo-local run-pdk-smoke label in labels.yml
- **Issue #642** (closed): CI: documented 'run-pdk-smoke' PR opt-in label does not exist
- **PR #637**: chore(loom): resync installed Loom to v0.19.1306

### 2026-11-16

- **PR #632**: fix(sim): make the bias grid's unusable-point guard a real disjunction on status
- **Issue #625** (closed): bias-retopo-grid.py's unusable-point guard: the status test is dead code (operator precedence), so a non-pass corner is graded
- **PR #627**: chore(loom): resync installed Loom to v0.19.1302
- **PR #626**: feat: pin README's ratified spec table with a DR-gated lock guard
- **Issue #618** (closed): Port gf180-ldo's spec-table guard so README's ratified mirror cannot drift again
- **PR #621**: fix(signoff): check attested hygiene exactly against the tree, not the branch diff
- **Issue #588** (closed): check-attested-hygiene.sh: detect stale re-mints, not just absent ones (+ a --self-test)
- **PR #617**: docs: point netlist prose at klt netlist instead of raw xschem
- **PR #616**: evidence: standalone 45-corner pex-post-layout schematic leg completes on the batch fleet (#327)
- **Issue #327** (closed): sim(pex): run the 45-corner schematic-side PEX leg once the batch fleet runner accepts klt 0.7.x clients (split from #277)
- **PR #628**: sim/pex-post-layout: shard batch jobs via job_ceiling_check split
- **PR #622**: refactor: collapse the triplicated PM/GM spec thresholds onto _fleet_campaign.py
- **Issue #596** (closed): Collapse the triplicated PM/GM spec thresholds in sim/bin onto _fleet_campaign.py
- **PR #593**: refactor(sim): build the bias grid's requests and submits on _fleet_campaign
- **Issue #586** (closed): Fold sim/bin/bias-retopo-grid.py onto _fleet_campaign.py: the one batch-fleet driver #574's dedup missed

### 2026-11-15

- **PR #620**: refactor(signoff): collapse duplicated item-5 envelope literal into one _envelope() helper
- **Issue #606** (closed): Collapse the duplicated 51-line item-5 envelope literal in signoff/make_item5_envelope.py
- **PR #619**: docs: make README's ratified spec-table mirror faithful to the gate
- **Issue #607** (closed): README.md's 16-row spec table is a second copy of the ratified gate and has drifted in four rows
- **PR #614**: refactor(sim): derive hysteresis observation instants from batch_thermal_staircase
- **Issue #613** (closed): Thermal observation instants (T_COLD..T_REEN) are duplicated between run_hysteresis.py and batch_thermal_staircase.py
- **PR #603**: refactor(sim): extract one shared batch endpoint-adapter test contract
- **Issue #587** (closed): Deduplicate the batch adapter test scaffolding: 113 identical lines across three test files
- **PR #602**: refactor(sim): use _record_common.spiceinit_sha256 in corner-run.py
- **Issue #598** (closed): Remove corner-run.py's spiceinit_digest: byte-identical duplicate of _record_common.spiceinit_sha256
- **PR #600**: docs(signoff): correct "What would move the needle" for items 11 and 1/2/9/10
- **Issue #582** (closed): README and signoff/README still say T1 5/11; the verdict of record says 9/11
- **PR #584**: feat(signoff): catch item-10 hygiene drift and T1 headline staleness in check:ci
- **Issue #579** (closed): Docs PRs touching README.md always fail signoff stage 1b (item 10 attestation drift)
- **PR #612**: sim: paired dropout local/fleet baseline check passes (equivalent, ngspice-47 both sides)
- **Issue #375** (closed): Dropout: run the paired local/remote baseline check for the cold-start batch adapter once the fleet preflight accepts
- **PR #611**: refactor(sim): share the thermal staircase Runner and deck frame in _record_common
- **Issue #597** (closed): Collapse the duplicated thermal Runner and deck frame onto _record_common.py's #297 block
- **PR #610**: sim: remove six dead module-level constants in sim/bin
- **Issue #605** (closed): Remove six dead module-level constants in sim/bin: the residue pyflakes cannot see
- **PR #608**: diagnostics: re-measure the pex resistance-graph blocker on the regenerated core
- **Issue #583** (closed): Item 7: re-measure the extraction blocker on the regenerated core (extraction only, no corner grid)
- **PR #594**: refactor(sim): extract the klt sim batch backend into _batch_backend.py
- **Issue #580** (closed): Split sim/bin/corner-run.py: extract the 845-line klt sim batch backend into an importable sibling module

### 2026-11-14

- **PR #601**: refactor(layout): one shared preamble for the five run-*-flow.sh drivers
- **Issue #599** (closed): layout/bin: the five run-*-flow.sh drivers duplicate their preamble, and two copies have drifted
- **PR #590**: refactor: drop never-called owner_of and grade_ac helpers
- **Issue #585** (closed): Remove two never-called helpers: owner_of in diagnose-official-drc.py and grade_ac in rcz-adaptive-370.py
- **PR #592**: refactor: one shared file-SHA-256 helper and one strict digest normalizer
- **Issue #589** (closed): Consolidate five file-SHA-256 helpers and two divergent digest normalizers into one contract
- **PR #581**: docs: roadmap as of 2026-11-13

### 2026-11-13

- **PR #575**: refactor(sim): extract the batch-fleet campaign core into _fleet_campaign.py
- **Issue #574** (closed): Deduplicate the batch-fleet driver core copied across bias-retopo-pvt / rcz-fleet-confirm / rcz-adaptive-370
- **Issue #267** (closed): layout: fix locally-routed official-DRC families (via.1a_b, m2.5, via2.5, nwell.9) found by #260

### 2026-11-12

- **PR #570**: test: share FakeSingleStepKlt across batch-adapter tests
- **Issue #568** (closed): Dedupe FakeKlt subclasses in batch-adapter tests (~120 LOC of copy-paste)
- **PR #566**: fix: repo-relative GDS path for layout-flow DRC and re-pin signoff item 3
- **Issue #564** (closed): signoff/README: item 3/4/11 narrative sections still describe pre-#553 records
- **PR #563**: sim: mint PSRR C_eff x ESR reduced-sweep evidence record
- **PR #559**: feat(signoff): wrap thermal hysteresis record as the item-5 envelope
- **Issue #558** (closed): signoff: item-5 Thermal envelope still wraps legacy record; Thermal row now grades the hysteresis record
- **PR #557**: layout: regenerate core from integrated-comparator netlist and re-pin signoff items 3, 4, 11
- **Issue #553** (closed): Layout evidence: regenerate and re-run DRC/LVS/ERC/area for the integrated comparator netlist (split from #548)
- **PR #556**: sim: re-run mc-output-accuracy on batch after comparator change; mark screening benches stale-by-design
- **Issue #552** (closed): Screening benches: decide and re-run those stale after the integrated comparator (split from #548)
- **PR #555**: feat(report): grade Thermal row from the 15-corner integrated-comparator hysteresis record
- **Issue #551** (closed): Thermal row: re-grade against the integrated comparator record (split from #548)
- **PR #549**: sim(thermal): dependent round at all 15 corners, ff brackets planned on the lowered grid
- **Issue #231** (closed): Thermal hysteresis: qualify the integrated comparator across PVT and refresh downstream evidence
- **PR #545**: feat: add cold-start, EN re-enable and amplitude points to the thermal batch route
- **Issue #541** (closed): sim(thermal): cold-start, EN-reenable and disturbance-amplitude runs at 15 corners (not on batch route)
- **PR #542**: sim(thermal): complete 15-corner staircase with ff bound lowered to 180 C
- **PR #539**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-10

- **PR #537**: sim: baseline Iq attribution of DR-013 exceedances (7 pre-existing, 3 caused)
- **Issue #536** (closed): DR-013: baseline Iq run on the 63-point matrix to attribute the candidate's 10 Iq failures (#467)
- **PR #534**: refactor: share verdict and report logic between paired comparison scripts
- **PR #531**: refactor: share deck-line filter and meas-card loop across sim batch adapters
- **Issue #530** (closed): Dedupe parse_deck across sim batch scripts and drop unused re-exports
- **Issue #529** (closed): Consolidate duplicated compare()/main() in the paired line/load-regulation comparison scripts
- **Issue #446** (closed): Dedupe batch_iq/batch_load_regulation parse_deck and drop unused re-exports
- **PR #500**: docs(spec): DR-012 stays proposed; point to fresh-ratification path

### 2026-11-07

- **PR #523**: fix(sim): use shared is_finite_number in psrr-cap-sweep-run
- **Issue #522** (closed): Dedupe: fold six copies of the finite-number predicate into _record_common
- **PR #518**: Bump Repo Skills 0.25.1 -> 0.25.10

### 2026-11-06

- **PR #505**: sim(load-regulation): record paired local/fleet check and add comparator
- **PR #504**: fix(measurements): select store-only sim records in latest_sim_record
- **Issue #381** (closed): Sim: admit load-regulation cold-start endpoints to the batch backend

### 2026-11-05

- **PR #512**: sim(thermal): batch route for the hysteresis staircase
- **PR #510**: sim(loop-gain): fleet screen of a sub-mA load-sensed adaptive R_CZ
- **PR #509**: signoff: re-cite item 3 DRC to the clean 3e7f504b envelope
- **PR #507**: sim(loop-gain): fleet-confirm #365 baseline and R_CZ x16 AC pairs
- **PR #506**: signoff: grade T1 items 1, 2, 9, 10 from klt --attest envelopes (klt 0.9.0)
- **PR #502**: sim(iq): mint superseding 45-corner record on batch backend (40/45 PASS)
- **Issue #511** (closed): sim: batch backend for corner-run.py so the thermal-staircase PVT qualification can run on the Spot fleet
- **Issue #508** (closed): Follow-on from PR #506: align the GDS cited by signoff items 2, 3, 4 and 11
- **Issue #423** (closed): T1 items 1, 2, 9, 10: bump the signoff grading pin and attest with artifact-anchored envelopes (klt signoff --attest)
- **Issue #370** (closed): Stability: confirm zero-load lever on fleet and screen sub-mA adaptive resistance
- **Issue #213** (closed): sim(iq): mint the 45-corner record under #173's seeded deck + #133's regulation gate

### 2026-11-04

- **PR #501**: sim: record paired line-regulation local/fleet check (engine mismatch, not equivalent)
- **PR #499**: refactor: drop dead sha256_file and dedupe _sha256_of
- **PR #498**: refactor(cap-study): remove caller-less rel_path, mim_cap_f, vpp_name_dims
- **PR #496**: docs(sim): simulate DR-013 alternative (a) mirror-ratio candidate
- **PR #494**: refactor(sim): share one klt sim runner across record scripts
- **PR #493**: docs(spec): amend DR-013/DR-010 status and provenance, qualify Iq row's DR-009 cite
- **PR #490**: docs(spec): DR-011 stays proposed; point to fresh-ratification path
- **PR #486**: docs(spec): DR-010 stays proposed; point to fresh-ratification path
- **PR #482**: docs(spec): add ll/hh Iq corners and DR-0033 departure to DR-013 record
- **Issue #497** (closed): Remove dead sha256_file from _official_drc.py and dedupe _sha256_of
- **Issue #495** (closed): Remove dead helpers from _cap_study.py: rel_path, mim_cap_f, vpp_name_dims
- **Issue #492** (closed): DR-013 alternative (a): simulate smaller R_BIAS plus mirror ratio
- **Issue #491** (closed): Consolidate five duplicated klt sim subprocess wrappers in sim/bin into _record_common
- **Issue #489** (closed): DR-010/DR-013 record hygiene from the #486/#482 key reviews
- **Issue #478** (closed): DR-013 follow-ups: ll/hh resistor-skew corners missing from the full-loop sweep
- **Issue #384** (closed): Line regulation: complete the unperformed numerical-equivalence handoff

### 2026-11-01

- **PR #483**: feat: PVT PSRR/stability grid and minted Iq record for the DR-013 R_BIAS candidate
- **PR #481**: refactor: share one two-endpoint deck parser between iq and load-regulation adapters
- **Issue #479** (closed): Consolidate duplicated parse_deck in batch_iq and batch_load_regulation
- **Issue #475** (closed): Remove superseded ldo-area-budget.py (#246): replaced by 4cap budget (#459), helpers duplicated
- **PR #470**: docs(spec): propose DR-013 bias re-topology (straight res_xhigh_po R_BIAS) with area and PVT evidence
- **PR #474**: chore: remove superseded #246 area-budget generator
- **Issue #472** (closed): Remove superseded ldo-area-budget.py (#246 generator); keep study record

### 2026-10-31

- **PR #473**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-28

- **PR #463**: layout(area-study): four-capacitor core area budget for current schematic
- **PR #462**: docs(signoff): describe area declared gap as a failing lower-bound row
- **Issue #460** (closed): signoff: state item 5 area is a failing row, not an unexpressible gap (part of #458)
- **Issue #459** (closed): T1 item 5 area: budget with all four capacitors, go figure or draft floor DR (part of #458)
- **PR #457**: refactor(sim): remove unused apply_cap_point from psrr cap sweep
- **Issue #455** (closed): Remove apply_cap_point: unused per-process netlist rewriter in psrr_cap_sweep.py

### 2026-10-27

- **PR #454**: refactor(tests): share one hyphenated-script loader per sim/layout tests tree
- **Issue #453** (closed): Consolidate duplicated hyphenated-script module loader across ~28 test modules
- **PR #450**: feat(signoff): wrap PVT records into klt sim envelopes for T1 item 5
- **Issue #449** (closed): T1 item 5 (Full corner verification): emit klt sim envelopes for every ratified row so failures are graded, not no_evidence

### 2026-10-23

- **PR #444**: test: remove frozen pre-extraction copies and source-grep tests
- **Issue #443** (closed): Remove frozen pre-extraction legacy copies from test_render_verdicts.py
- **PR #438**: feat(sim): store new run evidence in the artifact store, commit only manifest and summary
- **Issue #436** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)
- **PR #439**: fix(measurements): mint fresh core-area record against current routed GDS
- **Issue #437** (closed): Area row: mint a fresh core-area record against the current LATEST routed GDS and regenerate characterization.md

### 2026-10-22

- **PR #434**: feat(pex): bump klt pin and run klt pex with --resistance-graph
- **Issue #162** (closed): sim/pex-post-layout: full-load rows stay non-physical after #154 — the blocker is klt's lumped-R model, not this repo's routing

### 2026-10-21

- **PR #431**: Bump Repo Skills 0.24.3 -> 0.24.7

### 2026-10-19

- **PR #427**: docs(spec): DR-009 stays proposed; point to fresh-ratification path
- **PR #425**: docs(spec): DR-008 stays proposed; point to fresh-ratification path

### 2026-10-17

- **PR #418**: layout(folded-res-qual): n=4000 matrix, sigma-ratio SE reporting, BLOCKED batch record
- **PR #414**: refactor(cap-study): remove caller-less helpers from _cap_study.py
- **Issue #413** (closed): Remove dead helpers from layout/cap-study/_cap_study.py (~55 LOC, zero callers)
- **PR #420**: layout: use fail-closed parse_lyrdb in cap-rail and folded-res record scripts
- **Issue #419** (closed): Consolidate private .lyrdb readers onto fail-closed parse_lyrdb (~25 LOC)
- **PR #415**: layout: complete folded-resistor PVT/mismatch record; R_FB qualified to N=6, R_BIAS none
- **PR #412**: refactor(sim): reuse line-regulation endpoint helpers in load-regulation adapter
- **Issue #411** (closed): Dedupe endpoint_source_lines/endpoint_body and two-point parse_deck across sim/bin batch adapters
- **Issue #263** (closed): Qualify folded resistor electrical equivalence across process, temperature and mismatch
- **PR #409**: refactor(sim): share netlist gate and source replacement across batch adapters
- **Issue #408** (closed): Consolidate duplicated helpers across the sim batch endpoint adapters
- **PR #407**: layout: record 2026-10-17 folded-res PVT attempt; MC shards returned no report (#263)

### 2026-10-16

- **PR #272**: layout: #263 resume attempts, raw deterministic reports, MC still blocked
- **PR #275**: layout: fix via.1a_b, m2.5, via2.5, nwell.9 official-DRC families (#267)
- **PR #395**: Bump Repo Skills 0.24.1 -> 0.24.3
- **PR #399**: study: cap-study probe finds one settled state at ff/27C/2.97V/50mA
- **Issue #398** (closed): study: re-run ff/27C/2.97V/50mA op point; settled state differs between cap-study records
- **PR #397**: study: complete capacitor op-point and C(V) grids on the batch fleet
- **PR #396**: sim: bounded retry for batch fleet-cap refusal in corner-run
- **Issue #341** (closed): Area: complete the #319 capacitor study's operating-point and varactor C(V) grids once the batch runner matches the client

### 2026-10-15

- **PR #393**: sim: extend startup to a 12-leg C_out x load x ESR cold-enable grid
- **PR #392**: study: partial capacitor-study record, 105/126 op points on batch fleet
- **PR #387**: Bump Repo Skills 0.19.5 -> 0.24.1

### 2026-10-14

- **PR #386**: sim(iq): batch adapter for the iq endpoints (Part of #213; matrix blocked on fleet runner)

### 2026-10-11

- **PR #383**: sim: opt-in batch adapter for load-regulation cold-start endpoints (#381)
- **PR #380**: Sim: bounded batch adapter for line-regulation cold-start endpoints (#379)
- **PR #378**: sim: grade settled tail extrema alongside regulation endpoint averages (#377)
- **PR #376**: sim: admit dropout-vs-load cold-start crossing to the klt batch backend
- **PR #373**: sim: require in-window pre-step output for every load-transient COUT/ESR leg
- **PR #371**: sim: gate line-regulation endpoints on Output window; strict slope maxima (#369)
- **PR #361**: sim(#357): screen physical low-headroom amplifier + re-referenced clamp dropout candidate
- **PR #368**: Load regulation: gate settled endpoints on the Output window (#364)
- **PR #367**: sim: zero-load phase-dip mechanism and bounded light-load lever screen (#365)
- **Issue #379** (closed): Sim: qualify a bounded batch adapter for the line-regulation cold-start endpoints
- **Issue #377** (closed): Regulation: grade settled tail extrema alongside endpoint averages
- **Issue #374** (closed): Dropout: qualify a bounded fleet adapter for the existing cold-start ramp
- **Issue #372** (closed): Load transient: require an in-window pre-step output for every COUT/ESR leg
- **Issue #369** (closed): Line regulation: gate all settled endpoints and enforce strict slope bounds
- **Issue #357** (closed): Dropout: screen a physical low-headroom amplifier and re-referenced clamp candidate
- **Issue #364** (closed): Load regulation: gate settled endpoints on the ratified output window
- **Issue #365** (closed): Stability: isolate the zero-load phase dip and screen a bounded light-load lever
- **PR #363**: Stability: diagnose missing phase crossings before interpreting gain margin (#360)
- **PR #362**: sim: batch preflight accepts only a completed usable smoke response
- **PR #358**: sim: shared batch-runner preflight probe (#356)
- **PR #355**: sim: shared _probe_common helper for ngspice diagnostic probes
- **PR #354**: test(layout): PDK-free unit coverage for cap-study orchestrator (#351)
- **PR #352**: sim: load-adaptive compensation prototype screening (REVISE) (#349)
- **PR #350**: sim: dropout screening - isolated pass bench + combined ideal-tail/no-clamps probe (#339)
- **PR #348**: docs: finding for #347 (pinned lint handoff), no enforcement change
- **PR #346**: feat(sim): klt batch path for the load-transient COUT/ESR window grid
- **PR #344**: sim: 0 mA phase-margin mitigation screen with Iq accounting (#324)
- **PR #343**: sim/loop-gain: 18-leg boundary grid incl. exact-zero ESR (#338)
- **PR #342**: Area: compare capacitor implementations for the 162 pF budget (study, outcome c) (#319)
- **PR #340**: sim+design: dropout attribution study at tt/27C/3.30V/50mA (#323)
- **PR #337**: sim: explicit bound inclusivity in corner-run grader (#335)
- **Issue #360** (closed): Stability: diagnose missing phase crossings before interpreting gain margin
- **Issue #359** (closed): Batch preflight: reject incomplete or errored smoke responses
- **Issue #356** (closed): Sim: one shared batch-runner preflight probe for the issues blocked on the fleet runner
- **Issue #353** (closed): Sim: share the ngspice diagnostic-probe scaffolding in one helper module
- **Issue #351** (closed): Tests: add PDK-free unit coverage for the cap-study orchestrator (run-cap-study.py)
- **Issue #349** (closed): Stability: prototype load-adaptive compensation and measure sense-path loading
- **Issue #339** (closed): Dropout: screen isolated pass capability and combined amplifier/clamp interventions
- **Issue #347** (closed): Auditor: require pinned Python lint before handing diagnostic scripts to Judge
- **Issue #326** (closed): Load transient: run the COUT/ESR window grid campaign over the 45-point PVT matrix (Phase B of #313)
- **Issue #324** (closed): Stability: evaluate 0 mA phase-margin mitigations against the Iq budget and report numbers for the DR-007 decision
- **Issue #338** (closed): Stability: extend loop-gain coverage to zero ESR and all boundary load combinations
- **Issue #319** (closed): Area: compare capacitor implementations (MiM, vpp, MOS-cap) for the 162 pF compensation/soft-start budget
- **Issue #323** (closed): Dropout @ 50 mA: establish a current-schematic baseline and attribute the limiting mechanism
- **Issue #335** (closed): Simulation grading: represent strict ratified inequalities explicitly

- **PR #333**: docs: archive design/README.md investigation log, fix stale Freshness (#332)
- **PR #331**: layout: refresh current-core area evidence and reconcile floorplan docs (#318)
- **PR #330**: sim: PSRR C_eff x ESR sweep via klt sim analysis_steps (Part of #314; fleet run blocked)
- **PR #329**: spec: defer row status counts to generated report; guard against reintroduction (#325)
- **PR #328**: sim(pex): retain measured swx_nrds diagnosis + xschem 3.4.4 fixture regression (#277)
- **PR #322**: sim: load-transient COUT/ESR window grid, conservative aggregation, coverage disclosure (Phase A of #313)
- **PR #321**: sim: PSRR C_eff x ESR reduced-sweep tooling + selection tests (Phase 1 of #314)
- **Issue #332** (closed): Simplify design/README.md: move ~3000-line investigation log out, fix stale 'entirely DRAFT' Freshness claim
- **Issue #325** (closed): spec: stop hand-copying corner counts into target-spec status prose; lint against reintroduction
- **Issue #318** (closed): layout: refresh current-core area evidence and reconcile stale floorplan documentation
- **Issue #313** (closed): Load transient: qualify the ratified capacitor and ESR window
- **Issue #277** (closed): sim: post-layout PEX schematic-side corners fail with 'Undefined parameter [swx_nrds]'; no PEX evidence for #267 geometry

### 2026-10-10

- **PR #317**: layout: PDK-free verdict tests for cap-rail, folded-res, trivial-cell and official-DRC scripts
- **PR #316**: layout: refresh erc-supply-spec.json; mint ERC record 20261010-225954-95dca45
- **PR #315**: sim/thermal: deduplicate trip-search helpers and add PDK-free tests (#297)
- **PR #312**: sim: atomically reserve evidence record IDs before concurrent runs
- **PR #311**: startup: measure ramp monotonicity per cold-enable leg (#309)
- **PR #308**: PEX: retain batch-mismatch evidence for 45-corner schematic leg (Part of #277)
- **PR #307**: sim: opt-in klt sim batch backend for corner-run.py (smoke-only)
- **PR #305**: measurements: verify DRC freshness against the checked GDS bytes (#304)
- **PR #303**: spec: decision-record status index and CI consistency lint
- **PR #302**: sim: fix PEX schematic-side xschem expr() drift; retain failed-run evidence (#277)
- **PR #300**: sim: PDK-free unit tests for PEX bench generator and record renderer
- **PR #299**: ci: pinned ruff F-class lint gate for tracked Python (#293)
- **PR #295**: ci: pin and gate the ngspice/xschem versions the way the PDK is pinned
- **Issue #306** (closed): layout: PDK-free verdict tests for the cap-rail, folded-resistor and trivial-cell evidence scripts
- **Issue #276** (closed): layout: refresh erc-supply-spec.json so run-ldo-erc-flow.sh pre-flight matches the current layout
- **Issue #297** (closed): sim/thermal: deduplicate the copy-pasted trip-search helpers and add PDK-free tests
- **Issue #310** (closed): sim: atomically reserve evidence record IDs before concurrent runs
- **Issue #309** (closed): startup: measure ramp monotonicity instead of relying on peak and settled floor
- **Issue #298** (closed): sim: add an opt-in klt sim batch backend to corner-run.py for PVT grids
- **Issue #304** (closed): Characterization: verify DRC geometry against the cited input hash
- **Issue #292** (closed): spec: add a decision-record status index and CI consistency lint
- **Issue #296** (closed): sim: PDK-free unit tests for the post-layout PEX bench generator and record renderer
- **Issue #293** (closed): ci: add a pyflakes-class static lint to check:ci (py_compile misses dead imports and unused locals)
- **Issue #291** (closed): ci: pin and gate the ngspice/xschem versions the way the PDK is pinned
- **PR #290**: fix(sim): pdk-smoke fails on xschem 3.4.4 expr() params; retain diagnostics (#288)
- **PR #289**: report: content-based GDS freshness for LVS and dependent PEX
- **PR #286**: docs: split sim/README.md into harness reference plus sim/docs (#284)
- **PR #285**: ci: fail PRs that modify/rename/delete committed sim records (#283)
- **PR #282**: ci: lint every tracked shell script with bash -n
- **PR #281**: layout: PDK-free verdict tests for ERC/LVS/area renderers
- **Issue #288** (closed): Build/runtime failure on main: nightly PDK smoke fails all three corners
- **Issue #287** (closed): Characterization: invalidate LVS and PEX freshness when routed GDS changes
- **Issue #284** (closed): Split the 3,400-line sim/README.md into a harness reference plus per-experiment docs
- **Issue #283** (closed): CI guard: fail PRs that modify or delete committed sim records (append-only evidence)
- **Issue #280** (closed): ci: lint every tracked shell script with bash -n (4 flow scripts are missing from the hardcoded list)
- **Issue #278** (closed): layout: PDK-free verdict tests for the ERC/LVS/area evidence renderers
- **PR #274**: layout: consolidate git() and run_klt_json() helpers (#273)
- **Issue #273** (closed): layout: consolidate duplicated subprocess helpers in record-producing scripts
- **PR #270**: layout: folded-resistor PVT/mismatch qualification matrix, driver and BLOCKED record (#263)
- **PR #269**: test(layout): PDK-free unit tests for gen-ldo-blocks placement and track planners
- **PR #268**: layout: dual-deck (curated + official sky130A_mr) DRC gate and rule-family diagnosis for ldo-core (#260)
- **PR #266**: docs(readme): remove superseded verdicts and yield-control claim (#264)
- **PR #262**: Core area: MiM capacitor + supply-rail overlay demonstrator (feasible on plan, 0.0768 mm^2) (#254)
- **PR #259**: Folded resistors: resistor-only series-compaction qualification (#253)
- **Issue #265** (closed): layout: PDK-free unit tests for gen-ldo-blocks.py's placement and track planners
- **Issue #264** (closed): README: remove superseded measurement verdicts and yield-control claims
- **Issue #260** (closed): Routed ldo_core layout is not clean under the PDK's own sky130A_mr.drc (curated klt deck passes)
- **Issue #254** (closed): Core area: prove a MiM capacitor and supply-rail overlay plan
- **Issue #253** (closed): Folded resistors: validate series compaction before changing the LDO floorplan

### 2026-10-10

- **Issue #255** (closed): Characterization: reject malformed campaign verdicts instead of coercing truthiness
- **PR #257**: Characterization: reject malformed campaign verdicts (#255)
- **Issue #252** (closed): Share duplicated X-card token parsing between layout and LVS generators
- **PR #256**: refactor(layout): share X-card token parsing between generators
- **Issue #249** (closed): layout: add PDK-free unit tests with negative controls for check-erc-supply-spec.py
- **PR #251**: test(layout): PDK-free unit tests for check-erc-supply-spec.py

### 2026-10-09

- **Issue #246** (closed): Area: quantify compaction feasibility under the ratified core footprint limit
- **PR #248**: Area budget and compaction-feasibility study (#246)
- **Issue #245** (closed): Characterization: propagate schematic staleness through PEX source provenance
- **PR #247**: Characterization: propagate schematic staleness through PEX source provenance

### 2026-10-08

- **Issue #230** (closed): Thermal hysteresis: integrate the demonstrated regenerative comparator into the LDO
- **PR #242**: feat(thermal): integrate regenerative trip comparator into the LDO; tt/3.30V hysteresis 13.1 C (#230)
- **Issue #236** (closed): Measure routed core area against the ratified 0.1 mm² limit
- **PR #240**: Measure routed core area against the ratified 0.1 mm² limit
- **Issue #229** (closed): Thermal hysteresis: develop and demonstrate a standalone regenerative comparator
- **Issue #237** (closed): Extend simulation freshness to experiment and solver inputs
- **PR #234**: Standalone regenerative thermal comparator, tt/3.30V hysteresis demonstration (#229)
- **PR #238**: Extend simulation freshness to experiment and solver inputs

### 2026-10-08

- **Issue #145** (closed): sim/enable-shutdown: decide whether the near-zero max-only shutdown-current bounds need a noise-safe physicality floor
- **PR #232**: docs(sim/enable-shutdown): shutdown-current bounds stay max-only, deliberately (#145)

### 2026-10-07

- **PR #227**: ci: run on GitHub-hosted runners; the shared self-hosted runner is retired

### 2026-10-02

- **Issue #150** (closed): Follow-on: Work identified in PR #148
- **Issue #138** (closed): dropout-vs-load: #116's pass-device resize widens mechanism-4 DC-solution-multiplicity fragility at 125C (more corners, larger excursions)

### 2026-10-01

- **Issue #224** (closed): Remove duplicate klt_binary() in sim/bin/mc-run.py and yield-run.py
- **PR #226**: sim: dedup klt_binary() into _record_common.py

### 2026-09-30

- **Issue #222** (closed): signoff: paired ERC+LVS citation checks hash presence, not that each pin names its own file
- **Issue #129** (closed): layout: erc-supply-spec.json's nwell comment cites a superseded layout's x-span; pre-flight re-derives only the asserted region
- **Issue #112** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo
- **PR #225**: layout: ERC pre-flight re-derives the drawn n-well narrative (#129)
- **PR #223**: signoff: correlate each paired citation to its own pin, by file
- **PR #128**: layout: klt erc supply spec + evidence for T1 item 11 (power delivery, structural)
- **PR #102**: fix(ratification): remove unwrapped private-repo reference from market-key/SKILL.md

### 2026-09-27

- **Issue #220** (closed): Wire build_characterization_report.py --check into a gate (decide the PDK-dependence first)
- **Issue #217** (closed): sim/bin/mc-run.py and yield-run.py's new negative-control helpers have no PDK-free unit tests
- **Issue #215** (closed): build_characterization_report.py crashes on main: latest_sim_record picks the newest file, which is now a klt yield record with no netlist snapshot
- **Issue #211** (closed): signoff item 6 is met, but the campaign it cites declares no deterministic negative control
- **Issue #207** (closed): docs(signoff): item 5 still says 'FAIL on 7 of the 12 graded rows' — Line regulation's PASS makes it 6
- **Issue #203** (closed): signoff item 6: the Monte Carlo campaign passes but there is no `klt yield` report, so it grades wrong_kind
- **Issue #201** (closed): sim(psrr-dc): EN is an AC ground while VIN carries the 1 V perturbation — is the supply-rejection number measured with an off-contract enable?
- **Issue #173** (closed): Convert sim/iq's .op chain to a seeded initial condition, folding in #133's regulation gate
- **Issue #168** (closed): Generalize #164's initial-condition contract across sim/, and fold in #133's regulation gate: all 45 line-regulation corner logs carry solver warnings at the same resistor instances
- **Issue #133** (closed): sim/iq scores negative (non-physical) Iq at non-regulating corners as PASS — max-only bound has no floor or regulation gate
- **PR #221**: ci: gate measurements/characterization.md with a PDK-free structural --check
- **PR #219**: test: add PDK-free unit coverage for mc-run.py and yield-run.py helpers
- **PR #218**: fix: build_characterization_report.py must select campaign records, not klt yield records
- **PR #216**: sim(negctl): run the seeded known-bad variant — item 6's negative control is `detected` (#211)
- **PR #214**: sim(iq): seed the .op chain to the #171 IC contract, fold in #133's regulation gate
- **PR #212**: signoff item 6: mint a `klt yield` report over the MC campaign — unmet/wrong_kind -> met (T1 3/11 -> 4/11)
- **PR #210**: docs(signoff): item 5 FAIL count 7 -> 6 after Line regulation moved to PASS
- **PR #209**: sim(psrr-dc): settle the AC-grounded EN question — measured over 45 corners, ≤0.0017 dB, bench unchanged


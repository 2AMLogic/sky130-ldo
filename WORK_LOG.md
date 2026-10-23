# Work Log

Chronological record of merged pull requests and closed issues. Maintained by the Loom Guide role.

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

### 2026-09-26

- **Issue #206** (closed): docs(spec): restate the Line regulation row's Notes against record 20260926-200304-35b7392 — 'FAIL (18/45)' is three records stale and the row now passes 45/45
- **Issue #200** (closed): sim(line-regulation): mint the 45-corner record under #196's EN convention — the deck is fixed, the matrix is not re-run (~7 h serial on the sweep host)
- **Issue #196** (closed): sim(line-regulation): EN is driven at 'vsup' while VIN is alter-ed to 3.63V — the same EN-below-VIN geometry #187 root-caused, and the 5 failing corners are exactly that column
- **Issue #191** (closed): sim/README.md and dropout-vs-load/experiment.json misstate the shipped ramp rate as 106.5 V/s / 26ms (actual: 266.3 V/s / 14ms)
- **Issue #190** (closed): corner-run.py records the deck as the "exact input given to ngspice" but not sim/spiceinit, and #171's solver-diagnostic FAIL does not reproduce without it
- **Issue #189** (closed): sim(thermal): 2 of 15 corners still trip the #171 solver-diagnostic gate after seeding, and it is not the shared-.nodeset limitation
- **Issue #187** (closed): sim(dropout-vs-load): fs/125C/2.97V does not come up — the one residual outlier in the post-#178 record, with no solver diagnostic
- **Issue #184** (closed): sim/load-regulation's '200ms not 1ms' justification is attributed to the uic deck but measured on the seeded one (does not reproduce)
- **Issue #180** (closed): Seed sim/load-transient's tran analysis to conform to the initial-condition contract
- **Issue #179** (closed): Seed sim/loop-gain and sim/psrr-dc's AC analyses to conform to the initial-condition contract
- **Issue #178** (closed): Seed sim/dropout-vs-load and sim/thermal's DC/temperature sweeps to conform to the initial-condition contract
- **Issue #172** (closed): Convert sim/line-regulation and sim/load-regulation's .op chains to a seeded initial condition, re-run and record
- **Issue #166** (closed): spec/target-spec.md: rewrite the Load transient row's Notes column now that #180/PR #183 landed the full 45-corner re-run
- **Issue #127** (closed): signoff: items 4 and 6 cannot be freshness-pinned — this repo's LVS/MC envelopes were produced by klt 0.2.0 (provenance.input: null)
- **PR #208**: docs(spec): restate Line/Load regulation Notes against their current records
- **PR #205**: sim(line-regulation): mint the 45-corner record under #196's EN convention — 45/45 PASS, and the supply axis is finally a negative control
- **PR #204**: signoff: re-point item 6 at the current Monte Carlo record and pin it — the graded reason moves check_failed -> wrong_kind
- **PR #202**: sim(line-regulation): drive EN at the instantaneous VIN — the 5 failing corners were the #187 EN-below-VIN artifact, and the 45-corner re-run is a measured compute gap (#196)
- **PR #199**: signoff: re-point item 4 at a klt-0.6.0 LVS record; defer item 6's re-pointing
- **PR #198**: docs(spec): restate the Load transient row's Notes against the full 45-corner record 20260926-013955-6449a98
- **PR #197**: sim(dropout-vs-load): drive EN at the VIN rail and hold the ramp rate constant — the fs/125C/2.97V collapse was an enable-path headroom limit the bench convention walked into
- **PR #195**: sim(thermal): the last two #171-gate corners were one node's supply classification in the .nodeset seed, not the trip bifurcation (#189)
- **PR #194**: sim(corner-run): record the .spiceinit ngspice read next to each deck
- **PR #193**: docs(sim): correct dropout-vs-load's shipped ramp rate to 266.3 V/s / 14ms in two stale prose spots
- **PR #192**: docs(sim): correct load-regulation's 200ms-vs-1ms attribution (does not reproduce on the uic deck)
- **PR #188**: sim: seed loop-gain/psrr-dc's ac analyses per the initial-condition contract (#179)
- **PR #186**: sim: convert dropout-vs-load's dc VIN sweep to a cold-start ramp and seed thermal's dc temp sweeps (#171 contract)
- **PR #185**: sim(current-limit): seed legs 1 and 3 with `tran ... uic` — an EN edge alone does not cover the transient's op solve
- **PR #183**: sim: seed load-transient's tran to the #171 initial-condition contract
- **PR #182**: sim: convert line/load-regulation's unseeded .op chains to the #171 initial-condition contract, re-run both 45-corner matrices

### 2026-09-25

- **Issue #174** (closed): Audit remaining sim/ benches (current-limit, dropout-vs-load, loop-gain, load-transient, psrr-dc, thermal, startup, enable-shutdown) for the same initial-condition exposure
- **Issue #171** (closed): Define sim/'s initial-condition contract; fail a corner on a solver diagnostic (corner-run.py)
- **Issue #169** (closed): Re-test #81 item 2's 125C/50mA second equilibrium with the full node set constrained: #164 showed its method unreliable at a gentler corner
- **Issue #164** (closed): Mismatch alone latches the loop off at 27C/1mA: ~6% of MC draws settle with VOUT at the input rail (startup bench is 45/45 and cannot see it)
- **Issue #154** (closed): layout: gen-ldo-blocks.py routes VIN/VOUT as 0.30um signal trunks, making post-layout full-load rows non-physical
- **Issue #119** (closed): Load transient FAILs 20/45 corners — re-measure after the stability fix before designing for it
- **Issue #118** (closed): DC accuracy: Output (177/200 MC), line regulation (18/45) and load regulation (34/45) all FAIL
- **PR #181**: docs(sim): audit remaining sim/ benches for initial-condition-contract exposure
- **PR #176**: sim: define initial-condition contract; fail a corner on a solver diagnostic (corner-run.py)
- **PR #175**: sim+docs: #81 item 2's 125C/50mA second equilibrium does not exist -- a five-variant IC screen regulates everywhere; #81's numbers were EA_OUT/TS_SNS/TS_REF
- **PR #170**: sim: seed mc-output-accuracy's transient from a realizable state — the 27C/1mA rail mode is the bench's .op, not a second equilibrium
- **PR #167**: fix(sim): size load-transient C_out to DR-002 ceiling; instrument the recovery-time clause
- **PR #165**: DC accuracy: one mechanism behind all three rows — and it is not matching, supply rejection or loop gain
- **PR #163**: layout: size VIN/VOUT as spec-derived power rails, and measure why the extractor cannot see it

### 2026-09-24

- **Issue #159** (closed): Residual stale-ratification prose in design/README.md and challenge-4-proposal.md (left behind by #152) plus a possibly-stale "No LDO layout yet" heading
- **Issue #156** (closed): docs: the stated full-load extracted-VOUT range in signoff/README.md does not match the record's own delta[] rows
- **Issue #153** (closed): Stale "once issue #1 rules/ratifies" phrasing survives the DR-006 ratification sweep (and DR-006's own header still reads proposed)
- **Issue #152** (closed): Testbench .sch headers and design/README.md still call the target table DRAFT after DR-006/#1 ratified it
- **Issue #147** (closed): sim/ manifests and sim/README.md still call the target table DRAFT after DR-006/#1 ratified it
- **Issue #146** (closed): characterization.md's Post-layout PEX detail is stale relative to build_characterization_report.py --check
- **Issue #142** (closed): Draw the sky130 hvi voltage-domain marker in ldo_core's layout so extraction binds g5v0d10v5, not the 01v8 core flavour
- **Issue #140** (closed): ci: lint for duplicate DR-NNN decision-record numbers (four open PRs each claimed DR-008)
- **Issue #125** (closed): README: embed the fleet burndown chart (one line)
- **Issue #120** (closed): Thermal FAILs 3/15 corners — establish the delegated theta-JA assumption before treating it as a design defect
- **Issue #116** (closed): Dropout fails 0/45 corners against the ratified < 300 mV row — check pass-device sizing first (cf. gf180-ldo#139)
- **Issue #113** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **PR #161**: docs: retire the last stale "issue #1 has not ratified" claims and the "No LDO layout yet" heading (#159)
- **PR #160**: docs: state the real full-load extracted-VOUT extremes and narrow the klt-pin claim
- **PR #158**: docs: retire forward-looking "once issue #1 rules" phrasing; flip DR-006 to ratified (#153)
- **PR #157**: docs: cite spec/target-spec.md as ratified in testbench headers and design/README.md (#152)
- **PR #155**: feat(layout): draw the sky130 hvi voltage-domain marker so extraction binds g5v0d10v5 (#142)
- **PR #151**: docs: cite spec/target-spec.md as ratified in sim/ manifests and docs
- **PR #149**: feat(ci): fail check:ci on duplicate DR-NNN decision-record numbers (#140)
- **PR #148**: docs: relocate hand-written PEX triage narrative out of characterization.md
- **PR #139**: fix(design): re-size M_PASS/M_SENSE for dropout (DR-011); correct a disproven single-op claim (#116)
- **PR #135**: README: embed the fleet burndown chart
- **PR #132**: docs(spec): DR-008 — Thermal FAIL is the hysteresis bound, not theta-JA; record the delegated theta-JA integration constraint
- **PR #126**: feat(signoff): commit a klt signoff block manifest and the T1 verdict of record

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

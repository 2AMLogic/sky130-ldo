# Folded-resistor PVT / mismatch qualification -- record 20261017-031511-76e0ba72

Issue #263. Isolated passive devices only (PDK resistor model chains plus the measured li1 joint resistance). **Not** a full-core compliance claim and not a layout record. The matrix, the equivalence criterion (unchanged from #253) and the mismatch gates M1/M2 were committed in `layout/folded-res-qual/pvt/matrix.json` before any run.

## Provenance

- **git_sha**: 76e0ba729e8d7d7d8f36fe13c634d660b9223909
- **git_dirty_tooling**: False
- **klt**: klt 0.7.1.dev1649+g086c3106728a
- **backend**: batch
- **ngspice_det**: ngspice 46
- **ngspice_mc**: ngspice 46
- **remote_det**: {'provider': 'aws-batch-fleet', 'job_id': 'klt-sim-b76e6b9561f9', 'bucket': '2am-batch-jobs-221082181346', 'region': 'us-east-1', 'instance_id': 'i-0eb5e47660ac7a738', 'instance_type': 'm7i.4xlarge', 'availability_zone': 'us-east-1b', 'ami_id': 'ami-0e0bec04ad8e81877', 'lifecycle': 'spot', 'spot': True, 'state': 'done', 'exit_code': '0', 'concurrency': '1', 'physical_cores': '8', 'elapsed_seconds': 395}
- **remote_mc**: [{'provider': 'aws-batch-fleet', 'job_id': 'klt-sim-4f36cb8f4b25', 'bucket': '2am-batch-jobs-221082181346', 'region': 'us-east-1', 'instance_id': 'i-0216c1c46f432030a', 'instance_type': 'c7i.4xlarge', 'availability_zone': 'us-east-1b', 'ami_id': 'ami-0e0bec04ad8e81877', 'lifecycle': 'spot', 'spot': True, 'state': 'done', 'exit_code': '0', 'concurrency': '1', 'physical_cores': '8', 'elapsed_seconds': 998, 'client_submitted_at': None, 'client_launched_at': None, 'client_status_terminal_at': '2026-10-17T03:15:13.455397Z', 'client_collected_at': '2026-10-17T03:15:14.392600Z', 'runner_klt_version': '0.7.0', 'client_klt_version': '0.7.1.dev1649+g086c3106728a', 'runner_compatibility': 'match', 'runner_request_features': {'required': ['options.ngspice_init'], 'missing': [], 'status': 'supported'}, 'worker_environment': {'capture': 'ok', 'simulator': {'requested_binary': 'ngspice', 'binary_source': 'PATH', 'selected_path': '/usr/local/bin/ngspice', 'version_banner': '******\n** ngspice-46 : Circuit level simulation program\n** Compiled with KLU Direct Linear Solver\n** The U. C. Berkeley CAD Group\n** Copyright 1985-1994, Regents of the University of California.\n** Copyright 2001-2025, The ngspice team.\n** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n** Creation Date: Thu Oct  1 23:51:59 UTC 2026\n******\n', 'version_probe': 'ok'}, 'pdk': {'variant': 'sky130A', 'root': '/opt/pdk', 'stamp_scheme': 'sources-sha256', 'stamp_sha256': 'd5ac52956829da3fee35d0b307d4e6cb83ae0e6535b56dba2eefed61cdffaf9b', 'stamp_text': 'open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b', 'models_staged': False}, 'cpu_model': 'Intel(R) Xeon(R) Platinum 8488C', 'omp_num_threads': None, 'image_manifest': None, 'model_inputs': None, 'diagnostics': [], 'pdk_stamp_comparison': {'status': 'match'}, 'engine_build_comparison': {'status': 'mismatch', 'warning': "the worker's ngspice --version banner differs from the local binary's; build options (e.g. FFT linkage) may differ, so results derived from them can differ from a local run"}}, 'runner_model_inputs': None}, {'provider': 'aws-batch-fleet', 'job_id': 'klt-sim-d41aeddd4798', 'bucket': '2am-batch-jobs-221082181346', 'region': 'us-east-1', 'instance_id': 'i-039fb52feb6637bf8', 'instance_type': 'm7i.4xlarge', 'availability_zone': 'us-east-1d', 'ami_id': 'ami-0e0bec04ad8e81877', 'lifecycle': 'spot', 'spot': True, 'state': 'done', 'exit_code': '0', 'concurrency': '1', 'physical_cores': '8', 'elapsed_seconds': 843, 'client_submitted_at': None, 'client_launched_at': None, 'client_status_terminal_at': '2026-10-17T03:15:17.137275Z', 'client_collected_at': '2026-10-17T03:15:17.999572Z', 'runner_klt_version': '0.7.0', 'client_klt_version': '0.7.1.dev1649+g086c3106728a', 'runner_compatibility': 'match', 'runner_request_features': {'required': ['options.ngspice_init'], 'missing': [], 'status': 'supported'}, 'worker_environment': {'capture': 'ok', 'simulator': {'requested_binary': 'ngspice', 'binary_source': 'PATH', 'selected_path': '/usr/local/bin/ngspice', 'version_banner': '******\n** ngspice-46 : Circuit level simulation program\n** Compiled with KLU Direct Linear Solver\n** The U. C. Berkeley CAD Group\n** Copyright 1985-1994, Regents of the University of California.\n** Copyright 2001-2025, The ngspice team.\n** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n** Creation Date: Thu Oct  1 23:51:59 UTC 2026\n******\n', 'version_probe': 'ok'}, 'pdk': {'variant': 'sky130A', 'root': '/opt/pdk', 'stamp_scheme': 'sources-sha256', 'stamp_sha256': 'd5ac52956829da3fee35d0b307d4e6cb83ae0e6535b56dba2eefed61cdffaf9b', 'stamp_text': 'open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b', 'models_staged': False}, 'cpu_model': 'Intel(R) Xeon(R) Platinum 8488C', 'omp_num_threads': None, 'image_manifest': None, 'model_inputs': None, 'diagnostics': [], 'pdk_stamp_comparison': {'status': 'match'}, 'engine_build_comparison': {'status': 'mismatch', 'warning': "the worker's ngspice --version banner differs from the local binary's; build options (e.g. FFT linkage) may differ, so results derived from them can differ from a local run"}}, 'runner_model_inputs': None}, {'provider': 'aws-batch-fleet', 'job_id': 'klt-sim-fbb24b3a5c80', 'bucket': '2am-batch-jobs-221082181346', 'region': 'us-east-1', 'instance_id': 'i-0f62dd73adf3be4b2', 'instance_type': 'm7i.4xlarge', 'availability_zone': 'us-east-1b', 'ami_id': 'ami-0e0bec04ad8e81877', 'lifecycle': 'spot', 'spot': True, 'state': 'done', 'exit_code': '0', 'concurrency': '1', 'physical_cores': '8', 'elapsed_seconds': 922, 'client_submitted_at': None, 'client_launched_at': None, 'client_status_terminal_at': '2026-10-17T03:15:20.823987Z', 'client_collected_at': '2026-10-17T03:15:22.225395Z', 'runner_klt_version': '0.7.0', 'client_klt_version': '0.7.1.dev1649+g086c3106728a', 'runner_compatibility': 'match', 'runner_request_features': {'required': ['options.ngspice_init'], 'missing': [], 'status': 'supported'}, 'worker_environment': {'capture': 'ok', 'simulator': {'requested_binary': 'ngspice', 'binary_source': 'PATH', 'selected_path': '/usr/local/bin/ngspice', 'version_banner': '******\n** ngspice-46 : Circuit level simulation program\n** Compiled with KLU Direct Linear Solver\n** The U. C. Berkeley CAD Group\n** Copyright 1985-1994, Regents of the University of California.\n** Copyright 2001-2025, The ngspice team.\n** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n** Creation Date: Thu Oct  1 23:51:59 UTC 2026\n******\n', 'version_probe': 'ok'}, 'pdk': {'variant': 'sky130A', 'root': '/opt/pdk', 'stamp_scheme': 'sources-sha256', 'stamp_sha256': 'd5ac52956829da3fee35d0b307d4e6cb83ae0e6535b56dba2eefed61cdffaf9b', 'stamp_text': 'open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b', 'models_staged': False}, 'cpu_model': 'Intel(R) Xeon(R) Platinum 8488C', 'omp_num_threads': None, 'image_manifest': None, 'model_inputs': None, 'diagnostics': [], 'pdk_stamp_comparison': {'status': 'match'}, 'engine_build_comparison': {'status': 'mismatch', 'warning': "the worker's ngspice --version banner differs from the local binary's; build options (e.g. FFT linkage) may differ, so results derived from them can differ from a local run"}}, 'runner_model_inputs': None}, {'provider': 'aws-batch-fleet', 'job_id': 'klt-sim-63f01180686b', 'bucket': '2am-batch-jobs-221082181346', 'region': 'us-east-1', 'instance_id': 'i-0194b7895ebfb813c', 'instance_type': 'm7i.4xlarge', 'availability_zone': 'us-east-1b', 'ami_id': 'ami-0e0bec04ad8e81877', 'lifecycle': 'spot', 'spot': True, 'state': 'done', 'exit_code': '0', 'concurrency': '1', 'physical_cores': '8', 'elapsed_seconds': 1137, 'client_submitted_at': None, 'client_launched_at': None, 'client_status_terminal_at': '2026-10-17T03:15:24.878374Z', 'client_collected_at': '2026-10-17T03:15:25.814682Z', 'runner_klt_version': '0.7.0', 'client_klt_version': '0.7.1.dev1649+g086c3106728a', 'runner_compatibility': 'match', 'runner_request_features': {'required': ['options.ngspice_init'], 'missing': [], 'status': 'supported'}, 'worker_environment': {'capture': 'ok', 'simulator': {'requested_binary': 'ngspice', 'binary_source': 'PATH', 'selected_path': '/usr/local/bin/ngspice', 'version_banner': '******\n** ngspice-46 : Circuit level simulation program\n** Compiled with KLU Direct Linear Solver\n** The U. C. Berkeley CAD Group\n** Copyright 1985-1994, Regents of the University of California.\n** Copyright 2001-2025, The ngspice team.\n** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n** Creation Date: Thu Oct  1 23:51:59 UTC 2026\n******\n', 'version_probe': 'ok'}, 'pdk': {'variant': 'sky130A', 'root': '/opt/pdk', 'stamp_scheme': 'sources-sha256', 'stamp_sha256': 'd5ac52956829da3fee35d0b307d4e6cb83ae0e6535b56dba2eefed61cdffaf9b', 'stamp_text': 'open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b', 'models_staged': False}, 'cpu_model': 'Intel(R) Xeon(R) Platinum 8488C', 'omp_num_threads': None, 'image_manifest': None, 'model_inputs': None, 'diagnostics': [], 'pdk_stamp_comparison': {'status': 'match'}, 'engine_build_comparison': {'status': 'mismatch', 'warning': "the worker's ngspice --version banner differs from the local binary's; build options (e.g. FFT linkage) may differ, so results derived from them can differ from a local run"}}, 'runner_model_inputs': None}, {'provider': 'aws-batch-fleet', 'job_id': 'klt-sim-7c4e4b516200', 'bucket': '2am-batch-jobs-221082181346', 'region': 'us-east-1', 'instance_id': 'i-08984e913cf17a7e0', 'instance_type': 'm7i.4xlarge', 'availability_zone': 'us-east-1a', 'ami_id': 'ami-0e0bec04ad8e81877', 'lifecycle': 'spot', 'spot': True, 'state': 'done', 'exit_code': '0', 'concurrency': '1', 'physical_cores': '8', 'elapsed_seconds': 843, 'client_submitted_at': None, 'client_launched_at': None, 'client_status_terminal_at': '2026-10-17T03:15:28.405474Z', 'client_collected_at': '2026-10-17T03:15:29.303845Z', 'runner_klt_version': '0.7.0', 'client_klt_version': '0.7.1.dev1649+g086c3106728a', 'runner_compatibility': 'match', 'runner_request_features': {'required': ['options.ngspice_init'], 'missing': [], 'status': 'supported'}, 'worker_environment': {'capture': 'ok', 'simulator': {'requested_binary': 'ngspice', 'binary_source': 'PATH', 'selected_path': '/usr/local/bin/ngspice', 'version_banner': '******\n** ngspice-46 : Circuit level simulation program\n** Compiled with KLU Direct Linear Solver\n** The U. C. Berkeley CAD Group\n** Copyright 1985-1994, Regents of the University of California.\n** Copyright 2001-2025, The ngspice team.\n** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n** Creation Date: Thu Oct  1 23:51:59 UTC 2026\n******\n', 'version_probe': 'ok'}, 'pdk': {'variant': 'sky130A', 'root': '/opt/pdk', 'stamp_scheme': 'sources-sha256', 'stamp_sha256': 'd5ac52956829da3fee35d0b307d4e6cb83ae0e6535b56dba2eefed61cdffaf9b', 'stamp_text': 'open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b', 'models_staged': False}, 'cpu_model': 'Intel(R) Xeon(R) Platinum 8488C', 'omp_num_threads': None, 'image_manifest': None, 'model_inputs': None, 'diagnostics': [], 'pdk_stamp_comparison': {'status': 'match'}, 'engine_build_comparison': {'status': 'mismatch', 'warning': "the worker's ngspice --version banner differs from the local binary's; build options (e.g. FFT linkage) may differ, so results derived from them can differ from a local run"}}, 'runner_model_inputs': None}]
- **pdk**: sky130A open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b (pin c6d73a35f524070e85faff4a6a9eef49553ebc2b)
- **models_lib_sha256_det**: 48de7c677e2c6e7d09b2559279de9f818be71010a4aa933d728eb4db3b133c84
- **models_lib_sha256_mc**: 48de7c677e2c6e7d09b2559279de9f818be71010a4aa933d728eb4db3b133c84
- **joint_source**: layout/folded-res-qual/reports/20261010-033502-704005c (klt pin 040f3406, joint 37.7905 ohm, unchanged; no geometry regenerated)
- **mc_seed**: 263001
- **mc_n**: 200

## Tolerance (unchanged from #253)

| resistor | sigma_local (unsplit) | tolerance (3 sigma) |
|---|---|---|
| R_BIAS | 0.0821 % | 0.2462 % |
| R_FB_A | 0.5337 % | 1.6010 % |

## Deterministic matrix (63 corner x temperature x voltage points)

Shift = R_chain / R_unsplit - 1, each taken at the same point. `j1` = measured pinned-geometry strap (37.79 ohm/joint), the judged column; `noj` = PDK model only; `j4` = 4x joint sensitivity.

### R_BIAS

| N | worst shift (j1) | at | min..max (j1) | noj worst | j4 worst | verdict (j1) | j4 verdict |
|---|---|---|---|---|---|---|---|
| 2 | +0.0745 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.0667 % .. +0.0745 % | +0.0706 % | +0.0855 % | EQUIVALENT | EQUIVALENT |
| 3 | +0.1491 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.1335 % .. +0.1491 % | +0.1411 % | +0.1710 % | EQUIVALENT | EQUIVALENT |
| 4 | +0.2226 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.1995 % .. +0.2226 % | +0.2117 % | +0.2564 % | EQUIVALENT | NOT EQUIVALENT |
| 5 | +0.2972 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.2663 % .. +0.2972 % | +0.2823 % | +0.3419 % | NOT EQUIVALENT | NOT EQUIVALENT |
| 6 | +0.3717 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.3330 % .. +0.3717 % | +0.3528 % | +0.4274 % | NOT EQUIVALENT | NOT EQUIVALENT |
| 8 | +0.5198 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.4665 % .. +0.5198 % | +0.4940 % | +0.5993 % | NOT EQUIVALENT | NOT EQUIVALENT |
| 10 | +0.6689 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.5993 % .. +0.6689 % | +0.6351 % | +0.7703 % | NOT EQUIVALENT | NOT EQUIVALENT |
| 12 | +0.8170 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.7328 % .. +0.8170 % | +0.7752 % | +0.9412 % | NOT EQUIVALENT | NOT EQUIVALENT |
| 16 (control) | +1.1142 % | `ll/Vop_r_bias=1.200_Vop_r_fb_a=0.588V/-40C` | +0.9991 % .. +1.1142 % | +1.0575 % | +1.2831 % | NOT EQUIVALENT | NOT EQUIVALENT |

### R_FB_A

| N | worst shift (j1) | at | min..max (j1) | noj worst | j4 worst | verdict (j1) | j4 verdict |
|---|---|---|---|---|---|---|---|
| 2 | -0.0209 % | `hh/Vop_r_bias=2.000_Vop_r_fb_a=0.600V/125C` | -0.0209 % .. -0.0151 % | -0.0242 % | -0.0109 % | EQUIVALENT | EQUIVALENT |
| 3 | -0.0368 % | `hh/Vop_r_bias=2.400_Vop_r_fb_a=0.612V/125C` | -0.0368 % .. -0.0252 % | -0.0426 % | -0.0175 % | EQUIVALENT | EQUIVALENT |
| 4 | -0.0510 % | `hh/Vop_r_bias=2.000_Vop_r_fb_a=0.600V/125C` | -0.0510 % .. -0.0339 % | -0.0602 % | -0.0226 % | EQUIVALENT | EQUIVALENT |
| 5 | -0.0652 % | `hh/Vop_r_bias=2.400_Vop_r_fb_a=0.612V/125C` | -0.0652 % .. -0.0422 % | -0.0777 % | -0.0267 % | EQUIVALENT | EQUIVALENT |
| 6 | -0.0785 % | `hh/Vop_r_bias=2.400_Vop_r_fb_a=0.612V/125C` | -0.0785 % .. -0.0501 % | -0.0944 % | -0.0309 % | EQUIVALENT | EQUIVALENT |

## Seeded mismatch Monte Carlo (n=200 per point, seed 263001, 15 process x temperature points, joint mode j1)

M1: |mean shift| <= tolerance at every point. M2: sigma_chain/sigma_unsplit <= 1.1 at every point. Mean-shift standard error is in the JSON.

| resistor | N | worst abs mean shift | worst sigma ratio | M1 | M2 |
|---|---|---|---|---|---|
| R_BIAS | 2 | 0.0801 % | 1.1114 | pass | FAIL |
| R_BIAS | 3 | 0.1419 % | 1.1229 | pass | FAIL |
| R_BIAS | 4 | 0.2213 % | 1.1316 | pass | FAIL |
| R_BIAS | 5 | 0.2978 % | 1.2005 | FAIL | FAIL |
| R_BIAS | 6 | 0.3660 % | 1.1938 | FAIL | FAIL |
| R_BIAS | 8 | 0.5200 % | 1.2723 | FAIL | FAIL |
| R_BIAS | 10 | 0.6603 % | 1.0325 | FAIL | pass |
| R_BIAS | 12 | 0.8174 % | 1.1596 | FAIL | FAIL |
| R_BIAS | 16 | 1.1156 % | 1.2673 | FAIL | FAIL |
| R_FB_A | 2 | 0.0926 % | 0.9810 | pass | pass |
| R_FB_A | 3 | 0.0413 % | 1.0131 | pass | pass |
| R_FB_A | 4 | 0.0602 % | 0.9355 | pass | pass |
| R_FB_A | 5 | 0.0763 % | 1.0020 | pass | pass |
| R_FB_A | 6 | 0.0755 % | 1.0584 | pass | pass |

### Sigma detail at tt_mm / 27C (relative, j1)

| resistor | N | sigma unsplit | sigma chain | ratio | mean shift +- SE |
|---|---|---|---|---|---|
| R_BIAS | 1 | 0.0730 % | 0.0730 % | 1.000 | +0.0000 % +- 0.0073 % |
| R_BIAS | 2 | 0.0730 % | 0.0811 % | 1.111 | +0.0695 % +- 0.0077 % |
| R_BIAS | 3 | 0.0730 % | 0.0819 % | 1.123 | +0.1345 % +- 0.0078 % |
| R_BIAS | 4 | 0.0730 % | 0.0824 % | 1.131 | +0.2090 % +- 0.0078 % |
| R_BIAS | 5 | 0.0730 % | 0.0873 % | 1.199 | +0.2889 % +- 0.0081 % |
| R_BIAS | 6 | 0.0730 % | 0.0869 % | 1.194 | +0.3565 % +- 0.0080 % |
| R_BIAS | 8 | 0.0730 % | 0.0924 % | 1.271 | +0.4940 % +- 0.0084 % |
| R_BIAS | 10 | 0.0730 % | 0.0742 % | 1.023 | +0.6305 % +- 0.0074 % |
| R_BIAS | 12 | 0.0730 % | 0.0840 % | 1.159 | +0.7752 % +- 0.0079 % |
| R_BIAS | 16 | 0.0730 % | 0.0915 % | 1.266 | +1.0714 % +- 0.0083 % |
| R_FB_A | 1 | 0.5513 % | 0.5513 % | 1.000 | +0.0000 % +- 0.0551 % |
| R_FB_A | 2 | 0.5513 % | 0.5302 % | 0.962 | +0.0838 % +- 0.0541 % |
| R_FB_A | 3 | 0.5513 % | 0.5585 % | 1.013 | +0.0029 % +- 0.0555 % |
| R_FB_A | 4 | 0.5513 % | 0.4981 % | 0.903 | -0.0259 % +- 0.0525 % |
| R_FB_A | 5 | 0.5513 % | 0.5522 % | 1.002 | +0.0371 % +- 0.0552 % |
| R_FB_A | 6 | 0.5513 % | 0.5236 % | 0.950 | +0.0542 % +- 0.0538 % |

## Qualification and recommendation

QUALIFIED = deterministic criterion (all points, j1) AND M1 AND M2.

| resistor | N | det worst | det | M1 | M2 | QUALIFIED | j4 flips verdict |
|---|---|---|---|---|---|---|---|
| R_BIAS | 2 | 0.0745 % | ok | ok | FAIL | **no** | no |
| R_BIAS | 3 | 0.1491 % | ok | ok | FAIL | **no** | no |
| R_BIAS | 4 | 0.2226 % | ok | ok | FAIL | **no** | yes |
| R_BIAS | 5 | 0.2972 % | FAIL | FAIL | FAIL | **no** | no |
| R_BIAS | 6 | 0.3717 % | FAIL | FAIL | FAIL | **no** | no |
| R_BIAS | 8 | 0.5198 % | FAIL | FAIL | FAIL | **no** | no |
| R_BIAS | 10 | 0.6689 % | FAIL | FAIL | ok | **no** | no |
| R_BIAS | 12 | 0.8170 % | FAIL | FAIL | FAIL | **no** | no |
| R_BIAS | 16 (control) | 1.1142 % | FAIL | FAIL | FAIL | **no** | no |
| R_FB_A | 2 | 0.0209 % | ok | ok | ok | **YES** | no |
| R_FB_A | 3 | 0.0368 % | ok | ok | ok | **YES** | no |
| R_FB_A | 4 | 0.0510 % | ok | ok | ok | **YES** | no |
| R_FB_A | 5 | 0.0652 % | ok | ok | ok | **YES** | no |
| R_FB_A | 6 | 0.0785 % | ok | ok | ok | **YES** | no |

### Control check

The known nonequivalent control(s) R_BIAS N=16 FAILED the deterministic criterion as required (study valid).

### Divider (R_FB) VOUT sensitivity, informational

Relative VOUT change of the 1:2 divider from the deterministic worst R_FB shift, if only R_FB_A is folded vs. all three units folded identically (common shift cancels to first order). Not a spec claim.

| N | worst unit shift | only R_FB_A folded | all three folded |
|---|---|---|---|
| 2 | -0.0209 % | -0.0070 % | +0.0000 % |
| 3 | -0.0368 % | -0.0123 % | +0.0000 % |
| 4 | -0.0510 % | -0.0170 % | +0.0000 % |
| 5 | -0.0652 % | -0.0217 % | +0.0000 % |
| 6 | -0.0785 % | -0.0262 % | -0.0000 % |

### R_BIAS current sensitivity, informational

I_bias ~ 1/R_BIAS to first order; the worst deterministic R shift moves I_bias by the negative of it. Whether that is acceptable is a design/spec decision, not made here.

## Verdict

- **R_BIAS: NO QUALIFIED FOLD** among the candidates; only the unsplit device is supported.
- **R_FB_A: largest qualified segment count N = 6** (uncompensated, drawn L = schematic L). Candidates above it are not qualified in this record.

These are passive-device electrical results. They do not touch the Area row, do not claim core compliance, and leave length compensation and schematic changes out of scope.

## Limitations

- Joint resistance is the 27 C tt value of the pinned-geometry li1 strap, held constant over temperature (li1 tempco not modelled); a 4x sensitivity bounds a larger strap pitch.
- Mismatch draws are independent per segment and per head (model behaviour); real spatial correlation between adjacent segments is not modelled.
- sf/fs and *_mm skew sections of the PDK leave the resistor parameters nominal; resistor skew comes from ll/hh.
- Passive-device evidence only: says nothing about the LDO meeting any spec row.
- klt reports resistor mismatch activity as 'not independently verified' for sky130; the nonzero unsplit sigma above is the evidence the draws are live.
- Seeds are klt-derived per sample from the base seed; the same seed is reused at every process/temperature point, so cross-corner comparisons share the derivation scheme but not necessarily draw values.

# Fresh Step 3 quality review: REWORK

Reviewer: /root/r21_step3_quality_review. One P1 CONFIRMED_DEFECT.

The new unmarked offline test `test_actual_candidate_client_is_explicit_and_pin_remains_legacy` directly imports the actual optional `chstockdata` package and requires version 0.4.2. Independent minimal simulations reproduce ModuleNotFoundError without the vendor and AssertionError with the legitimate old pin 0.3.0. Ordinary SIOS offline CI must not require this candidate installation.

Required narrow correction: inject a fake library in this offline test to verify explicit candidate admission, default rejection and old pin compatibility. Keep actual installed-library checks mandatory in the original five opt-in live tests; do not add skips.

The reviewer independently validated all 111 raw hashes, stable runtime/live qualification source, 54 passing capability outcomes, six v3 snapshots/run identities, four positive-plan RAW fills, two positive-plan halt rejections, actual 5 PASS/0 FAIL/0 SKIP live run and 17 PASS offline run. No other material issue was identified. No reviewer edits or network calls.

This REWORK blocks Step 3 local acceptance until the isolated offline dependency defect is corrected and reviewed.

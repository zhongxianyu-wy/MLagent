# Production CLI Tasks

Source plan: `docs/superpowers/plans/2026-05-27-production-cli.md`

## Phase 1: CLI Runtime Safety

- [X] PCLI-T001 Add product runtime integration tests for natural-language agent routing and plan-mode non-execution in `tests/integration/test_cli_runtime_product.py`
- [X] PCLI-T002 Verify PCLI-T001 fails with the current ask-only natural-language path
- [X] PCLI-T003 Wire `ConversationService.handle_turn()` to slash-first routing, natural-language classification, and `ModeGuard.authorize()`
- [X] PCLI-T004 Verify PCLI-T001 passes and existing mode/routing tests remain green

## Phase 2: Product Data Intake

- [X] PCLI-T005 Add product intake tests for manifest JSON writing and deterministic random split in `tests/integration/test_product_intake.py`
- [X] PCLI-T006 Verify PCLI-T005 fails against the current train-only manifest builder
- [X] PCLI-T007 Implement manifest JSON writing, split options, sample alignment validation, and standardized CSV outputs
- [X] PCLI-T008 Verify intake tests and existing data-intake tests pass

## Phase 3: Real Training Core

- [X] PCLI-T009 Add real sklearn k-fold training integration test in `tests/integration/test_real_training_pipeline.py`
- [X] PCLI-T010 Verify PCLI-T009 fails because `src/training/modeling.py` is missing
- [X] PCLI-T011 Implement `SklearnModelTrainer` with logistic regression probability prediction
- [X] PCLI-T012 Verify real training, metric, threshold, and leakage tests pass

## Phase 4: Real Exploration Outputs

- [X] PCLI-T013 Add real exploration output test in `tests/integration/test_real_explore_cli.py`
- [X] PCLI-T014 Verify PCLI-T013 fails against the mock exploration harness
- [X] PCLI-T015 Implement manifest loading, bounded real exploration rounds, and output artifacts
- [X] PCLI-T016 Verify exploration tests and run-service tests pass

## Phase 5: CLI Command Productization

- [X] PCLI-T017 Add CLI command tests for intake plus explore and non-silent unsupported command behavior
- [X] PCLI-T018 Verify PCLI-T017 fails against current CLI parser/no-op paths
- [X] PCLI-T019 Productize CLI argument handling for intake/explore and return actionable non-zero errors for unsupported real commands
- [X] PCLI-T020 Verify CLI command tests and quickstart path tests pass

## Phase 6: Strict Reproduction

- [X] PCLI-T021 Add product reproduction tests for matching and missing features
- [X] PCLI-T022 Verify PCLI-T021 fails until reproduction loads manifests
- [X] PCLI-T023 Implement strict Skill reproduction against standardized manifests
- [X] PCLI-T024 Verify reproduction tests pass

## Phase 7: Interactive Validation

- [X] PCLI-T025 Add product interactive validation test for one real round then pause
- [X] PCLI-T026 Verify PCLI-T025 fails until real one-round validation is wired
- [X] PCLI-T027 Implement one-round validation reuse of exploration pipeline with paused status
- [X] PCLI-T028 Verify interactive validation tests pass

## Phase 8: Skill Distillation and Optimization Gate

- [X] PCLI-T029 Add product distillation tests for notebook and best-run candidate generation
- [X] PCLI-T030 Verify PCLI-T029 fails until candidate content is product-grade
- [X] PCLI-T031 Implement structured SkillCandidate generation and darwin iteration status handling
- [X] PCLI-T032 Verify Skill distillation and approval-gate tests pass

## Phase 9: Research Boundary

- [X] PCLI-T033 Add product research tests for structured artifact metadata and memory ingestion
- [X] PCLI-T034 Verify PCLI-T033 fails against current offline placeholder client
- [X] PCLI-T035 Implement structured research adapter boundary with explicit unavailable status for non-injected offline search
- [X] PCLI-T036 Verify research tests pass

## Phase 10: Internal Readiness

- [X] PCLI-T037 Add full CLI smoke test for intake plus one-round exploration
- [X] PCLI-T038 Verify PCLI-T037 fails until all glue is connected
- [X] PCLI-T039 Update quickstart with product CLI commands and output expectations
- [X] PCLI-T040 Run full verification: `uv run pytest tests/ --cov=src --cov-report=term-missing`
- [X] PCLI-T041 Run manual fixture CLI intake/explore smoke commands

## Follow-Up Hardening

- [ ] PCLI-F001 Add Socratic or non-interactive handling for random splits where requested k-fold exceeds the post-split minority class count

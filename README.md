# ICT3113 Team 1 Assignment 1

The [golden test set](golden_set/README.md) contains the 175 final labels, annotation protocol and revision, independent label sheets, resolution record, and agreement statistic.

The [evaluation setup](evaluation/README.md) contains the pinned candidate models, the classification prompt, generation settings and parser shared by all models, and the CPU-only and smoke-test checks.

The [triage service](service/README.md) is the plain baseline web service that will be load-tested: it classifies tickets with one pinned model, stores them, supports search and counts, and writes a per-request log. It runs in Docker with Compose and has its own unit and integration tests.
# ICT3113 Team 1 Assignment 1

The [golden test set](golden_set/README.md) contains the 175 final labels, annotation protocol and revision, independent label sheets, resolution record, and agreement statistic.

The [evaluation setup](evaluation/README.md) contains the pinned candidate models, the classification prompt, generation settings and parser shared by all models, and the CPU-only and smoke-test checks.

The [triage service](service/README.md) is the plain baseline web service that will be load-tested: it classifies tickets with one pinned model, stores them, supports search and counts, and writes a per-request log. It runs in Docker with Compose and has its own unit and integration tests.
The [load and stress tests](load_test/SECOND_PC_SETUP.md) contain the open-loop JMeter plans, the automated test phases, and the raw `.jtl` files and per-run service logs. Setting up the system under test is in [load_test/FIRST_PC_SETUP.md](load_test/FIRST_PC_SETUP.md).

The [results record](results-record.md) holds every measured number (peak load, R3 throughput, stress test, accuracy) with its run IDs and the files it comes from, plus the predictions compared with the measurements and the deviations and limitations. The frozen predictions are in [prediction-record.md](prediction-record.md) and the requirements in [performance-requirements.md](performance-requirements.md).

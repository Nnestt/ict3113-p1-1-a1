# Test cases

The record of every test case for the triage service: the automated tests in this folder, and the system checks run by hand in Docker. For how to run the automated tests see the Tests section of [../README.md](../README.md). For the test strategy see section 10 of [../DESIGN.md](../DESIGN.md).

## Summary

| Level | File | Test functions | Cases run |
| --- | --- | ---: | ---: |
| Unit | `test_storage.py` | 11 | 11 |
| Unit | `test_request_log.py` | 11 | 11 |
| Unit | `test_app_unit.py` | 18 | 22 |
| Unit | `test_classifier_copy.py` | 1 | 3 |
| Integration | `test_integration.py` | 17 | 17 |
| **Automated total** | | **58** | **64** |
| System, by hand in Docker | section "System checks" below | | 19 |

A test function with several inputs counts as several cases. Last full run: 64 passed, on Python 3.12 (Docker) and Python 3.10 (virtual environment), 3 October 2026.

## What is real and what is replaced

| Level | Real | Replaced by a stand-in |
| --- | --- | --- |
| Unit, storage | `storage.py`, SQLite | The Docker volume, by a temporary file |
| Unit, request log | `request_log.py` | The request object, by a fake; the endpoints, by two dummy routes on a bare app; the log folder, by a temporary file |
| Unit, HTTP layer | `app.py` and its routing | `classifier.classify`, `classifier.ollama_get` and the storage functions, by stubs. No model, network or database is used |
| Integration | `app.py`, `storage.py`, `request_log.py` and the classifier's prompt building and parser, together | Only the two Ollama HTTP calls (`classifier.ollama_post`, `classifier.ollama_get`) |
| System | The built image, Uvicorn, the volume, the log bind mount and the network path to the host | Ollama, by a stand-in server on the host that replies after a set delay |

The classifier's own parser and prompt are not tested here. They belong to `evaluation/` and have their own `--self-test`.

## Unit tests: `test_storage.py`

| ID | Test function | Checks |
| --- | --- | --- |
| ST-01 | `test_init_db_creates_the_tickets_table` | `init_db` creates `tickets` with the six columns in order |
| ST-02 | `test_init_db_twice_keeps_existing_tickets` | Calling `init_db` again does not remove stored tickets |
| ST-03 | `test_insert_returns_increasing_ids` | Three inserts return ids 1, 2, 3 |
| ST-04 | `test_insert_stores_all_fields` | The row holds the narrative, category, model and request id given, and a UTC timestamp |
| ST-05 | `test_search_is_a_case_insensitive_substring_match` | `bANk FRO` finds `My Bank froze my account` |
| ST-06 | `test_search_returns_the_documented_fields` | Each result has exactly `id`, `narrative`, `category`, `model`, `created_at` |
| ST-07 | `test_search_orders_by_id` | Results come back in id order |
| ST-08 | `test_search_treats_percent_and_underscore_literally` | `%` and `_` match only tickets that contain those characters |
| ST-09 | `test_search_returns_empty_list_when_nothing_matches` | No match gives an empty list |
| ST-10 | `test_counts_include_every_category_with_zeros` | An empty table gives all eight categories with count 0 |
| ST-11 | `test_counts_are_correct_after_inserts` | Counts match the inserted tickets, including `INVALID`, and still have eight keys |

## Unit tests: `test_request_log.py`

| ID | Test function | Checks |
| --- | --- | --- |
| RL-01 | `test_write_log_line_appends_one_line_per_call` | Two calls give two valid JSON lines, in order |
| RL-02 | `test_write_log_line_keeps_non_ascii_text` | Non-ASCII text is written as is and reads back unchanged |
| RL-03 | `test_write_log_line_escapes_newlines_and_quotes` | A value with newlines and quotes still takes exactly one line |
| RL-04 | `test_build_record_has_all_required_fields` | The nine common fields come first, in order, with the right values; `ts` is UTC |
| RL-05 | `test_build_record_run_id_is_null_without_header` | `run_id` is null when `X-Run-ID` is absent |
| RL-06 | `test_build_record_appends_the_endpoint_extras` | Fields the endpoint added appear in the record |
| RL-07 | `test_middleware_logs_one_line_with_status_extras_and_duration` | One line for one request, with status 200, the endpoint's extra field, and `total_ms` of at least the 50 ms the endpoint slept |
| RL-08 | `test_middleware_uses_and_echoes_the_client_request_id` | A client `X-Request-ID` is logged and echoed in the response header |
| RL-09 | `test_middleware_generates_a_request_id_when_none_is_sent` | A 32-character id is generated, echoed and logged |
| RL-10 | `test_middleware_logs_an_unhandled_exception_as_500_with_the_error` | An endpoint that raises gives a 500 and one line with status 500 and the error text |
| RL-11 | `test_middleware_logs_unknown_route_and_wrong_method` | A 404 and a 405 are each logged with the right status, method and route |

## Unit tests: `test_app_unit.py`

| ID | Test function | Cases | Checks |
| --- | --- | ---: | --- |
| APP-01 | `test_post_tickets_returns_id_category_and_request_id` | 1 | A successful POST returns the stored id, the category, and the same request id as the response header |
| APP-02 | `test_post_tickets_classifies_once_and_inserts_the_label_once` | 1 | The classifier is called once with the narrative and model; one insert with the classifier's label and the request id returned to the client |
| APP-03 | `test_invalid_label_is_stored_and_returned` | 1 | An `INVALID` label is inserted and returned with status 200 |
| APP-04 | `test_connection_error_gives_502_and_nothing_is_stored` | 1 | A refused connection gives 502 and no insert |
| APP-05 | `test_read_timeout_gives_504_and_nothing_is_stored` | 1 | A `TimeoutError` gives 504 and no insert |
| APP-06 | `test_connect_timeout_wrapped_in_urlerror_gives_504` | 1 | A timeout wrapped in `URLError` also gives 504 |
| APP-07 | `test_bad_narrative_gives_422_and_classify_is_not_called` | 4 | Empty, whitespace-only, missing and non-string narratives give 422; the classifier and storage are not called |
| APP-08 | `test_search_without_q_gives_422` | 2 | Missing `q` and empty `q` give 422; storage is not called |
| APP-09 | `test_search_returns_what_storage_returns` | 1 | The reply holds the query, the count and the rows from storage; storage receives the query text |
| APP-10 | `test_stats_returns_storage_counts_with_all_eight_categories` | 1 | Storage is asked for the seven labels plus `INVALID`; the reply has the total and eight keys |
| APP-11 | `test_check_model_passes_when_the_digest_matches` | 1 | A pinned model with the matching digest passes |
| APP-12 | `test_check_model_only_checks_the_selected_model` | 1 | Another pinned model that is not pulled does not fail the check |
| APP-13 | `test_check_model_rejects_an_unknown_model` | 1 | An unpinned model raises "not a pinned model" |
| APP-14 | `test_check_model_rejects_a_model_that_is_not_pulled` | 1 | A pinned model missing from Ollama raises "not pulled" |
| APP-15 | `test_check_model_rejects_a_digest_mismatch` | 1 | A different local digest raises a digest error |
| APP-16 | `test_check_model_reports_unreachable_ollama` | 1 | A failing tags call raises "cannot reach Ollama" |
| APP-17 | `test_startup_exits_with_a_clear_message_when_the_check_fails` | 1 | Startup exits with a message that begins `STARTUP ERROR:` |
| APP-18 | `test_startup_creates_the_table_when_the_check_passes` | 1 | Startup calls `init_db` with the database path |

## Unit tests: `test_classifier_copy.py`

| ID | Test function | Cases | Checks |
| --- | --- | ---: | --- |
| CC-01 | `test_service_copy_is_identical_to_the_frozen_original` | 3 | `classifier.py`, `eval_config.json` and `prompt_template.md` in `service/` are byte-identical to the originals in `evaluation/` |

## Integration tests: `test_integration.py`

| ID | Test function | Checks |
| --- | --- | --- |
| INT-01 | `test_post_then_search_then_stats_agree` | A posted ticket is found by a search in a different case and counted once in stats |
| INT-02 | `test_real_prompt_is_built_from_the_narrative` | The prompt sent to Ollama contains the narrative |
| INT-03 | `test_unparseable_answer_is_stored_and_counted_as_invalid` | An answer the parser cannot read is returned, stored and counted as `INVALID` |
| INT-04 | `test_ollama_failure_returns_502_and_stores_nothing` | A refused connection gives 502; stats total and the table stay at 0 |
| INT-05 | `test_ollama_timeout_returns_504` | A timeout gives 504 |
| INT-06 | `test_request_and_run_ids_are_echoed_and_logged` | Client ids appear in the response header, the reply body and the log line |
| INT-07 | `test_ids_are_generated_when_headers_are_absent` | Two requests get different 32-character ids, logged in order; `run_id` is null |
| INT-08 | `test_every_request_gets_exactly_one_valid_log_line` | Eight requests with statuses 200, 422, 422, 200, 200, 404, 405, 502 give eight lines in that order, each with all common fields and the model and digest |
| INT-09 | `test_ticket_log_line_has_the_classifier_fields` | A successful ticket line has the ticket id, category, raw output, narrative length and all timing and token fields; `model_ms` is not above `total_ms` |
| INT-10 | `test_total_ms_and_model_ms_are_real_durations` | With a 50 ms Ollama delay, `model_ms` is at least 50 and `total_ms` is at least `model_ms` |
| INT-11 | `test_invalid_answer_keeps_the_raw_output_in_the_log` | An `INVALID` line keeps the model's raw answer |
| INT-12 | `test_search_log_line_has_query_and_result_count` | A search line has the query and the number of results |
| INT-13 | `test_failed_ollama_call_is_logged_with_error_and_no_ticket_id` | A 502 line has the error, the narrative length and `model_ms`, and no ticket id |
| INT-14 | `test_storage_failure_after_classification_is_a_500_that_keeps_the_model_fields` | If the insert fails after classification, the reply is 500 and the one log line has the error and the model fields, with no ticket id |
| INT-15 | `test_narrative_text_never_appears_in_the_log` | The narrative is absent from the log after a success, a 502 and a 422 |
| INT-16 | `test_request_id_stored_with_the_ticket_equals_the_logged_one` | The request id in the table equals the one in the log |
| INT-17 | `test_startup_check_passes_and_creates_the_table` | The app starts through its real startup check and serves `/stats` with total 0 |

## System checks

Run by hand in Docker on 3 October 2026, on a development machine (Windows 11, Docker Desktop), with `MODEL=qwen2.5:1.5b` and a stand-in Ollama on the host. The stand-in answers every call in parallel after a set delay, so these checks show the service's behaviour, not Ollama's. No real model was used. SYS-01 to SYS-18 were run on the first build (commit `d9a08aa`), during the build and again in part during the independent review. SYS-19 was run after the later changes.

| ID | Check | Expected | Observed |
| --- | --- | --- | --- |
| SYS-01 | Build the image and start the service; call `/stats` | Starts; all eight counts are 0 | Pass |
| SYS-02 | Post tickets, then `/search` and `/stats` | The three endpoints agree; `%` and `_` are literal | Pass |
| SYS-03 | Send `X-Request-ID` and `X-Run-ID`; then send neither | Ids echoed and logged; a 32-character id generated when absent | Pass |
| SYS-04 | Make the stand-in return an unreadable answer | Stored, returned and counted as `INVALID`; raw answer in the log | Pass |
| SYS-05 | Empty, whitespace and missing narrative; missing and empty `q`; unknown route; wrong method | 422, 422, 422, 422, 422, 404, 405, one log line each | Pass |
| SYS-06 | Stop the stand-in, then post | 502, nothing stored, log line has the error; `/stats` still answers | Pass |
| SYS-07 | Start with `MODEL` unset, unpinned, Ollama unreachable, digest mismatch, model not pulled | Compose refuses without `MODEL`; the others exit with one `STARTUP ERROR` line | Pass; exit code 3 |
| SYS-08 | `restart`, `down` then `up`, then `down -v` then `up` | Tickets kept until `down -v`; the log survives all of them | Pass |
| SYS-09 | Post with a 5 s reply; call `/search` during it | POST takes about 5 s; search returns at once | Pass: `total_ms` 5004.6, `model_ms` 4993.9; search 0.009 s |
| SYS-10 | 20 concurrent POSTs, 1 s reply | All succeed; 20 distinct lines and tickets; no lock errors | Pass: `total_ms` 1007.5 to 1057.4 |
| SYS-11 | Client gives up after 2 s on a 6 s reply | Recorded as observed behaviour | Nothing logged when the client left. At 6 s one line with status 200 and `total_ms` 5998.7; the ticket is stored |
| SYS-12 | Count log lines against requests sent | Equal; every line valid JSON | Pass: 46 lines for 46 requests; 13 for 13 in the review run |
| SYS-13 | 45 concurrent POSTs, 8 s reply; `/search` and `/stats` 1.5 s in | Requests beyond the 40-thread pool wait | The 5 late POSTs waited about 7.86 s for a thread. Search took 6565 ms and stats 6526 ms. With 20 concurrent POSTs they took 5.1 and 9.3 ms |
| SYS-14 | 100 concurrent POSTs with no delay plus 200 sequential searches | No errors, no lock errors, no malformed lines | Pass: all 300 returned 200; every line valid JSON with a unique id |
| SYS-15 | Remove the table, then post, search and get stats | 500, one log line each with the error | Pass on status and error. The POST line lacked the model fields; fixed in commit `d35bff5` and now covered by INT-14. Not repeated in Docker after the fix |
| SYS-16 | `docker compose stop` with a 5 s and a 15 s request in flight | Recorded as observed behaviour | The 5 s request finished and was logged. The 15 s request was killed at 10 s: no reply and no log line |
| SYS-17 | Reach a host service bound to `127.0.0.1` through `host.docker.internal` | The container connects | Pass on Docker Desktop for Windows. Not tested on Linux |
| SYS-18 | Store `CAFÉ`, search `café` and `CAFÉ` | Recorded as observed behaviour | `café` finds nothing, `CAFÉ` finds it: case is ignored for ASCII letters only |
| SYS-19 | After copying the classifier files into `service/`: rebuild, post, `/stats`, list the image | Works as before; the image holds only the six service files and `requirements.txt` | Pass |

Test traffic from these runs was deleted from `logs/` afterwards.

## Checking the tests themselves

During the review, 18 deliberate bugs were put into a copy of the code, one at a time, to see whether the suite would fail. Twelve were caught and six were not. Two of the six were judged not worth a test: a changed SQLite busy timeout, and a local-time timestamp that only passed because the container clock is UTC. The other four were real gaps: the status of an unhandled exception, the error field on that path, a `total_ms` of zero, and a missing raw output for `INVALID`. Tests RL-07, RL-10, INT-10 and INT-11 were added, and those four are now caught.

## Checks run outside this test suite

These need the team's test machine and cannot be run with a stand-in. Their results are in [results-record.md](../../results-record.md).

| ID | Check | Status |
| --- | --- | --- |
| PEND-01 | Start the service against real Ollama with each pinned model, and classify one non-golden ticket | Done: the peak-load runs started the service with each of the four models and classified non-golden tickets |
| PEND-02 | Reach port 8000 from the load generator machine | Done: every load and stress run was sent from the load generator |
| PEND-03 | A real 300 s Ollama timeout returning 504 | Not run. The mapping is covered by APP-05, APP-06 and INT-05 with a raised timeout |
| PEND-04 | Behaviour when real Ollama is overloaded, with `OLLAMA_NUM_PARALLEL=1` | Done in the stress test: requests queue inside Ollama; the service returned 200 for all 180 tickets |

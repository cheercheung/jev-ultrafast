# EvoLink integration notes

This fork adapts [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) for EvoLink Luna. The original MIT license, browser executor and indexed-target architecture are preserved. See the [main README](README.md) for installation, configuration and usage, and [source provenance](EVOLINK_SOURCE.json) for the upstream snapshot.

## Decision transport

The default provider is `evolink`. The adapter serializes observed state as `input`, converts named criteria to `questions[].choices`, and validates the returned answer array before the original action policy and freshness checks execute.

The default route is `POST https://direct.evolink.ai/v1/decisions`, model `gpt-6-luna-decisions`. The documented model alias `gpt-6-luna` and explicitly configured origin `https://api.evolink.ai` are accepted. There is no automatic endpoint fallback. [Official Decisions reference](https://evolink.ai/docs/en/api-manual/language-series/gpt/decisions/decisions-reference.json).

Operation and operation-specific target heads share one request. Targets with only one observed choice are omitted from the API request, because choice questions require at least two choices, and are resolved locally. Their confidence/probability of 1 represents one possible target rather than a model measurement. Only the selected operation's target can execute; invented targets, malformed probabilities and refusals stop execution.

Set `DECISION_PROVIDER=typesafe` to use the retained upstream transport. The regression fixtures for that transport remain separate from the EvoLink wire-format tests.

## Text generation and credentials

`TYPE_TEXT` uses a separate OpenAI-compatible text helper. The shipped `.env.example` selects `https://api.evolink.ai/v1`, model `gpt-6-luna`, and `TEXT_MODEL_REASONING=none`. This route sends `reasoning_effort`. Do not send `gpt-6-luna-decisions` to Chat Completions.

Fill both `EVOLINK_API_KEY` and `TEXT_MODEL_API_KEY` locally; they can contain the same EvoLink key. The inspector does not interpolate environment references within `.env`, so `${EVOLINK_API_KEY}` is not a substitute for a literal key in the second field. Missing keys stop before their model request. Keys remain server-side; no credential is bundled in this repository.

## Completion and outcomes

`Agent(..., completion_check=callback)` lets the caller decide whether the observed page permits a `DONE` operation. The callback does not choose browser actions or supply field strings. Its boolean result gates `DONE`; a blocked run, exception or budget stop can still occur. A final independent assertion remains necessary.

The recorded Shanghai–LAX task used this hook to check route, date, passenger/cabin settings, language and visible flights. The generic inspector and CLI do not install this flight-specific checker automatically.

## Evidence

The [published demo](docs/evolink/README.md) records the final verified Shanghai–LAX attempt, its timing boundary, earlier failed attempts and a later unsuccessful multi-month calendar task. [Run summary](docs/evolink/run-summary.json) includes the public measurements and source hashes. Original upstream Jev/Mercury performance numbers have not been reproduced as Luna results.

Offline verification uses mocked HTTP replies with no browser or paid APIs. To keep Browser Harness's import-time temporary directories inside the checkout, set `BROWSER_HARNESS_HOME` to a task-local ignored directory as shown in the README. The current suite has 50 tests, with Ruff, JavaScript syntax and wheel/sdist build checks alongside it.

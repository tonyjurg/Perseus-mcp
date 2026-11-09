# Live Perseus CTS responses

These XML files are unmodified response bodies captured on 9 November 2026.
`sources.json` records each request URL and observed root element. Tests use
these files offline; no live service is needed to run the regression suite.

The passage edition is the one resolved in notebook 01. Perseus returns a
`GetPassage` envelope for both passage operations, and uses the `cts3/ti`
namespace for references and the bare capabilities `TextInventory`. The
reference response contains the whole edition despite the requested book.
The large inventory and reference files are intentionally kept complete.

The `Live CTS format monitor` workflow runs every Monday at 05:23 UTC and can
also be started manually in GitHub Actions. It fetches the four captured response
URLs in `sources.json` and compares exact expanded XML roots (local name and
namespace). It also checks the manifest's three additional `probes`: GetLabel,
GetFirstUrn, and GetPrevNextUrn. Those endpoints have no successful captured
envelope yet, so the probes require the correct local operation root and report
the observed namespace without inventing a namespace baseline. Their known
malformed HTML responses are failures, not accepted baselines.

Each result is marked `ok`, `failed`, or `inconclusive`. Only
`ROOT_OR_NAMESPACE_CHANGED` and `INVALID_PAYLOAD` produce exit code 1.
Challenges, timeouts, HTTP/connection failures, and other upstream errors are
inconclusive: the report includes their codes, but they alone produce exit code
0. The overall report and job summary say `INCONCLUSIVE` rather than `OK` when
any endpoint could not be checked and none failed. A format failure still fails
a mixed run containing inconclusive endpoints. Review the summary even on a
green Actions run; that color can mean inconclusive, not that every format matched.

It runs independently of pull requests and is not a required merge
check. GitHub Actions notification preferences control failed-run notifications.
Keep this workflow out of branch-protection required checks.

Run it locally with `python scripts/check_cts_upstream.py`; use `--report PATH`
to save the JSON report. Each endpoint is fetched once, without metadata caches
or retries, with a 60-second total deadline and the server's response-size cap.
No response bodies are saved, and the monitor never updates the baseline.
Investigate failed runs and review any new captures before updating fixtures or
`sources.json`; an outage or challenge must not become the new expected format.

Runtime CTS validation uses local root names, so a namespace-only change is
reported by this monitor without rejecting usable responses or disk caches.

`navigation-malformed.html` is the unmodified response captured on 9 November
2026 from:
https://www.perseus.tufts.edu/hopper/CTS?request=GetFirstUrn&urn=urn:cts:greekLit:tlg0012.tlg001.perseus-grc1

It reproduces the undeclared `c:` prefix and `unbound prefix: line 2, column 2`
error documented in notebook 01. The notebook records that error for GetLabel
but does not preserve the raw body; this fixture is a fresh navigation capture.

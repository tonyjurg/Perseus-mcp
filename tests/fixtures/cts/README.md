# Live Perseus CTS responses

These XML files are unmodified response bodies captured on 9 November 2026.
`sources.json` records each request URL and observed root element. Tests use
these files offline; no live service is needed to run the regression suite.

The passage edition is the one resolved in notebook 01. Perseus returns a
`GetPassage` envelope for both passage operations, and uses the `cts3/ti`
namespace for references and the bare capabilities `TextInventory`. The
reference response contains the whole edition despite the requested book.
The large inventory and reference files are intentionally kept complete.

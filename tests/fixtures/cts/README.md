# Live Perseus CTS responses

These XML files are unmodified response bodies captured on 9 November 2026.
`sources.json` records each request URL and observed root element. Tests use
these files offline; no live service is needed to run the regression suite.

The passage edition is the one resolved in notebook 01. Perseus returns a
`GetPassage` envelope for both passage operations, and uses the `cts3/ti`
namespace for references and the bare capabilities `TextInventory`. The
reference response contains the whole edition despite the requested book.
The large inventory and reference files are intentionally kept complete.

`navigation-malformed.html` is the unmodified response captured on 9 November
2026 from:
https://www.perseus.tufts.edu/hopper/CTS?request=GetFirstUrn&urn=urn:cts:greekLit:tlg0012.tlg001.perseus-grc1

It reproduces the undeclared `c:` prefix and `unbound prefix: line 2, column 2`
error documented in notebook 01. The notebook records that error for GetLabel
but does not preserve the raw body; this fixture is a fresh navigation capture.

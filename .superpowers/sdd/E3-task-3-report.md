# E3 Task 3 Report: Deterministic Router and HTML Inserter

## Status

Implemented Task 3 in the `editorial-search-funnel` worktree from base commit
`3288879`, without changing the prior E1 logging or E2 classification work.

## Scope

Source changes are limited to the Task 3 ownership files:

- `config.py`
- `conversion_funnel.py`
- `tests/test_conversion_funnel.py`

This report is intentionally kept outside the source commit, matching the
earlier task-report convention in this worktree.

## TDD Evidence

1. Added the eight specified router, inserter, flag, and commercial-link
   tests before creating `conversion_funnel.py`.
2. Ran `python -m unittest tests.test_conversion_funnel -v`.
3. Confirmed the expected RED failure: `ModuleNotFoundError: No module named
   'conversion_funnel'`.
4. Added the safe configuration defaults and validation, followed by the
   complete deterministic routing and bounded HTML insertion module.
5. Re-ran `python -m unittest tests.test_conversion_funnel -v`: all 8 tests
   passed.

## Implementation

- `CONVERSION_CTA_ENABLED` defaults to disabled and must equal environment
  value `"1"` to enable insertion.
- `CERTIFICATION_SITE_URL` defaults to
  `https://certificacionmontessori.com`, strips only a trailing slash, and is
  validated to be exactly that HTTPS origin with no credentials, port, path,
  query, or fragment.
- `WHATSAPP_PHONE` defaults to `5215548885013` and is validated as digits
  only.
- `ConversionDecision` is frozen and routing accepts only the six declared
  intent destinations at `high` or `medium` relevance. All other inputs get a
  no-op decision.
- Every commercial destination is derived from the validated fixed origin and
  a closed route map. Attribution uses the specified five UTM fields.
- Contextual copy selection is deterministic from SHA-256 of
  `intent:post_slug`; no random selection is used.
- Enabled medium decisions insert exactly one contextual link. Enabled high
  decisions additionally append exactly one final CTA section containing the
  controlled destination and WhatsApp links. Low, invalid, and disabled cases
  preserve the original HTML unchanged.
- Existing AMMAC funnel markers prevent repeat insertion. Model-authored links
  to the commercial host, including `www`, are unwrapped while their text is
  retained; unrelated links remain intact.

## Verification

- `python -m unittest tests.test_conversion_funnel -v`: 8 passed.
- `python -m unittest discover -v`: 14 passed.
- `python -m compileall -q .`: passed.
- Secret scan for Telegram bot URL token patterns: no matches.
- `git diff --check`: passed.

## Self-Review

Reviewed the Task 3 diff against the supplied brief. The route map, labels,
UTM values, safe defaults, validation predicates, CTA copy, deterministic
anchor variation, insertion limits, and no-op behavior match the specified
implementation. The diff is confined to the requested source files; the
prior logging and classification changes remain intact.

## Concerns

No known implementation concerns. The specified Task 3 test suite does not
exercise `config.validate()` in a subprocess with malformed environment
values, so that validation is covered by direct implementation review rather
than a dedicated automated test in this task.

## E3 Review Fix Evidence

Controller confirmation established that the stricter security behavior takes
precedence over the brief's former marker-presence early return.

### Files Changed

- `config.py`
- `conversion_funnel.py`
- `tests/test_conversion_funnel.py`
- `.superpowers/sdd/E3-task-3-report.md`

### RED

Command:

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: failed as expected with 4 failures and 1 error across 12 tests.

- `test_high_rebuilds_spoofed_and_duplicate_markers` found two contextual
  links because any marker caused the former early return.
- `test_medium_removes_injected_final_cta_and_rebuilds_contextual_link`
  retained the spoofed contextual URL and final CTA for the same reason.
- `test_validate_rejects_noncanonical_certification_origins` accepted
  `https://@certificacionmontessori.com` and
  `https://certificacionmontessori.com:`; it also leaked `ValueError` for
  `https://certificacionmontessori.com:not-a-port`.

### GREEN

`apply_conversion_funnel()` now preserves idempotency only when the existing
structure exactly matches the deterministic contextual paragraph and, for a
high decision, final CTA for the current decision. Any marked CTA is removed;
marked contextual links are unwrapped and marked contextual containers are
unwrapped before bounded controlled content is rebuilt. This guarantees one
contextual link for medium decisions and one contextual link plus one final
CTA for high decisions.

`config.validate()` now requires the trailing-slash-normalized value to equal
`https://certificacionmontessori.com`, verifies the parsed netloc, and catches
invalid port parsing so every malformed origin follows the controlled
validation failure path.

Command:

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 12 tests passed.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 18 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

## E3 Quality-Gate Follow-Up: Orphan Final-CTA Markers

### Root Cause

The controlled-insertion check validated only contextual links and containers
plus final CTA sections. A fully valid generated insertion followed by an
orphan `ammac-training-cta-primary` or
`ammac-training-cta-whatsapp` link therefore passed idempotency validation.
The cleanup path used the same narrow selectors, leaving those arbitrary URLs
in the output.

### RED

Added focused high- and medium-relevance regression tests for an otherwise
valid generated insertion followed by, respectively, an orphan primary CTA
marker and an orphan WhatsApp CTA marker. Both use an arbitrary
`https://attacker.example/...` destination.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: failed as expected with 2 failures across 14 tests.

- `test_high_rebuilds_when_an_orphan_primary_cta_marker_is_present` found two
  primary CTA links.
- `test_medium_rebuilds_when_an_orphan_whatsapp_cta_marker_is_present` found
  one orphan WhatsApp CTA link.

### GREEN

Idempotency now requires the complete AMMAC marker inventory to be exactly the
deterministic contextual structure and, for high relevance, final CTA section
for the current decision. Marker detection covers every class beginning with
`ammac-training-` and the CTA attributes `data-program-id` and
`data-cta-position`. When the inventory is not exact, malformed CTA blocks are
removed and all remaining marked elements are unwrapped before bounded
controlled output is rebuilt.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 14 tests passed.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 20 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

## E3 Structural Cleanup Fix

### Root Cause

The complete marker inventory correctly rejected malformed structures, but the
cleanup path unwrapped every marked element. A marked non-anchor container such
as `<aside data-cta-position="final">...</aside>` therefore released arbitrary
descendants, including attacker-controlled links, back into the article.

Cleanup now inventories every element carrying an `ammac-training-*` class or
controlled CTA attribute. When that inventory is not the exact deterministic
insertion for the current decision, each outermost marked non-anchor subtree is
decomposed as a unit. Any surviving standalone marked anchor is replaced with
plain text, removing its URL and nested markup before bounded output is rebuilt.

### RED

Added high- and medium-relevance regressions for malformed data-attribute
containers with arbitrary child links, plus a regression for an unknown
`ammac-training-*` marked container.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: failed as expected with 3 failures across 17 tests.

- `test_high_removes_malformed_attribute_container_subtree` retained the
  attacker link.
- `test_medium_removes_malformed_attribute_container_subtree` retained the
  attacker link.
- `test_removes_unknown_marker_class_container_subtree` retained the attacker
  link.

### GREEN

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 17 tests passed.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 23 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

```bash
git diff --check
```

Result: exited 0.

### Concerns

No known implementation concerns.

## E3 User-Approved Normalize-and-Rebuild Architecture

The user approved replacing exact-structure recognition after repeated review
failures. Existing funnel markup is now always treated as uncontrolled input:
every application normalizes it away, strips uncontrolled certification-host
links, and rebuilds only the output permitted by the current decision and
configuration.

### Root Cause

The prior architecture returned before normalization for disabled and no-CTA
decisions, and returned early when generated-looking markup matched the
expected serialized structure. Placement and enclosing ancestors were not part
of that trust check, so exact-looking content could remain hidden, inert, or
inside an attacker-controlled anchor. The same early return also prevented
cleanup when promotion was disabled or relevance/intent resolved to no CTA.

### RED

Added regressions for hidden/inert relocation, enclosing attacker anchors,
medium/high byte-for-byte two-run idempotence, disabled/low/invalid cleanup,
safe visible paragraph selection, and safe root fallback. Existing spoof,
orphan, duplicate, and malformed-subtree tests were preserved.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: failed as expected with 8 failures across 22 tests. Failures showed the
attacker wrapper survived, contextual content was inserted under unsafe
ancestors, disabled/low/invalid paths skipped cleanup, and exact-looking blocks
under hidden/inert wrappers were trusted in place.

### GREEN

Removed the exact-structure recognition and marker-inventory trust helpers.
`apply_conversion_funnel()` now parses and normalizes before checking the flag
or CTA level. Normalization:

- unwraps unmarked ancestor anchors enclosing marked content;
- decomposes outermost marked non-anchor subtrees as units;
- replaces surviving marked anchors with plain text;
- strips every remaining link to the certification host; and
- leaves unrelated ordinary links outside malformed funnel structures intact.

Only `medium` and `high` decisions rebuild controlled output. Contextual
insertion skips paragraphs under anchors, `hidden`, `inert`, `aria-hidden`,
`display:none`, or `visibility:hidden` ancestors and otherwise uses a safe root
fallback. Repeated normalization and deterministic reconstruction converge to
byte-for-byte identical HTML.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 22 tests passed.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 28 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

```bash
rg -n "api\\.telegram\\.org/bot[0-9]{6,}:[A-Za-z0-9_-]{20,}" .
```

Result: no matches (`rg` exited 1 as expected).

```bash
git diff --check
```

Result: exited 0.

### Files Changed

- `conversion_funnel.py`
- `tests/test_conversion_funnel.py`
- `.superpowers/sdd/E3-task-3-report.md`

### Self-Review

Reviewed the final diff against the approved override and each requested
regression. The trust/recognition architecture is removed rather than bypassed;
normalization precedes every promotion decision; high, medium, and no-promotion
limits remain exact; unrelated links remain intact; and focused plus full-suite
verification covers the accumulated spoof/orphan/duplicate cases. Changes are
limited to E3-owned files. No known implementation concerns remain.

## Final E3 Architecture Review: Four Important Findings

The normalize-then-rebuild architecture remains in place. Every application
still normalizes uncontrolled funnel markup and certification-host links before
the enabled/relevance gate, and only then rebuilds canonical controlled output.

### RED Evidence

Added all four review regressions before changing production code, then ran:

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 27 tests ran with 5 expected failures.

- `test_strips_browser_normalized_backslash_commercial_links` retained all 6
  browser-normalized certification links, covering HTTPS, `www`, slash-based
  protocol-relative, and backslash-based protocol-relative forms.
- `test_forged_high_decision_is_rebuilt_from_classifier_fields` emitted the
  forged URL/program fields, while `test_forged_invalid_decision_fails_closed`
  promoted an invalid forged decision because `cta_level` was trusted.
- `test_disabled_hygiene_preserves_attribute_only_article_root` deleted the
  complete attribute-only editorial article subtree.
- `test_contextual_insertion_rejects_css_comment_obfuscation` inserted the
  contextual CTA under `style="display:/**/none"`.

### GREEN Implementation

- Link hygiene normalizes browser URL separators before authority parsing,
  unwraps parse failures conservatively, matches only the exact certification
  host and `www` host, and preserves
  `certificacionmontessori.com.evil.example` links.
- Promotion re-resolves a canonical decision solely from `intent`,
  `relevance`, `post_slug`, and `post_title`. All CTA level, route, program,
  label, URL, UTM, and copy generation uses that canonical object; invalid
  caller input resolves to no promotion.
- Normalization treats only `ammac-training-*` classes as removable funnel
  subtrees. Controlled attributes on classless elements are removed in place,
  preserving the element, descendants, content, and unrelated links. Existing
  malformed marked-class subtree coverage remains active.
- Contextual placement no longer parses inline CSS declarations. Any nonblank
  inline style on the candidate or an ancestor rejects that candidate, in
  addition to anchor, `hidden`, `inert`, and `aria-hidden` checks. The fallback
  regression confirms the CTA remains a top-level, bodyless WordPress fragment.

Focused GREEN command:

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 28 tests passed.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 34 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

```bash
rg -n "api\\.telegram\\.org/bot[0-9]{6,}:[A-Za-z0-9_-]{20,}" .
```

Result: no matches (`rg` exited 1 as expected).

```bash
git diff --check
```

Result: exited 0.

### Files Changed

- `conversion_funnel.py`
- `tests/test_conversion_funnel.py`
- `.superpowers/sdd/E3-task-3-report.md`

### Self-Review

Reviewed the diff against each Important finding and the accumulated E3
security/idempotence suite. Host matching remains exact after browser separator
normalization; supplied output fields are unreachable after canonical
re-resolution; attribute-only cleanup cannot delete semantic roots; malformed
marked-class subtrees are still removed; and styled contextual candidates are
rejected without partial CSS interpretation. Medium/high two-run output remains
byte-identical, disabled/low/invalid paths still perform hygiene without
promotion, and changes remain limited to E3-owned files.

### Concerns

No known implementation concerns.

## E3 Exact-Host Hygiene Follow-Up

### Root Cause

Host canonicalization used `rstrip(".")`, which accepted any number of
trailing DNS root dots. The parse-error path also unwrapped every link when
`urlsplit()` or strict `unquote()` failed, including unrelated malformed
authorities.

### RED

Added focused regressions for one trailing root dot versus two trailing dots,
and for the observed unrelated bracket-malformed URLs:
`https://[example.com/path` and `https://example.com]/path`. The existing
browser-valid controlled-host regressions and the prior malformed controlled
host regression remain in the focused suite.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: failed as expected with 2 failures across 34 tests.

- `test_strips_one_trailing_root_dot_but_preserves_double_dot_host` removed
  both one-dot and two-dot hosts because `rstrip(".")` removed both dots.
- `test_preserves_unrelated_bracket_malformed_links` removed both unrelated
  links because every parse failure entered the unconditional unwrap branch.

### GREEN

Host canonicalization now removes at most one trailing dot. Parse failures
now remain unchanged unless a conservative malformed-authority fallback can
positively establish the exact controlled certification or `www` host; the
prior malformed controlled-host cleanup remains active.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 34 tests passed, including all prior browser-valid controlled-host
regressions and the new exact-host cases.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 40 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

```bash
rg -n "api\.telegram\.org/bot[0-9]{6,}:[A-Za-z0-9_-]{20,}" .
```

Result: no matches; `rg` exited 1 as expected.

```bash
git diff --check
```

Result: exited 0.

### Files Changed

- `conversion_funnel.py`
- `tests/test_conversion_funnel.py`
- `.superpowers/sdd/E3-task-3-report.md`

### Concerns

No known implementation concerns.

## E3 Final Two Important Findings

The approved normalize-then-rebuild architecture remains unchanged. URL host
normalization is performed within uncontrolled-link hygiene, and contextual
placement still occurs only after existing funnel content has been normalized
away and the decision has been rebuilt canonically.

### Root Cause

The link sanitizer replaced backslashes but passed the result directly to
`urlparse()`. Excess post-scheme slashes were therefore parsed as path text,
and encoded or trailing-dot host spellings did not equal the canonical host.
The placement predicate modeled anchors, hidden/inert/ARIA-hidden state, and
nonblank inline styles, but did not model HTML elements whose descendants are
semantically unavailable or closed.

### RED

Added regressions for excess and mixed slash/backslash HTTP(S) authorities,
protocol-relative slash runs, no-slash special-scheme authority, C0/space and
embedded ASCII whitespace handling, percent-encoded and trailing-dot hosts,
exact-host suffix protection, unrelated path/query text, template, noscript,
closed details, closed dialog, and visible-paragraph placement.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 32 tests ran with 4 expected failures.

- `test_strips_whatwg_like_special_url_authorities` removed only 2 of 7
  controlled-host variants.
- `test_strips_encoded_and_trailing_dot_certification_hosts_only` removed 0
  of 2 controlled-host variants.
- `test_contextual_insertion_skips_template_and_noscript` placed the CTA after
  the noscript paragraph.
- `test_contextual_insertion_skips_closed_details_and_dialog` placed the CTA
  after the closed-dialog paragraph.

### GREEN

Added a dependency-free special-URL normalizer before `urlsplit()`. It trims
leading/trailing C0 and space, removes embedded tab/newline/carriage-return,
normalizes backslashes, canonicalizes HTTP(S) post-colon slash runs and
protocol-relative leading slash runs, and conservatively supplies the special
authority delimiter when absent. Parsed hosts are percent-decoded strictly,
lowercased, and stripped of a trailing root dot before exact comparison with
only `certificacionmontessori.com` and its `www` host.

The safe-placement predicate now rejects `template`, `noscript`, `script`,
`style`, `textarea`, `title`, `select`, `option`, and `head`, plus `details`
and `dialog` without the `open` attribute. Existing anchor, hidden, inert,
ARIA-hidden, and nonblank-style checks remain active.

```bash
python -m unittest tests.test_conversion_funnel -v
```

Result: 32 tests passed.

### Final Verification

```bash
python -m unittest discover -v
```

Result: 38 tests passed.

```bash
python -m compileall -q .
```

Result: exited 0.

```bash
rg -n "api\\.telegram\\.org/bot[0-9]{6,}:[A-Za-z0-9_-]{20,}" .
```

Result: no matches (`rg` exited 1 as expected).

```bash
git diff --check
```

Result: exited 0.

### Files Changed

- `conversion_funnel.py`
- `tests/test_conversion_funnel.py`
- `.superpowers/sdd/E3-task-3-report.md`

### Self-Review

Reviewed the diff against both remaining findings and all earlier E3
constraints. Host matching is exact only after authority normalization and
host decoding; suffix hosts and domain text in unrelated paths or queries are
preserved. Malformed authorities retain the existing conservative cleanup.
Semantic placement rejects every requested unavailable ancestor while allowing
open details/dialog to follow their visible semantics. Normalize-then-rebuild,
canonical decision reconstruction, idempotence, and no-promotion hygiene are
unchanged. The diff is confined to E3-owned files and adds no dependency.

### Concerns

No known implementation concerns.

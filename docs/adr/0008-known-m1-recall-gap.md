# ADR-0008 — Known M1 recall gap: root-caused, not fixed

- **Status:** accepted
- **Date:** 2026-08-20
- **Deciders:** RaiAbhijeet

## Context

Running the real evaluation harness (`python -m eval.run_eval`, against the
live Postgres + Ollama stack and the real 894-chunk `siemens-dishwasher`
corpus, real 60-entry `golden_de.yaml`) produced:

```
recall_at_5:       0.732  (gate: >= 0.850)  BREACH
keyword_hit:       0.294  (no gate)
refusal_accuracy:  0.000  (gate: >= 0.950)  BREACH — see note below, out of scope here
```

This ADR covers the `recall_at_5` breach only. `refusal_accuracy` is a
separate, still-open issue (`min_retrieval_score` is very likely too low
for bge-m3's real similarity range on this corpus — confirmed by a
4-query spot check during M1.2 and then conclusively by this same eval
run, where all 14 `must_refuse` entries were wrongly answered) and isn't
addressed here.

7 of 46 answerable entries scored `recall_at_5 == 0.0`: `g009`, `g011`,
`g017`, `g031`, `g035`, `g037`, `g044`.

This project's usual instinct for a recall miss is "fix the chunking,
don't lower the threshold." That was checked first: for every one of the
7 entries, the expected content was confirmed **present in the `chunks`
table at exactly the expected page, containing the expected keywords
verbatim** (checked directly against the database, not inferred). This is
not a chunking bug — chunking correctly captured this content. The actual
causes are in retrieval, and they split into three distinct, verified
mechanisms plus two entries that didn't fit any of them cleanly:

**1. German separable verbs stem differently split than written whole.**
Confirmed on `g009`, `g035`, `g044`. A separable verb split into its
natural question word order stems to a different lexeme than its written
infinitive form, and `websearch_to_tsquery` ANDs all terms together, so
one mismatched lexeme fails the whole match:

| Entry | Question fragment | Query stems to | Manual's real form | Stems to |
|---|---|---|---|---|
| g009 | "...schalte ich...**komplett aus**?" | `schalt` | "Klarspüleranlage **ausschalten**" | `ausschalt` |
| g035 | "Wie **stelle** ich **ein**..." | `stell` | "Zeitvorwahl **einstellen**" | `einstell` |
| g044 | "...**bereite** ich...**vor**?" | `bereit` | "Gerät transportieren **vorbereiten**" | `vorbereit` |

**2. Dense embeddings don't reliably separate instructional intent from
adjacent mentions of the same topic.** Confirmed concretely on `g009`:
the real page-29 how-to content ("Klarspüleranlage ausschalten") scores
only 0.683 cosine similarity — but page 55's *status message*
("Klarspüleranlage ist ausgeschaltet") scores 0.793, and page 53's
*troubleshooting entry* ("Kein Klarspüler eingefüllt") scores 0.731.
bge-m3 picks up on shared vocabulary ("Klarspüler") more strongly than it
distinguishes "how do I do X" from "here's a message about X's state."
The right page ranks 7th on dense alone — just outside `top_k=5`.

**3. Vocabulary the manual simply never uses.** Confirmed on `g031`
("Laugenpumpe", the colloquial term for the drain pump — **0 occurrences**
anywhere in the 894-chunk corpus, vs. 4 occurrences of the manual's actual
term, "Abwasserpumpe") and `g017` ("Lämpchen" — 0 occurrences — vs. the
manual's "LED", 2 occurrences). No retrieval tuning bridges a word that
isn't in the source document at all.

**Not root-caused with the same confidence:** `g011` and `g037` don't
cleanly fit any of the three mechanisms above (no separable-verb split,
no obvious missing vocabulary) — most likely a milder case of mechanism 2,
but this wasn't individually confirmed with real numbers the way `g009`
was, and is reported here as an open question rather than a claimed cause.

## Decision

For M1, accept the `recall_at_5` gap (0.732 vs. 0.85) rather than build a
fix now. None of the three confirmed causes are addressable by "fix the
chunking" — the chunker did its job correctly here — and every real fix
below is materially bigger scope than this milestone. Documented here so
a future real deployment (or a future milestone with retrieval-quality
budget) has a concrete, evidence-backed starting menu instead of
rediscovering these from scratch.

## Consequences

**Positive**
- The recall gap is explained by verified root cause, not just a missed
  number — useful for this project and as interview material: the exact
  mechanism is on record, not "recall was low."
- Each failing entry's likely cause (or honestly, its absence of one) is
  documented, so future investigation doesn't restart from zero.

**Negative / accepted costs**
- `make eval`'s `recall_at_5` gate stays breached until one of the
  alternatives below is actually implemented and re-measured;
  `check_thresholds.py` keeps exiting non-zero on this metric.
- Two of the seven failing entries (`g011`, `g037`) remain unexplained.

## Alternatives considered

| Alternative | Why not now |
|---|---|
| Per-object synonym/normalization list (e.g. `Laugenpumpe→Abwasserpumpe`, `Lämpchen→LED`) fed into the lexical query | Directly fixes cause 3, and would help some cause-1 cases too — the cheapest real fix, but still needs a new `object.yaml` schema field and retrieval-code changes; out of scope for closing M1 |
| Smarter German morphological analysis (replace or augment Postgres' snowball stemmer) so `schalte...aus` and `ausschalten` unify | Addresses cause 1 directly, but snowball stemmers don't do this kind of analysis by design — would need a different tool (e.g. a German lemmatizer) in the retrieval path, a real dependency and design change, not a config tweak |
| A different embedding model, or a reranking step, to better separate instructional intent from adjacent mentions | Addresses cause 2, the hardest of the three — a real information-retrieval research problem, not a config fix. Would need real A/B measurement against this same golden set to justify, and any alternative model is still bound by ADR-0004 (Pascal, no compute capability >= 7.0 features) |
| Do nothing; document the causes | **Chosen.** Turns "we don't know why recall missed" into "we know exactly why, for 5 of 7 entries, and what each real fix would take." |

## References

- `docs/benchmarks/eval-latest.json` — the real report this ADR diagnoses (`recall_at_5=0.732`, n=60, 2026-08-20)
- `server/eval/golden_de.yaml` — entries `g009`, `g011`, `g017`, `g031`, `g035`, `g037`, `g044`
- ADR-0004 (int4 quantization, no FP16 on Pascal) — the constraint bounding any future embedding-model alternative
- ADR-0003 (RAG instead of fine-tuning), ADR-0006 (refusal over generation) — the broader retrieval design this gap sits inside

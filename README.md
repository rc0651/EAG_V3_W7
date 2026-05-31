# EAG W7 — SEBI Compliance RAG Agent

## Demo Video
[YouTube link coming soon]

## What this builds
Agent6 + FAISS vector memory. Answers SEBI compliance questions by meaning, not keywords. Built over 6 SEBI circulars, 33 chunks.

## Corpus
| File | Document | Chunks |
|---|---|---|
| sebi_master_circular_stockbrokers.md | Master Circular on Stock Brokers 2024 | 6 |
| sebi_peak_margin_circular.md | Peak Margin & Intraday Leverage | 5 |
| sebi_algo_ibt_circular.md | Algo Trading & IBT Guidelines | 6 |
| sebi_fo_eligibility_retail_2024.md | F&O Eligibility for Retail Investors | 5 |
| sebi_kyc_nomination_circular.md | KYC & Nomination Requirements | 5 |
| sebi_scores_grievance_circular.md | Investor Grievance SCORES 2.0 | 6 |

## Semantic proof
grep -ri "misuse\|misusing" papers/ → no matches
grep -ri "runaway" papers/ → no matches
FAISS finds answers from meaning alone.

## Traces
traces/base/ — a, b, c1, c2, d, e, f1, f2, g, h
traces/custom/ — q1, q2, q3, q4, q5

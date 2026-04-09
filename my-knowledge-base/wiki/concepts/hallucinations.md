---
title: "Hallucinations"
date_created: 2026-04-09
date_modified: 2026-04-09
summary: "AI generating incorrect or fabricated information presented as fact"
tags: [concept, ai-problem]
type: concept
status: draft
---

# Hallucinations

**Category:** AI Behavior Problem
**Severity:** High (impacts reliability and trust)

## Overview

AI hallucinations refer to the phenomenon where large language models generate confident but incorrect or fabricated information. The AI presents these fabrications as facts, making them particularly dangerous because the confident delivery makes them appear credible.

## Why AI Hallucinates

- **Training Data** — Models learn patterns from vast text, including inaccuracies
- **No Truth Gauge** — LLMs don't have built-in fact-checking mechanisms
- **Pattern Completion** — Models complete text based on learned patterns, not truth
- **Token Prediction** — Next-token prediction can lead to plausible-sounding but wrong outputs

## Mitigation Strategies

1. **Prompt Engineering** — Use prompts that encourage uncertainty acknowledgment
2. **Reality Filter** — Instructions to label unverified content with [Inference], [Speculation], [Unverified]
3. **Verification** — Cross-reference outputs with reliable sources
4. **RAG Systems** — Ground outputs in retrieval-augmented data

## Related Sources

- [[minchoi-1964716900660965644-hallucination-prompt]] — ChatGPT prompt that stops hallucinations
- [[rohanpaul_ai-1964529285282086967-reality-filter]] — Reality Filter prompt for reducing hallucinations

## Related Entities

- [[chatgpt]] — Where hallucinations are commonly observed
- [[claude]] — Also susceptible to hallucinations
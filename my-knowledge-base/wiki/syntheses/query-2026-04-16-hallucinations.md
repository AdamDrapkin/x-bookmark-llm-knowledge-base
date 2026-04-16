---
title: "What do we know about preventing AI hallucinations?"
date_created: 2026-04-16
date_modified: 2026-04-16
summary: "The wiki has two source prompts and one concept page on hallucination prevention - the key insight is that mechanical verification指令 work better than hoping for better reasoning"
tags: [query, synthesis, hallucinations]
type: synthesis
status: draft
---

# What do we know about preventing AI hallucinations?

## Quick Answer

The wiki has **two source prompts** and **one concept page** on hallucination prevention. The key insight: the most effective approach is "mechanical" — using repeated verification instruction patterns rather than hoping for better reasoning.

## Sources in the Wiki

### 1. [[minchoi-1964716900660965644-hallucination-prompt]]
This bookmark (posted 2025-09-07) points to a prompt that "literally stops ChatGPT from hallucinating." It's described as a "Reality Filter" - a directive scaffold that makes AI models more likely to admit when they don't know something.

### 2. [[rohanpaul_ai-1964529285282086967-reality-filter]]
This bookmark (also from 2025-09-07) discusses the same "Reality Filter" prompt approach, but from a different author. It has versions for GPT-4, Gemini Pro, Claude, and a universal version. Key requirement: label unverified content with [Unverified] or [Inference] tags.

### 3. [[hallucinations]] (concept page)
The concept page explains why AI hallucinates:
- **Training Data** — Models learn patterns from vast text, including inaccuracies
- **No Truth Gauge** — LLMs don't have built-in fact-checking
- **Pattern Completion** — Models complete based on patterns, not truth
- **Token Prediction** — Next-token prediction leads to plausible-sounding but wrong outputs

Mitigation strategies listed:
1. **Prompt Engineering** — Encourage uncertainty acknowledgment
2. **Reality Filter** — Label unverified content
3. **Verification** — Cross-reference with reliable sources
4. **RAG Systems** — Ground outputs in retrieval-augmented data

## Key Techniques from Sources

### The Reality Filter Prompt

The core mechanism is mechanical:
- Require the model to label any non-factual content with [Unverified] or [Inference]
- Mandate saying "I cannot verify this" when lacking data
- Use repeated verification steps rather than single instructions

From [[rohanpaul_ai-1964529285282086967-reality-filter]]: "It works mechanically — through repeated instruction patterns, not by teaching them 'truth.'"

## Agreements Across Sources

Both source prompts agree:
- Labeling unverified content is effective
- Model versions (GPT-4, Gemini, Claude) all respond to this approach
- "Mechanical" verification beats hoping for better reasoning

## What's Missing / Gaps

- **No quantitative data** — The wiki doesn't have before/after accuracy metrics
- **No recent sources (2025+)** — Could use more recent work on RAG-based approaches
- **No code implementation** — No scripts or tools in wiki output

## Suggested Follow-ups

1. Ingest more recent research on RAG + hallucinations
2. Add actual prompt templates to the wiki
3. Find benchmarks comparingReality Filter vs standard prompting
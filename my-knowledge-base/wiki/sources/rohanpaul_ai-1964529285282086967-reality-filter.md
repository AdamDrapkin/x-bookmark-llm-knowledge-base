---
title: "A Reality Filter - prompt that reduces AI hallucinations"
date_created: 2026-04-09
date_modified: 2026-04-09
summary: "A prompt designed to reduce AI hallucinations by making models label unverified content and admit when they don't know"
tags: [prompt-engineering, ai-prompts, tutorial, hallucinations, reality-filter]
type: source
status: draft
---

# A Reality Filter - prompt that reduces AI hallucinations

**Author:** @rohanpaul_ai
**Category:** prompt-engineering
**Date ingested:** 2026-04-09
**Type:** bookmark

## Summary

This bookmark discusses the "Reality Filter" prompt - a directive scaffold that makes AI models (GPT-4, Gemini Pro, Claude) more likely to admit when they don't know something. The prompt works by requiring the model to label any content that is not directly verifiable with tags like [Unverified] or [Inference], and mandates saying "I cannot verify this" when lacking data.

The key insight is that this approach reduces hallucinations "mechanically—through repeated instruction patterns, not by teaching them 'truth.'" It's a mechanical approach that works through repeated verification steps rather than hoping for better reasoning.

The prompt has versions for GPT-4, Gemini Pro, Claude, and a universal version. This originated from the r/PromptEngineering subreddit.

## Key Takeaways

- The Reality Filter is a permanent directive that requires labeling unverified content
- Works across multiple AI models: GPT-4, Gemini Pro, Claude, and universal version
- Uses [Unverified] or [Inference] tags for non-factual content
- Mandates "I cannot verify this" when lacking data
- The approach is mechanical - using repeated instruction patterns rather than teaching "truth"

## Entities & Concepts

- [[prompt-engineering]]
- [[hallucinations]]
- [[reality-filter]]
- [[ai-reliability]]

## Relation to Other Wiki Pages

This is closely related to the Min Choi bookmark about hallucination reduction - both address the same problem from slightly different angles.

## Notes

- Image was extracted but could not be analyzed - GEMINI_API_KEY not set
- Image saved to: raw/x-article-images/rohanpaul_ai-1964529285282086967-image-1.png
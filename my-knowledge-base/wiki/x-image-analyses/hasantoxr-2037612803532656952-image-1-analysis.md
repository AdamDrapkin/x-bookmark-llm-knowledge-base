---
title: "Image Analysis: hasantoxr - 2037612803532656952"
date_created: 2026-04-14
date_modified: 2026-04-14
summary: "Text document analysis (text content) from 2037612803532656952 by hasantoxr"
tags: [image-analysis, open-source]
type: source
status: draft
---

# Image Analysis: hasantoxr - 2037612803532656952

**Source:** [Tweet](https://x.com/hasantoxr/status/2037612803532656952)

## Image Type: Text Document

**Document Type:** text content

## Extracted Text

## Extracted Text

Insanely Fast Whisper

An opinionated CLI to transcribe Audio files w/ Whisper on-device! Powered by 🤖 Transformers, Optimum & flash-
attn

TL;DR - Transcribe 150 minutes (2.5 hours) of audio in less than 98 seconds - with OpenAI's Whisper Large v3.
Blazingly fast transcription is now a reality!⚡

pipx install insanely-fast-whisper==0.0.15 --force

Not convinced? Here are some benchmarks we ran on a Nvidia A100 - 80GB ⚡

Optimisation type

Time to Transcribe (150 mins of
Audio)

large-v3 (Transformers) (fp32)

~31 (31 min 1 sec)

large-v3 (Transformers) (fp16 + batching [24] +
bettertransformer )

~5 (5 min 2 sec)

large-v3 (Transformers) (fp16 + batching [24] + Flash
Attention 2 )

~2 (1 min 38 sec)

distil-large-v2 (Transformers) (fp16 + batching [24] +
bettertransformer )

~3 (3 min 16 sec)

distil-large-v2 (Transformers) (fp16 + batching [24] + Flash
Attention 2 )

~1 (1 min 18 sec)

large-v2 (Faster Whisper) (fp16 + beam_size [1] )

~9.23 (9 min 23 sec)

large-v2 (Faster Whisper) (8-bit + beam_size [1] )

~8 (8 min 15 sec)



## Summary

Insanely Fast Whisper  An opinionated CLI to transcribe Audio files w/ Whisper on-device! Powered by



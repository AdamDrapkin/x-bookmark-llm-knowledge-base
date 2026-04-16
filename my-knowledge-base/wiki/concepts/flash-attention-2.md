---
title: "Flash Attention 2"
date_created: 2026-04-16
date_modified: 2026-04-16
summary: "Flash Attention 2 provides 2-4x speedup over standard attention implementations while dramatically reducing memory usage, making it essential for training and inference of large language models."
tags: [concept]
type: concept
status: final
---

# Flash Attention 2

**Category:** Technique
**Definition:** An optimized attention mechanism algorithm that dramatically accelerates transformer model inference by improving memory efficiency and computational speed through tiled computation and hardware-aware implementation.

## Overview

Flash Attention 2 is an evolution of the original Flash Attention technique, designed to maximize hardware utilization on modern GPUs for attention computation in transformer models. It achieves significant speedups and memory reduction by avoiding materialization of the full attention matrix, instead using a divide-and-conquer approach that processes attention in blocks that fit in fast on-chip SRAM.

## Related Sources

- [[hasantoxr-2037612803532656952]]

## Related Entities

- [[nvidia]] — Related entity

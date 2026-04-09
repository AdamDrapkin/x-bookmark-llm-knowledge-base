---
title: "Wiki Log"
date_created: 2026-04-08
date_modified: 2026-04-09
summary: "Changelog of all wiki operations"
tags: [log, changelog]
type: log
status: draft
---

# Wiki Log

## 2026-04-09 - Batch 1 | 10 Sources Processed

### Operation: BACKLOG PROCESS

Processed first 10 classified bookmarks from prompt-engineering category.

#### Sources Created (10)

| File | Author | Topic |
|------|--------|-------|
| [[godofprompt-1967590989062664316-book-writing-prompt]] | godofprompt | Claude Opus 4.1 Prompt to automate writing an entire book |
| [[minchoi-1964716900660965644-hallucination-prompt]] | minchoi | ChatGPT prompt that stops hallucinations |
| [[rohanpaul_ai-1964529285282086967-reality-filter]] | rohanpaul_ai | Prompt that reduces ChatGPT hallucinations |
| [[alex_prompter-1953861679248560379-ai-prompt-library]] | alex_prompter | AI prompt library |
| [[godofprompt-1970101500396634129-ai-prompt-library]] | godofprompt | AI prompt library |
| [[godofprompt-1970086539402121690-prompt-engineer-protocol]] | godofprompt | Protocol for Designing Prompts |
| [[mindbranches-1974621848844616006-video-prompt-styles]] | MindBranches | Styles to try in AI video prompts |
| [[godofprompt-1974425241582796820-anthropic-prompting-style]] | godofprompt | Anthropic's internal prompting style |
| [[godofprompt-1974102012670407035-depth-prompt-framework]] | godofprompt | D-E-P-T-H Prompt Framework |
| [[shushant_l-1974097166454174149-perplexity-research-prompts]] | shushant_l | 10 Perplexity Deep Research prompts |

#### Concepts Updated (2)
- [[prompt-engineering]] — Added new techniques from batch 1
- [[video-prompting]] — New concept from MindBranches video prompt styles

#### Entities Added (3)
- [[anthropic]] — From godofprompt's Anthropic prompting style analysis
- [[perplexity]] — From shushant_l's Perplexity Deep Research prompts
- [[god-of-prompt]] — From multiple godofprompt sources

#### Media Analyses
- **Images:** 7 analyzed (gemini-2.0-pro-vision)
- **Videos:** 2 analyzed

#### Index Updates
- Master wiki/index.md updated (16 sources, 6 concepts, 7 entities)
- wiki/sources/_index.md updated (16 sources)
- wiki/concepts/_index.md updated (6 concepts)
- wiki/entities/_index.md updated (7 entities)

### Operation: INGEST

Ingested first 5 bookmarks from SQLite database `~/.ft-bookmarks/bookmarks.db`.

#### Sources Created (5)

| File | Author | Topic |
|------|--------|-------|
| [[robert-youssef-2026-claude-ai-business]] | Robert Youssef | Claude + Andrew Ng AI agent business framework |
| [[jb-2026-workflow-play]] | J.B. | AI wrapper business strategy |
| [[meng-to-2026-designmd-tool]] | Meng To | DESIGN.md tool for site recreation |
| [[n8n-2026-smart-alerting]] | n8n.io | Smart alert filtering workflow |
| [[louis-gleeson-2026-feynman-agent]] | Louis Gleeson | Feynman open source research agent |

#### Concepts Created (5)

| File | Concept |
|------|---------|
| [[agentic-ai]] | AI systems that autonomously plan and execute multi-step tasks |
| [[ai-business]] | Business models leveraging AI agents |
| [[workflow-automation]] | Automating business processes through workflows |
| [[prompt-engineering]] | Crafting effective AI instructions |
| [[research-automation]] | Using AI to automate research processes |

#### Entities Created (4)

| File | Entity |
|------|--------|
| [[claude]] | Anthropic's AI assistant |
| [[andrew-ng]] | AI researcher, Google Brain founder |
| [[n8n]] | Open-source workflow automation platform |
| [[feynman]] | Open source AI research agent |

#### Cross-References Added

- All source pages linked to relevant concepts and entities
- All concept pages linked to source pages
- All entity pages linked to source pages
- Created bidirectional links where appropriate

#### Index Updated

- wiki/index.md created with all pages and categorisation

## 2026-04-09 - Raw Source Processing

### Operation: INGEST (continued)

Processed raw sources for all 5 bookmarks following browser.md SOP.

#### Browser Verification

Verified each tweet using cookie-injected browser to identify content types:

| Tweet | Type Found | Additional Content |
|-------|-----------|---------------------|
| Robert Youssef | Single tweet | None |
| J.B. | Single tweet | None |
| Meng To | Video tweet | 50-sec demo video |
| n8n.io | Image + link | Workflow screenshot |
| Louis Gleeson | Image + replies | GitHub link in reply |

#### Raw Files Created

| File | Type | Content |
|------|------|---------|
| `x-threads/rryssf-2041169193140408574-thread.md` | Thread | Robert Youssef tweet thread |
| `x-article-images/rryssf-2041169193140408574-image-1.jpg` | Image | Tweet image |
| `x-video-transcripts/vibemarketer-2041159211858452840-transcript.txt` | Video transcript | Morphic demo video |
| `x-external-links/vibemarketer-2041159211858452840-link-morphic.txt` | External link | Morphic AI website |
| `x-video-transcripts/mengto-2041141824283365521-video-note.txt` | Video note | Silent demo (no audio) |
| `x-article-images/n8nio-2041078519623520666-image-1.jpg` | Image | Workflow screenshot |
| `x-external-links/n8nio-2041078519623520666-link-n8nio.txt` | External link | n8n workflow template |
| `x-article-images/aigleeson-2041073339616387468-image-1.jpg` | Image | Feynman landing page |
| `x-threads/aigleeson-2041073339616387468-tweet.md` | Thread | Louis Gleeson tweet + replies |
| `x-external-links/aigleeson-2041073339616387468-link-github-feynman.txt` | External link | Feynman GitHub repo |

#### Source Pages Updated

Updated all source wiki pages with raw source references:

- [[robert-youssef-2026-claude-ai-business]]
- [[jb-2026-workflow-play]]
- [[meng-to-2026-designmd-tool]]
- [[n8n-2026-smart-alerting]]
- [[louis-gleeson-2026-feynman-agent]]

Each source page now includes:
- Content type (tweet/thread/video/image)
- Media details
- External link references
- Raw file paths

## 2026-04-09 - Lint Report

### Operation: LINT

Ran comprehensive lint audit on all 16 source pages, 6 concepts, and 7 entities.

#### Results
- 🔴 **5 Broken Links** — Missing entity/concept pages referenced in wikilinks
- ✅ **0 Missing Frontmatter** — All pages properly formatted
- ✅ **0 Contradictions** — No conflicting claims detected
- ✅ **0 Stale Claims** — All content is current

#### Broken Links Identified
Missing pages: [[pricing]], [[anthropic]], [[chatgpt]], [[hallucinations]], [[mindbranches]], [[alerting]], [[monitoring]], [[perplexity]]

#### Report
- [[lint-2026-04-09]] — Full lint report saved to wiki/outputs/

#### Index Updates
- wiki/index.md updated with Maintenance category
- wiki/outputs/_index.md updated with lint report entry
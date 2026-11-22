---
name: deep-research-and-synthesis
description: Multi-source research, literature and document synthesis, source triangulation, fact verification, knowledge management, and technical documentation across online and offline environments.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [research, synthesis, knowledge-management, technical-documentation, fact-verification]
    related_skills: [research-paper-writing, llm-wiki, duckduckgo-search, arxiv]
---

# Deep Research, Source Analysis & Knowledge Synthesis

Use this skill when conducting comprehensive research, literature reviews, comparative technical evaluations, policy briefs, or knowledge-base synthesis.

## Hybrid Online / Offline Research Methodology

1. **Multi-Channel Discovery**
   - **Local Corpus & Memory**: Always search local workspace documents (`search_files`, `read_document`, `read_file`), persistent memory (`memory`), and prior conversations (`session_search`) first.
   - **Online Sources (when connected)**: Use `web_search` and `web_extract` across primary, authoritative sources. If connectivity drops mid-research, TchuekaM's offline recovery fallback seamlessly returns local findings so synthesis continues uninterrupted.

2. **Source Triangulation & Epistemic Rigor**
   - Cross-check factual claims, statistics, and dates across independent sources.
   - Clearly distinguish verified empirical facts from analytical inferences or assumptions.
   - Cite concrete sources (file paths + section/page for local documents; URLs + publication titles for web sources).

3. **Structured Deliverable Synthesis**
   - Organize complex research outputs into clear sections: **Executive Synthesis**, **Methodology & Sources**, **Key Findings & Comparative Matrix**, **Implications & Recommendations**, and **References**.
   - Persist requested research reports to disk and verify with `autonomous_plan(action="verify")`.

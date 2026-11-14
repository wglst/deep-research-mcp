============================================================
RESEARCH REPORT
============================================================
Task ID: resp_07c84eb8db09888c016af899d6d40887d0bd2e52d2b024c950
Total steps: 5
Search queries: 2
Citations: 6
Execution time: 67.41s
Provider note: Code Interpreter is not available for openai-codex; research completed with web search only.

**You can build an AI-based research station as an app that searches trusted sources, reads your documents, analyzes evidence, and produces reports with citations.** Start with one focused workflow—not a fully autonomous “AI scientist.”

I’ll assume you mean a **software research workspace**. If you mean a physical station with sensors, cameras, or laboratory equipment, the design would be different.

## 1. Define what the station should do

For a first version, I recommend these five capabilities:

| Capability | What the user gets |
|---|---|
| Ask a research question | A clear research plan |
| Search the web | Relevant sources with publication dates |
| Upload documents | Answers grounded in their PDFs and reports |
| Compare evidence | Tables of findings, numbers, and disagreements |
| Generate a report | A summary with citations and downloadable results |

**Example task:** “Compare three water-purification technologies using published evidence on cost, energy consumption, and effectiveness.”

The underlying building blocks already exist: OpenAI’s documented tools include web search, file search, and connections to external capabilities. Web search can return sourced citations; file search retrieves relevant material from uploaded documents using semantic and keyword search. These are implementation options, not requirements to use one vendor. ([developers.openai.com](https://developers.openai.com/api/docs/guides/tools?utm_source=openai))

## 2. Use a simple architecture

My recommended starting design is:

```text
User interface
      ↓
Research controller
      ↓
Web search + document retrieval
      ↓
Evidence store
      ↓
Analysis and report generation
      ↓
Citation checks + human review
```

### Suggested stack

These are **design recommendations**, rather than a benchmarked comparison of products.

| Layer | Suggested starting choice |
|---|---|
| Interface | A simple Python web interface |
| Backend | Python |
| AI | A hosted model API with tool support |
| Public research | Web-search tool |
| Private documents | Hosted file search initially |
| Project storage | SQLite for the prototype |
| Files | Local storage initially |
| Reports | Markdown and CSV first; PDF later |

Keep your first version to **one controller with clearly defined steps**. You can add specialized agents later if testing shows a benefit. OpenAI’s practical agent-building guidance similarly recommends maximizing a single agent before introducing multi-agent complexity. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf?_bhlid=b6ece51f84e92792c815104ce51a65b69a818537&utm_source=openai))

## 3. Build the workflow in six steps

### Step 1 — Capture the research brief

Ask users for:

- Research question.
- Subject area.
- Date range and geographic scope.
- Preferred or excluded sources.
- Desired output.
- Time and spending limits.

For example:

> Compare residential solar battery technologies in the United States. Prioritize official specifications and independent studies. Return a comparison table and explain uncertainties.

### Step 2 — Create a research plan

Have the model produce subquestions and search queries before collecting evidence. Let the user approve the plan.

Suggested output:

```text
Question
Subquestions
Search queries
Preferred source types
Required comparison fields
Stopping conditions
```

### Step 3 — Retrieve sources

Use two separate routes:

- **Web research:** public information and recent developments.
- **Document research:** uploaded papers, internal reports, and notes.

OpenAI’s Responses API supports web-search citation annotations containing the source URL, title, and citation location. Its hosted file-search tool requires uploaded files and a vector store; you can also request the retrieved search results for inspection. ([developers.openai.com](https://developers.openai.com/api/docs/guides/tools-web-search?utm_source=openai))

### Step 4 — Save structured evidence

**Do not save only the AI’s final answer.** My recommendation is to store an evidence record for each important finding:

```text
claim_id
claim_text
supporting_passage
source_title
source_url_or_file_id
author_or_organization
publication_date
retrieval_date
page_or_section
units_and_population
limitations
```

This gives reviewers something concrete to inspect and makes later updates easier.

### Step 5 — Analyze and write

Require the report to separate:

1. **Findings directly supported by sources.**
2. **Calculations derived from source data.**
3. **Interpretations or hypotheses.**
4. **Unknowns and conflicting evidence.**

For numerical comparisons, preserve units, time periods, and denominators. My suggested rule is: **if two figures are not comparable, explain why instead of ranking them.**

### Step 6 — Verify before publishing

Add checks for:

- Missing citations.
- Citations that do not support the claim.
- Incorrect arithmetic.
- Duplicate sources presented as independent evidence.
- Outdated information.
- Unsupported conclusions.

A second model pass can flag problems, but should not be your sole approval mechanism. NIST identifies confidently stated false content—“confabulation”—and inappropriate human reliance as generative-AI risks. ([nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/AI/NIST.AI.600-1.pdf?utm_source=openai))

## 4. Set measurable acceptance criteria

The following are **proposed prototype targets, not industry benchmarks**:

| Metric | Initial target |
|---|---:|
| Test questions | 30 representative questions |
| Important factual claims with citations | 100% |
| Sampled citations that actually support their claims | At least 95% |
| Fabricated references in the test set | 0 |
| Research-run spending cap | Set and enforced per run |
| Human review | Required before external publication |

Track **cost per completed report, completion time, and reviewer corrections**. These can become a dashboard showing whether each change improves quality or merely increases spending.

## 5. Add security from the beginning

My recommended minimum controls are:

- Keep API keys on the server, not in browser code.
- Restrict each user to their own documents.
- Treat downloaded pages and PDFs as untrusted content.
- Start with read-only tools.
- Require approval before sending messages, changing files, or running external actions.
- Run any generated analysis code in an isolated environment.
- Set limits on tool calls, runtime, and spending.

These controls address risks highlighted in agent-safety guidance, including malicious instructions embedded in external content and unsafe tool use. They reduce risk; they do not guarantee safety. ([developers.openai.com](https://developers.openai.com/api/docs/guides/agent-builder-safety?utm_source=openai))

## 6. A practical build sequence

For a small prototype, I would use this sequence:

1. **Question → web research → cited answer.**
2. Add document uploads and document citations.
3. Add the structured evidence store.
4. Add comparison tables and CSV export.
5. Test against your 30-question evaluation set.
6. Add authentication, quotas, monitoring, and deployment controls.

**My recommendation:** build an **“ask → retrieve → evidence table → cited report”** system first. Defer autonomous experiments, many-agent teams, and expensive hardware until you know what your users actually need.

### Source register

| Publisher | Source | Type |
|---|---|---|
| OpenAI | *Using tools; Web search; File search* | Official implementation documentation. ([developers.openai.com](https://developers.openai.com/api/docs/guides/tools?utm_source=openai)) |
| OpenAI | *A Practical Guide to Building Agents; Safety in Building Agents* | Architecture and security guidance. ([cdn.openai.com](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf?_bhlid=b6ece51f84e92792c815104ce51a65b69a818537&utm_source=openai)) |
| NIST | *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*, NIST AI 600-1, 2024 | Government risk-management publication. ([nist.gov](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence?trk=article-ssr-frontend-pulse_little-text-block&utm_source=openai)) |

**Are you building this for academic research, business research, or a physical laboratory—and what is your coding experience and budget?**

============================================================
CITATIONS
============================================================
1. [Using tools | OpenAI API](https://developers.openai.com/api/docs/guides/tools?utm_source=openai)
2. [A practical](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf?_bhlid=b6ece51f84e92792c815104ce51a65b69a818537&utm_source=openai)
3. [Web search | OpenAI API](https://developers.openai.com/api/docs/guides/tools-web-search?utm_source=openai)
4. [Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile](https://nvlpubs.nist.gov/nistpubs/AI/NIST.AI.600-1.pdf?utm_source=openai)
5. [Safety in building agents | OpenAI API](https://developers.openai.com/api/docs/guides/agent-builder-safety?utm_source=openai)
6. [Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence?trk=article-ssr-frontend-pulse_little-text-block&utm_source=openai)
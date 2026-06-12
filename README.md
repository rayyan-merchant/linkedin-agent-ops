# LinkedIn Agent Ops

A private AI research and content-planning system for a production-focused AI
engineer.

It includes:

- A scheduled Daily AI Brief from arXiv, Hacker News, GitHub, and curated feeds
- A Post Architecture Agent for hooks, structure, format, and discussion prompts
- A full-paper Paper Brief Agent with page-level evidence
- A Carousel Architect with structured slides and Marp export
- A Performance Analyzer driven by computed LinkedIn metrics
- A Cricket CV Build Log Agent that connects engineering progress to cricket meaning

FastAPI provides typed agent endpoints, Streamlit provides the local interface,
and Google Sheets stores selected research, analytics, and compact run history.
Gemini is the primary model with Groq fallback.

Every manual agent uses structured outputs, grounded evidence, deterministic
checks, a validation pass, and one repair attempt. The outputs support human
thinking and writing; the system does not publish posts or automate engagement.

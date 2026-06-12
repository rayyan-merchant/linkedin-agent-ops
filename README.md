# Daily AI Brief

An automated research pipeline that delivers a curated AI intelligence brief
every morning.

It collects recent signals from:

- arXiv
- Hacker News
- GitHub
- Curated AI and engineering RSS feeds

The pipeline ranks and deduplicates candidates, generates concise summaries and
content angles with Gemini or Groq, emails the brief through Gmail, and archives
selected items in Google Sheets.

It runs daily at 7:30 AM PKT through GitHub Actions and includes deterministic
fallbacks, partial-failure handling, and duplicate-delivery protection.

The output is research material for human-written LinkedIn content, not
automatically generated posts.

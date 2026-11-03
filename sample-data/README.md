# Fictional demo catalogue

`catalogue.json` contains six fictional artists, twelve release editions and thirty-six recordings. Names, dates, tags and durations are illustrative, not sourced real-world claims. No followers, streaming counts, popularity or growth figures are supplied.

After migrations, run `cd backend && uv run python -m app.seed` from the repository root. Loading is explicit and idempotent, uses `provider=demo` and preserves separate source mappings. Never present these records as live music data.

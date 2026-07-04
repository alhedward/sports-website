# Community discovery and curation pipeline

The long-term goal is for visitors to help build the sporting-body database without turning the site into an unmoderated link farm.

## Current POC behaviour

- Public visitors can submit a suggested sporting body or pathway through the site.
- Suggestions are stored in the `suggestions` DynamoDB table with `status = pending_review`.
- Suggestions are not automatically published into `sport_bodies`.
- Search still uses curated tables only: `sport_bodies`, `tournaments`, `players` pathway profiles, and `top_players` spotlights.

## Why moderation matters

The site mission is based on trust. User submissions should be reviewed for:

- official or clearly legitimate source URL,
- sport-body relevance,
- safe participation messaging,
- accessibility and inclusion value,
- duplicate entries,
- commercial conflicts,
- spam or misleading claims.

## Proposed OpenAI-assisted later stage

A later admin-only Lambda can use the OpenAI Responses API with the `web_search` tool to research a submitted organisation and produce a review packet.

Suggested flow:

1. User submits a body or pathway.
2. Submission lands in `suggestions` as `pending_review`.
3. Admin clicks `research` in a future review dashboard.
4. Backend sends a constrained prompt to OpenAI asking for:
   - official organisation name,
   - official website,
   - sport / discipline,
   - region,
   - participation pathways,
   - inclusion/disability notes,
   - source citations,
   - risk flags.
5. AI output is stored as `research_draft`, not published.
6. Admin approves, edits, rejects, or merges the entry.
7. Approved records move into `sport_bodies` and become searchable.

## Guardrails

- Do not allow public users to directly trigger expensive AI searches without rate limiting and abuse controls.
- Do not auto-publish AI output.
- Require visible citations for any AI-researched source claims.
- Keep a review trail: who approved, when, and what source URLs were checked.
- Add CAPTCHA or another bot-control mechanism before taking the suggestion form fully public.

## Top-player spotlight approach

Top-player cards should inspire participation without pretending the POC has an official statistics licence.

For each spotlight:

- show the sport genre,
- explain why they are featured,
- link to official sources,
- keep high-level achievements until verified,
- add detailed lifetime stats only when checked against official/approved data sources.

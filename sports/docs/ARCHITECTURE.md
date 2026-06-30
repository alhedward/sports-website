# Architecture

The POC stays deliberately serverless:

- CloudFront distributes a static frontend.
- S3 stores the site files privately behind CloudFront Origin Access Control.
- API Gateway exposes a small HTTP API.
- Python Lambda reads DynamoDB tables.
- A separate Python ingest Lambda seeds curated public-link data.
- DynamoDB uses on-demand billing and point-in-time recovery.
- ACM and Route 53 support `https://sports.vk2ale.com` when the hosted zone is in AWS.

## API routes

- `GET /health`
- `GET /organisations`
- `GET /organisations/{id}`
- `GET /tournaments`
- `GET /tournaments/{id}`
- `GET /events`
- `GET /players`
- `GET /players/{id}`
- `GET /search?q=term`

`/organisations` is the key route for the aggregator concept. `/players` is retained for compatibility with the earlier POC, but the seeded records are participation/pathway profiles rather than athlete-stat pages.

## Why this shape

The site should benefit sporting bodies by sending visitors to official sites rather than copying their content. The database stores curated summaries, tags and official URLs, not scraped pages.

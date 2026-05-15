# Local deployment

Run the full MVP stack with:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Services:
- Web app: http://localhost:3000
- API gateway: http://localhost:4000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

For local development without containers, copy `.env.example`, run `npm install`, then run `npm run dev`.

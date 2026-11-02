# LoL Coach web frontend

React, TypeScript, Vite and Tailwind. It reads the FastAPI app through a dev
proxy: `/api/...` goes to `http://localhost:8000/...`.

```sh
docker compose up -d        # the API and database
cd web
npm install
npm run dev                 # http://localhost:5173
npm test                    # unit tests
```

The page draws and formats; it never computes a statistic. Verdicts, gaps,
margins and percentages all come from the API, and the headline sentence is
written by code from the API's findings.

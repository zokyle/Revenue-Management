# Revenue-Management

Two independent FastAPI applications share this repository and its Python
dependencies:

| App | Directory | Run | What it does |
|-----|-----------|-----|--------------|
| Hotel revenue management | `app/` | `uvicorn app.main:app --reload` | demand forecasting, dynamic pricing, overbooking, PMS integrations |
| **Caddie** - golf strategy agent | `golf/` | `uvicorn golf.main:app --reload --port 8001` | learns your golf game from logged rounds and builds hole-by-hole strategies for any course, with the goal of breaking 80 |

```bash
pip install -r requirements.txt
cp .env.example .env
python scripts/seed_golf.py      # demo golfer, course and 12 rounds for the golf app
python -m pytest -q              # both apps' test suites
```

See [`golf/README.md`](golf/README.md) for how the golf agent works (with
pictures and analogies), the data-collection workflow, and the API.

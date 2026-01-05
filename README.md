# Concert Management Service

Manages concert schedules, CRUD operations for concerts, and integrates with Facebook Events via Kafka.

## Features

- Concert CRUD operations
- Kafka consumer for event updates
- gRPC server for event synchronization
- Optimistic locking for concurrent edits

## Development

```bash
cd backend/concert-management
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8001
```


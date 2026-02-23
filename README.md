# SDC Test Prioritization Service

This repository implements a REST API for uploading, prioritizing, and evaluating Self-Driving Car (SDC) simulation test suites. The service aims to provide to users a seamless integration of their prioritization strategies, by adding them into inner layer (strategies.py). It has been followed the Open/Close methodology to be compliant for future gRPC integration. It has been inspired by the [SDC Testing Competition 2026 – Test Prioritization Track](https://github.com/christianbirchler-org/sdc-testing-competition).

## Service Architecture

The SCD Test Prioritization Service follows a **layered architecture** as depicted below:

```
┌───────────────────────────────────────────────────────┐
│  API / Transport Layer                                │
│  routers/test_suite_router.py, history_router.py      │
│  FastAPI endpoints, HTTP status codes, error mapping  │
│  Pydantic models for request/response validation      │
└───────────────────────┬───────────────────────────────┘
                        │
┌───────────────────────│──────────────────────────────┐
│  Domain Logic Layer                                   │
│  domain/test_suite_service.py    (orchestration)      │
│  domain/strategies.py            (Strategy Pattern)   │
│  domain/evaluation.py            (mock + APFD metric) │
│  TestCaseData: transport-agnostic domain object       │
└───────────────────────┬───────────────────────────────┘
                        │ 
┌───────────────────────│───────────────────────────────┐
│  Persistence                                          │
│  persistence/postgres_repository.py  (metadata)       │
│  persistence/mongo_repository.py     (road points)    │
│  Domain exceptions propagated upward                  │
└───────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Strategy Pattern** with ABC — new prioritization algorithms are added by subclassing `PrioritizationStrategy` and registering in `STRATEGY_REGISTRY`. No existing code is modified (Open/Closed Principle).
- **Transport-agnostic domain objects** — Inner layer: strategies operate on `TestCaseData` (a plain dataclass with raw road points), decoupled from both Pydantic (REST) and Protobuf (gRPC), or different transportation layer.
- **Dual persistence** — PostgreSQL stores suite metadata and evaluation history (relational, queryable); MongoDB stores full road point documents (flexible, document-oriented).
- **Stateless prioritization** — the `GET /prioritization` endpoint computes ordering on the fly without storing results, keeping the system stateless where possible.
- **Budget mode as optional field** — evaluation supports both base and budget modes via a single endpoint with an optional `budget` parameter. No separate endpoints, no architectural changes.
- **Routers** - the two routers handled different data and have been separated for REST best practices.

## REST API Endpoints

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/v1/test-suite/` | Upload a test suite | 201 |
| `GET` | `/v1/test-suite/prioritization` | Compute prioritized order (stateless) | 200 |
| `POST` | `/v1/test-suite/evaluation` | Evaluate and store report | 201 |
| `GET` | `/v1/history/` | Export evaluation history as CSV | 200 |

Available strategies: `longest-first`, `total-distance-first`, `euclidean-outlier-first`, `mahalanobis-outlier-first`, `less-safe-first`.

---

## Getting Started

### Prerequisites

- **Docker** (Docker Compose) — recommended
- **Python 3.11+** — for local development
- `requests` library — for running the experiment script

---

### Option 1: Docker Compose (recommended)

#### 1. Clone and configure

```bash
git clone https://github.com/Mascele11/sdc-test-prioritization-service.git
cd sdc-test-prioritization-service
```

Create (or verify) the `.env` file in the project root:

```env
# .env (Docker Compose — uses container hostnames)
MONGODB_URI=mongodb://mongodb:27017
POSTGRESQL_URI=host=postgres port=5432 dbname=sdc_testing user=sdc_user password=sdc_password
```

#### 2. Build and start

```bash
docker compose build --no-cache && docker compose up -d
```

Verify all services are healthy or using docker Desktop App:

```bash
docker compose ps
```

The API will be available at `http://localhost:8000`. Interactive Swagger docs: `http://localhost:8000/docs`.

#### 4. Stop

```bash
docker compose down
```

Full reset (wipe databases):

```bash
docker compose down -v && docker compose build --no-cache && docker compose up -d
```

---

### Option 2: Local Development

#### 1. Start databases locally

```bash
docker run -d --name postgres-local -p 5432:5432 -v postgres-data:/var/lib/postgresql/data -e POSTGRES_USER=sdc_user -e POSTGRES_PASSWORD=sdc_password -e POSTGRES_DB=sdc_testing postgres:16
docker exec -i postgres-local psql -U sdc_user -d sdc_testing < ./db/init.sql
docker run -d --name mongo-local -p 27017:27017 mongo:7 
```

#### 2. Create a local `.env` file

```env
# .env.local (local run — uses localhost)
MONGODB_URI=mongodb://localhost:27017
POSTGRESQL_URI=host=localhost port=5432 dbname=sdc_testing user=sdc_user password=sdc_password
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Run the server

```bash
# Load local env and start
export $(cat .env.local | xargs) && python main.py
```

The API will be available at `http://localhost:8000`. Interactive Swagger docs: `http://localhost:8000/docs`.

---

## API Usage Examples

### 1. Upload a test suite

```bash
curl -X POST http://localhost:8000/v1/test-suite/ \
  -H "Content-Type: application/json" \
  -d '{
    "testSuiteId": "suite_01",
    "tests": [
      {
        "testId": "TC_001",
        "roadPoints": [
          {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
          {"sequenceNumber": 1, "x": 5.0, "y": 1.0},
          {"sequenceNumber": 2, "x": 10.0, "y": 3.0}
        ]
      },
      {
        "testId": "TC_002",
        "roadPoints": [
          {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
          {"sequenceNumber": 1, "x": 10.0, "y": 0.0},
          {"sequenceNumber": 2, "x": 10.0, "y": 10.0}
        ]
      }
    ]
  }'
```

Response (201):
```json
{
  "testSuiteId": "suite_01",
  "testCount": 2,
  "createdAt": "2026-02-23T10:00:00Z",
  "message": "Test suite uploaded successfully."
}
```

### 2. Prioritize a test suite

```bash
curl "http://localhost:8000/v1/test-suite/prioritization?testSuiteId=suite_01&strategy=euclidean-outlier-first"
```

Response (200):
```json
{
  "testSuiteId": "suite_01",
  "strategy": "euclidean-outlier-first",
  "orderedTests": ["TC_002", "TC_001"]
}
```

### 3. Evaluate — Base mode (all tests executed)

```bash
curl -X POST http://localhost:8000/v1/test-suite/evaluation \
  -H "Content-Type: application/json" \
  -d '{
    "testSuiteId": "suite_01",
    "strategy": "euclidean-outlier-first"
  }'
```

Response (201):
```json
{
  "evaluationId": 1,
  "testSuiteId": "suite_01",
  "strategy": "euclidean-outlier-first",
  "failuresDetected": 1,
  "executionCost": 5,
  "score": 0.75
}
```

### 4. Evaluate — Budget mode (execution capped at N road points)

```bash
curl -X POST http://localhost:8000/v1/test-suite/evaluation \
  -H "Content-Type: application/json" \
  -d '{
    "testSuiteId": "suite_01",
    "strategy": "euclidean-outlier-first",
    "budget": 4
  }'
```

The `budget` field is optional. When omitted, all tests execute fully (base mode). When provided, execution stops when the budget is exhausted. The report reflects partial execution.

### 5. Export evaluation history

```bash
curl http://localhost:8000/v1/history/ -o evaluation_history.csv
```

---

## Running the Experiment

The `experiment.py` script automates the full workflow: upload test suites from competition data, evaluate with all strategies, and export results.

### Prerequisites

```bash
pip install requests
```

### Usage

Place `sdc-test-data.json` (competition test data) in the project root, then:

```bash
# Base mode — evaluate all suites with all strategies
python experiment.py --data sdc-test-data.json

# Budget mode — cap execution at 100 road points per evaluation
python experiment.py --data sdc-test-data.json --budget 100
```

The script will:
1. Load and transform 956 competition test cases into 96 suites of 10
2. Upload all suites via `POST /v1/test-suite/`
3. Evaluate each suite with all 5 strategies (480 evaluations)
4. Print average APFD scores per strategy
5. Export per-strategy CSV reports to `experiments/`

### Example output

```
============================================================
  EXPERIMENT RESULTS
============================================================
  longest-first              avg APFD = 0.5091  (n=96)
  euclidean-outlier-first    avg APFD = 0.6578  (n=96)
  mahalanobis-outlier-first  avg APFD = 0.6168  (n=96)
  less-safe-first            avg APFD = 0.6402  (n=96)
============================================================
```

---

## Project Structure

```
sdc-test-prioritization-service/
├── main.py                          # FastAPI app entry point + lifespan
├── docker-compose.yml               # MongoDB + PostgreSQL + Prioritizer
├── Dockerfile                       # Multi-stage Python 3.11 image
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables (Docker)
├── config/
│   └── config.yml                   # Server, logging, DB config (non-sensitive)
├── db/
│   └── init.sql                     # PostgreSQL schema (auto-runs on first start)
├── experiment.py                    # Automated experiment runner
├── experiments/                     # Exported CSV evaluation reports
├── logs/                            # Rotating log files
├── data/sample_tests/               # Sample test data
└── src/sdc_prioritizer/
    ├── __init__.py                  # Logging bootstrap
    ├── config/                      # Pydantic-validated YAML config
    ├── data_models/
    │   ├── api_models.py            # Pydantic request/response models
    │   └── error_responses.py       # Standardized error format
    ├── domain/
    │   ├── strategies.py            # Strategy Pattern + feature extraction
    │   ├── evaluation.py            # Mock failure function + APFD metric
    │   └── test_suite_service.py    # Service orchestrator
    ├── persistence/
    │   ├── mongo_repository.py      # MongoDB road points storage
    │   └── postgres_repository.py   # PostgreSQL metadata + history
    ├── routers/
    │   ├── test_suite_router.py     # Endpoints 1-3
    │   └── history_router.py        # Endpoint 4
    └── utils/
        ├── exceptions.py            # Domain exceptions
        ├── error_handlers.py        # Global FastAPI error handlers
        └── logging.py               # Console + rotating file logging
```

---

## References

- [SDC Testing Competition 2026](https://github.com/christianbirchler-org/sdc-testingcompetition/blob/main/competitions/2026.md)
- APFD metric: [Birchler et al., 2025](https://doi.org/10.48550/arXiv.2504.10313)
- Road Safety features and Shoelace area: [Birchler et al., 2021](https://doi.org/10.48550/arXiv.2111.04666)

# ACME Corp Model Registry

Team project repository for ECE 46100 Software Engineering

## Team Members

- **Dylan Brannick**
- **James Neff**
- **Herbert Alexander De Bruyn**
- **Joshua LeBlanc**

## Project Overview

ACME Corp Model Registry is a comprehensive machine learning artifact management platform designed to centrally manage and evaluate ML models, datasets, and code repositories. Unlike simple storage solutions, this system automatically calculates trust and quality metrics for every artifact—checking for proper documentation, responsive maintainers, reproducible code, and license compliance. 

The platform helps engineers quickly assess which models are safe and easy to adopt, reducing manual vetting time and integration risk. It combines a Django-based REST API backend with a React TypeScript frontend, integrating with HuggingFace, GitHub, and Purdue's GenAI Studio for comprehensive analysis.

## Features

- **Artifact Management:** Upload and manage ML models, datasets, and code repositories from multiple sources (HuggingFace, GitHub, S3)
- **Automated Metrics Calculation:**
  - Performance Claims analysis using LLM-based scoring
  - Bus Factor (repository health via contributors and commit history)
  - Model Size evaluation across deployment platforms
  - Ramp-Up Time (documentation quality and ease of adoption)
  - Code & Dataset Quality assessment
  - License compliance validation
  - Reproducibility scoring
- **Advanced LLM Integration:** AI-powered analysis using Purdue GenAI Studio and Llama 3.1
- **Full-Text Search:** Search artifacts by name, description, and metadata
- **Batch Processing:** Evaluate multiple artifacts sequentially or in parallel with performance timing
- **REST API:** Comprehensive API compliant with OpenAPI 3.0 specification
- **Interactive Web UI:** React-based dashboard with real-time metrics visualization
- **Role-Based Access Control:** Support for admin, submitter, and viewer roles
- **Activity Logging:** Audit trail of all submissions, evaluations, and modifications
- **Docker Support:** Containerized deployment for easy scaling

## Prerequisites

- **Python 3.11 or higher**
- **Node.js 18 or higher** (for frontend development)
- **PostgreSQL 12+** (or SQLite for local development)
- **Git**
- **Docker** (optional, for containerized deployment)
- **Hugging Face account** (for API access)
- **GitHub account** (for repository analysis, optional but recommended)
- **Google Cloud or Purdue GenAI account** (for LLM-powered metrics, optional)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/ECE46100-Fall2025-Team26.git
cd ECE46100-Fall2025-Team26
```

### 2. Backend Setup

#### On Windows:

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Verify Python version
python --version
```

#### On macOS/Linux:

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify Python version
python --version
```

### 3. Frontend Setup

#### On Windows:

```powershell
cd frontend
npm install
npm run dev
```

#### On macOS/Linux:

```bash
cd frontend
npm install
npm run dev
```

### 4. Environment Variables Setup

Create a `.env` file in the project root with the following variables:

```bash
# Database Configuration
POSTGRES_DB=registry_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Django Security
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True  # Set to False in production

# External APIs - Model Fetching
HF_TOKEN=your_hugging_face_token_here
GITHUB_TOKEN=your_github_personal_access_token

# LLM Service - For AI-Powered Metrics
GEMINI_API_KEY=your_gemini_api_key  # OR
PURDUE_LLM_API_KEY=your_purdue_llm_key

# AWS S3 - For Artifact Storage
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_BUCKET_NAME=your_s3_bucket
AWS_REGION=us-east-1
```

#### Getting API Tokens:

**Hugging Face Token (Required):**
1. Go to https://huggingface.co/settings/tokens
2. Click "New token"
3. Choose "Read" permissions
4. Copy the token and add to `.env`

**GitHub Token (Optional but Recommended):**
1. Go to https://github.com/settings/personal-access-tokens/new
2. Select scopes: `public_repo`, `read:user`
3. Copy the token and add to `.env`

**Gemini API Key (Optional for LLM features):**
1. Go to https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key and add to `.env`

### 5. Database Setup

```bash
cd backend/web/registry

# Apply migrations
python manage.py migrate

# Create superuser (admin account)
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

## Project Structure

```
ECE46100-Fall2025-Team26/
├── .github/
│   └── workflows/                    # CI/CD pipelines
│       ├── deploy-backend.yml        # Docker build & EC2 deployment
│       ├── deploy-to-s3.yml          # React build & S3 sync
│       └── pytest.yml                # Backend test runner
├── backend/
│   ├── src/                          # Core Python application
│   │   ├── main.py                   # CLI & batch processing entry point
│   │   ├── Controllers/
│   │   │   └── Controller.py         # Data fetching orchestration
│   │   ├── Services/
│   │   │   └── Metric_Model_Service.py    # Metric evaluation engine
│   │   ├── Models/
│   │   │   ├── Model.py              # Core data model
│   │   │   └── Manager_Models_Model.py    # Model manager
│   │   ├── lib/
│   │   │   ├── Github_API_Manager.py      # GitHub integration
│   │   │   ├── HuggingFace_API_Manager.py # HuggingFace integration
│   │   │   ├── LLM_Manager.py             # LLM service integration
│   │   │   ├── Kaggle_API_Manager.py      # Kaggle integration
│   │   │   └── Metric_Result.py           # Metric result dataclass
│   │   ├── Helpers/
│   │   │   ├── Calc_Months.py       # Date calculation utilities
│   │   │   └── ISO_Parser.py        # ISO datetime parsing
│   │   └── Testing/
│   │       ├── conftest.py                           # Pytest fixtures
│   │       ├── test_controller.py                    # Controller tests
│   │       ├── test_controller_coverage.py           # Controller coverage boost
│   │       ├── test_helpers.py                       # Helper utilities tests
│   │       ├── test_helpers_coverage_boost.py        # Helper edge cases
│   │       ├── test_lib.py                           # API manager tests
│   │       ├── test_main.py                          # CLI/main entry point tests
│   │       ├── test_main_coverage.py                 # Main coverage boost
│   │       ├── test_main_coverage_boost.py           # Additional main tests
│   │       ├── test_metric_service.py                # Metric service core
│   │       ├── test_metric_service_coverage_boost.py # Metric service edge cases
│   │       ├── test_models.py                        # Model and manager tests
│   │       ├── test_real_world_integration.py        # End-to-end integration
│   │       ├── test_services_coverage.py             # Service coverage
│   │       ├── test_service_branch_coverage.py       # Branch coverage for services
│   │       ├── test_service_coverage_final.py        # Final service coverage
│   │       ├── test_simple_coverage.py               # Basic coverage tests
│   │       ├── test_full_service_coverage.py         # Complete service coverage
│   │       ├── test_internal_logic.py                # Internal logic tests
│   │       ├── test_service_logic_intensive.py       # Logic-intensive tests
│   │       ├── test_final_coverage_push.py           # Final push for coverage
│   │       └── test_tracks_endpoint.py               # API endpoint tracking
│   ├── web/registry/                 # Django REST API
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── views.py             # DRF ViewSets
│   │   │   ├── activity_views.py    # Activity log endpoints
│   │   │   ├── auth_views.py        # Authentication endpoints
│   │   │   ├── serializers.py       # Data serializers
│   │   │   ├── models.py            # ORM models
│   │   │   ├── urls.py              # API routes
│   │   │   ├── auth.py              # Authentication backend
│   │   │   ├── storage.py           # Storage configuration
│   │   │   ├── admin.py             # Django admin
│   │   │   ├── apps.py              # App configuration
│   │   │   ├── services/            # Business logic services
│   │   │   ├── management/          # Management commands
│   │   │   ├── migrations/          # Database migrations
│   │   │   └── tests/               # Django app tests
│   │   ├── registry/
│   │   │   ├── settings.py          # Django configuration
│   │   │   ├── urls.py              # Root URL config
│   │   │   └── wsgi.py              # WSGI entry point
│   │   └── manage.py                # Django CLI
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Docker configuration
│   └── deploy.sh                     # AWS deployment script
├── frontend/
│   ├── src/
│   │   ├── main.tsx                 # React entry point
│   │   ├── App.tsx                  # Main app component
│   │   ├── pages/
│   │   │   ├── SearchPage.tsx       # Main search interface
│   │   │   ├── ArtifactDetailPage.tsx
│   │   │   ├── UploadPage.tsx
│   │   │   ├── ActivityLogPage.tsx
│   │   │   ├── AdminPage.tsx
│   │   │   ├── BrowsePage.tsx
│   │   │   └── LoginPage.tsx
│   │   ├── components/
│   │   │   ├── Header.tsx
│   │   │   ├── ArtifactCard.tsx
│   │   │   ├── MetricsDisplay.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   ├── LoadingSpinner.tsx
│   │   │   └── Toast.tsx
│   │   ├── services/
│   │   │   └── api.ts               # API client
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx      # Auth state
│   │   ├── types/
│   │   │   ├── index.ts
│   │   │   └── activity.ts
│   │   └── utils/
│   │       └── format.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts               # Vite build config
│   └── index.html
├── openapi_spec.yaml                # API specification
├── pytest.ini                        # Pytest configuration
└── README.md                         # This file
```

## Usage

### Running the Backend

#### Development Server

```bash
cd backend/web/registry

# Run the Django development server
python manage.py runserver 0.0.0.0:8000

# The API will be available at http://localhost:8000
# Admin panel at http://localhost:8000/admin
```

#### Using Docker

```bash
cd backend

# Build the Docker image
docker build -t registry-backend:latest .

# Run the container
docker run -p 8000:8000 \
  --env-file .env \
  -e DJANGO_SETTINGS_MODULE=registry.settings \
  registry-backend:latest
```

#### CLI / Batch Processing

```bash
cd backend

# Run metric evaluation on a single model
python -m src.main sample_input.txt

# Input file format (CSV):
# code_link, dataset_link, model_link
# https://github.com/example/repo, https://huggingface.co/datasets/dataset, https://huggingface.co/user/model
```

### Running the Frontend

```bash
cd frontend

# Development server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

The frontend will be available at `http://localhost:5173` by default.

### Running Tests

#### Backend Unit & Integration Tests

```bash
cd backend

# Run all tests with pytest
python -m pytest

# Run with verbose output
python -m pytest -v

# Run specific test file
python -m pytest src/Testing/test_metric_service.py -v

# Run tests matching a pattern
python -m pytest -k "test_size" -v

# Generate coverage report
python -m coverage run -m pytest
python -m coverage report -m
```

#### Frontend Tests

```bash
cd frontend

# Run ESLint
npm run lint

# Build (validates TypeScript)
npm run build
```

## API Endpoints

### Artifact Management
- `GET /api/artifacts/` - List all artifacts
- `POST /api/artifacts/` - Create new artifact
- `GET /api/artifacts/{id}/` - Get artifact details
- `PATCH /api/artifacts/{id}/` - Update artifact
- `DELETE /api/artifacts/{id}/` - Delete artifact

### Metrics
- `GET /api/artifacts/{id}/metrics/` - Get all metrics
- `POST /api/artifacts/{id}/re-evaluate/` - Trigger re-evaluation
- `GET /api/metrics/summary/` - Aggregate statistics

### Search & Discovery
- `GET /api/search/?q=query` - Full-text search
- `GET /api/browse/?category=X&sort=Y` - Browse by category

### Authentication
- `POST /api/auth/login/` - User login
- `POST /api/auth/logout/` - User logout
- `GET /api/auth/profile/` - Current user profile

## Development

### Adding New Metrics

1. Add metric type to [lib/Metric_Result.py](lib/Metric_Result.py):
   ```python
   class MetricType(Enum):
       NEW_METRIC = "new_metric"
   ```

2. Implement evaluation in [Services/Metric_Model_Service.py](Services/Metric_Model_Service.py):
   ```python
   def EvaluateNewMetric(self, Data: Model) -> MetricResult:
       # Your implementation
       return MetricResult(
           metric_type=MetricType.NEW_METRIC,
           value=score,
           details={...},
           latency_ms=elapsed_time
       )
   ```

3. Add tests in `Testing/test_*.py`

4. Integrate into `run_evaluations_sequential()` and `run_evaluations_parallel()` in `main.py`

### Code Structure Guidelines

- **Controllers:** Business logic and orchestration
- **Services:** External API calls and metric calculations
- **Models:** Data structures and ORM models
- **lib:** API managers and utility services
- **Helpers:** Pure utility functions
- **Testing:** Comprehensive test coverage with mocks

### Contributing Workflow

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes following code style guidelines
3. Add tests and ensure coverage maintained
4. Run: `python -m pytest` and `npm run lint`
5. Commit with clear messages: `git commit -m "feat: add new metric"`
6. Push and create pull request

## Troubleshooting

### Common Issues

**Import Errors:**
- Ensure backend is active: `source venv/bin/activate` (or `.\venv\Scripts\Activate.ps1` on Windows)
- Run from correct directory: `cd backend` before running tests
- Check PYTHONPATH: `export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"`

**API Authentication Errors:**
- Verify `.env` file exists with valid tokens
- Check token scopes on HuggingFace and GitHub
- For LLM: Ensure API key is valid and account has quota

**Database Connection Errors:**
- Verify PostgreSQL is running: `psql --version`
- Check credentials in `.env`
- Run migrations: `python manage.py migrate`

**Frontend can't connect to backend:**
- Verify backend is running on correct port
- Check `VITE_API_URL` in frontend `.env`
- Check CORS settings in `backend/web/registry/settings.py`

**Docker Issues:**
- Clear cache: `docker system prune -a`
- Rebuild image: `docker build --no-cache -t registry-backend .`
- Check logs: `docker logs <container_id>`

### Getting Help

- Check GitHub Issues for known problems
- Review API documentation:
  - [HuggingFace Hub](https://huggingface.co/docs/hub/api)
  - [GitHub REST API](https://docs.github.com/en/rest)
  - [Django REST Framework](https://www.django-rest-framework.org/)

## Contributing

Follow these guidelines:
- Use type hints for Python code
- Write tests for new features
- Follow PEP 8 style guide
- Update documentation
- Use conventional commits (feat:, fix:, docs:, test:, etc.)

## License

Built by **Team 26** for ECE 46100 Software Engineering (Fall 2025) at Purdue University.
# FleetGuard AI

> Predictive Failure Engine and Agentic AI Assistant for Commercial Vehicle Fleets

FleetGuard AI is a predictive maintenance platform for commercial fleets. It combines synthetic telematics and failure history, applies correlative risk analysis, and exposes actionable vehicle health signals through a backend API and AI assistant.

## Overview

Modern fleet operations generate large volumes of telematics signals, but they rarely surface the leading indicators of component failure early enough to act. FleetGuard AI addresses that gap by modeling historical failure patterns and live vehicle behavior to estimate:

- failure probability for critical parts
- risk tiers and precursor signals
- remaining useful life (RUL)
- fleet-wide risk trends
- natural-language insights grounded in the backend data

The platform is designed to support operational teams and decision makers with clear, data-backed outputs rather than opaque model scores alone.

## What the project is building

FleetGuard AI helps teams:

- generate synthetic fleet data for testing and modeling
- analyze component-level failure correlations
- score vehicles and parts using telemetry patterns
- classify risk levels and prioritize intervention
- estimate remaining useful life for high-risk components
- expose results through a dashboard and AI-driven assistant

## Architecture

```mermaid
flowchart LR
    A[Synthetic Fleet Data] --> B[(Database)]
    B --> C[ML / Scoring Engine]
    C --> D[Failure Probability + RUL]
    D --> E[FastAPI Backend]
    E --> F[Dashboard]
    E --> G[Agentic AI Assistant]
```

## Core components

### Backend
The backend is the control plane for the platform. It handles data generation, persistence, prediction logic, RUL calculations, and the API layer that powers the rest of the application.

### ML and scoring engine
The scoring engine evaluates component-specific rules based on live telematics data and historical failure signatures. It outputs failure probability, risk classification, and a ranked list of precursor signals.

### Agentic AI
The AI layer is grounded to backend tools and returns responses only from validated fleet data. This keeps answers interpretable and prevents speculative or fabricated fleet insights.

## Technology stack

| Layer | Technology | Status |
| --- | --- | --- |
| Backend | Python, FastAPI | Active |
| Database | SQLAlchemy, SQLite | Active |
| ML | pandas, scikit-learn | Active |
| AI | Google Gemini via GenAI SDK | Active |
| Frontend | React + Tailwind CSS | Planned |

## Repository structure

```text
Fleet AI backend/
├── fleetguard-backend/
│   ├── app/
│   │   ├── api/
│   │   ├── ml/
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── generate_data.py
│   ├── clean_db.py
│   ├── requirements.txt
│   ├── test_agent.py
│   └── README.md
├── README.md
└── .gitignore
```

## Feature set

- Synthetic fleet data generation
- Failure correlation and rule evaluation
- Part-specific risk scoring
- Probability-based failure classification
- Remaining useful life estimation
- Fleet-level summary and drilldown analysis
- Grounded natural-language assistant for fleet questions
- Dashboard-ready API responses

## Current project status

This project is in active development. The backend already includes:

- synthetic fleet and failure generation
- SQLAlchemy models for vehicles, parts, telematics, rules, and predictions
- ML scoring and risk logic
- FastAPI endpoints for fleet summary, predictions, and AI tools
- a Gemini-backed chat assistant with grounded tool usage

Planned next steps include:

- frontend dashboard polish
- richer rule management and UX flows
- expanded analytics and comparison views
- production-grade deployment configuration

## Getting started

### Prerequisites

- Python 3.10+
- pip
- virtual environment support

### 1. Clone the repository

```bash
git clone <repository-url>
cd "Fleet AI backend"
```

### 2. Set up the backend environment

```bash
cd fleetguard-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in `fleetguard-backend/`:

```env
GEMINI_API_KEY=your_google_gemini_api_key
```

### 4. Generate the synthetic fleet dataset

```bash
python generate_data.py
```

### 5. Start the API

```bash
uvicorn app.main:app --reload
```

The app will be available at:

- http://127.0.0.1:8000
- health check: http://127.0.0.1:8000/api/health

## API and project flow

The backend exposes endpoints for:

- fleet summaries and risk trends
- vehicle and part analysis
- prediction outputs
- top precursor signals
- AI tool access and chat requests

The general flow is:

```text
Synthetic data -> database -> ML scoring -> prediction outputs -> FastAPI -> dashboard / assistant
```

## Roadmap

### Near term
- harden the scoring model behavior and thresholds
- expose more fleet insights through the API
- refine AI tool grounding and response quality

### Medium term
- add frontend dashboard interactions
- add rule builder and scenario tuning
- improve visualization of risk and RUL trends

### Longer term
- production-ready deployment pipeline
- richer fleet analytics and alerting
- operational workflow automation and action recommendations

## Project roles

This project is best understood as a collaboration between:

- Data / ML engineer: synthetic data, feature analysis, probability scoring, failure logic
- Product / operations engineer: dashboard experience, risk decisioning, AI workflow UX

## License

This project is currently under active development and has not yet been assigned a formal public license.

## Notes

FleetGuard AI is intentionally built to surface realistic maintenance insight from synthetic operational data while keeping the system grounded in backend-generated facts. The AI assistant is designed to answer queries using the platform’s actual fleet data instead of free-form speculation.

Create a minimal setup section.

Because the exact setup commands may not yet be finalized, use placeholders:

```bash
# Backend
[TBD]

# Frontend
[TBD]
```

Include:

```text
<!-- TODO: Replace placeholders with verified setup commands. -->
```

Do NOT invent commands.

---

## 10. Environment Configuration

Include a short section stating that environment-specific configuration and secrets should be stored outside source control.

Use a placeholder:

```text
Environment variables:
[TBD — document finalized variables here]
```

Do not invent actual API keys or configuration names.

---

## 11. Development Roles

Create:

| Developer   | Primary Responsibility |
| ----------- | ---------------------- |
| Developer A | Data, ML & Backend     |
| Developer B | Frontend & Agentic AI  |

Briefly describe each role.

---

## 12. Project Status

Create a simple checklist.

Example:

```markdown
- [ ] Project setup
- [ ] Database design
- [ ] Synthetic data generator
- [ ] ML / correlation engine
- [ ] Failure probability engine
- [ ] RUL engine
- [ ] FastAPI backend
- [ ] React dashboard
- [ ] Insight Agent
- [ ] Integration testing
- [ ] Documentation
```

Do not mark unfinished components as completed.

---

## 13. Roadmap

Create a short roadmap organized into logical stages:

1. Project foundation
2. Data and database
3. ML and scoring
4. Backend APIs
5. Frontend
6. Agentic AI
7. Integration
8. Testing
9. Documentation and demo

Keep this high level.

---

## 14. Documentation

Add a placeholder section:

```markdown
## Documentation

Project documentation will be maintained in the `docs/` directory.

Planned documentation:

- Software Design Document
- Database Design
- API Documentation
- ML Methodology
- Agent Design
- Testing Documentation

<!-- TODO: Add links as documents are created. -->
```

---

## 15. Git Workflow

Keep this section very short.

Mention that feature branches and pull requests will be used.

Example:

```text
main
├── feature/backend-*
├── feature/frontend-*
├── feature/ml-*
└── feature/agent-*
```

Add:

```text
<!-- TODO: Update with the finalized Git workflow. -->
```

Do not over-document Git here because the detailed workflow will exist elsewhere.

---

## 16. Known TODOs

End with a dedicated TODO section.

Include items such as:

```markdown
- [ ] Finalize database schema
- [ ] Finalize API contracts
- [ ] Finalize repository structure
- [ ] Add verified setup commands
- [ ] Add environment variable documentation
- [ ] Add architecture diagram
- [ ] Add API documentation
- [ ] Add screenshots
- [ ] Add demo instructions
```

---

# Formatting Requirements

The final output must be **only the contents of `README.md`**.

Use Markdown.

Keep it concise and readable.

Use:

* Headings
* Tables
* Bullet lists
* Code blocks
* Checklists
* Mermaid diagrams where useful

Avoid excessive prose.

Do not use emojis unless genuinely useful.

Do not create a polished marketing README.

The goal is to create a **clean initial README that can be continuously updated as FleetGuard AI moves from architecture → implementation → testing → final submission**.

Before finalizing, verify that:

* No unverified commands are presented as real.
* No unfinished functionality is presented as completed.
* No finalized database schema is invented.
* No finalized API endpoints are invented.
* All TBD information is clearly marked.
* The README remains concise enough to maintain throughout the project.

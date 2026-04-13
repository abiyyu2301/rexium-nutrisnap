# NutriSnap — Meal Vision Nutrition Analyzer

Snap a photo of your meal → AI identifies foods → instant calorie & macro breakdown.

**Stack:** Next.js (frontend) + FastAPI (backend) + GCP Vertex AI Gemini + Firestore

---

## Project Structure

```
rexium-nutrisnap/
├── frontend/               # Next.js 14 app
│   ├── app/
│   │   ├── page.tsx       # Main upload + results UI
│   │   └── layout.tsx
│   └── package.json
├── backend/                # FastAPI service
│   ├── main.py            # API endpoints
│   ├── vertexai.py        # Gemini vision integration
│   ├── nutrition.py       # Firestore fuzzy search
│   └── requirements.txt
├── infrastructure/        # GCP deployment
│   ├── Dockerfile.frontend
│   ├── Dockerfile.backend
│   └── cloudbuild.yaml
├── nutrition-data/        # DB seeding
│   └── import_firestore.py
└── README.md
```

---

## Local Development

### 1. Backend
```bash
cd backend
pip install -r requirements.txt

# Set env
export GCP_PROJECT=rexium-nutrisnap
export GCP_LOCATION=us-central1
export GCS_BUCKET=rexium-nutrisnap-images

# Run
uvicorn main:app --reload --port 8080
```

### 2. Frontend
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8080 npm run dev
```

---

## Deployment (GCP Cloud Run)

Push to `main` → Cloud Build auto-deploys both services.

Or manually:
```bash
# Build & push
docker build -t us-central1-docker.pkg.dev/rexium-nutrisnap/nutrisnap-images/backend:latest ./backend
docker push us-central1-docker.pkg.dev/rexium-nutrisnap/nutrisnap-images/backend:latest

# Deploy
gcloud run deploy nutrisnap-api \
  --image=us-central1-docker.pkg.dev/rexium-nutrisnap/nutrisnap-images/backend:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated
```

---

## Data Seeding (one-time)

```bash
gcloud auth application-default login
python3 nutrition-data/import_firestore.py --project rexium-nutrisnap
```

---

## GCP Requirements Checklist

- [ ] Project: `rexium-nutrisnap`
- [ ] APIs: Cloud Run, Vertex AI, Firestore, Cloud Build, Artifact Registry, Secret Manager, Cloud Storage
- [ ] Artifact Registry: `nutrisnap-images` (Docker, us-central1)
- [ ] Cloud Storage: `rexium-nutrisnap-images` (24h TTL lifecycle)
- [ ] Firestore: Native mode, us-central1
- [ ] Service Account: `nutrisnap-backend-sa` with Vertex AI User + Cloud Run Developer + Secret Manager + Storage Object Admin roles
- [ ] Secret Manager: `GCP_PROJECT_ID` = your project ID

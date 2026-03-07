#!/usr/bin/env bash
set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────────────
PROJECT="project-cf964f7d-d79b-4b69-81c"
REGION="us-central1"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/weatherwise"
SA_NAME="weatherwise-run"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

# ─── Load .env ────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  echo "ERROR: .env file not found in current directory" >&2
  exit 1
fi
set -a; source .env; set +a

: "${OPENWEATHER_API_KEY:?OPENWEATHER_API_KEY must be set in .env}"
: "${VERTEX_PROJECT:?VERTEX_PROJECT must be set in .env}"
: "${VERTEX_LOCATION:?VERTEX_LOCATION must be set in .env}"
: "${LLM_PROVIDER:?LLM_PROVIDER must be set in .env}"

# ─── 1. Artifact Registry ─────────────────────────────────────────────────────
echo "▶ Creating Artifact Registry repo (idempotent)..."
gcloud artifacts repositories create weatherwise \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT}" \
  --quiet 2>/dev/null || true

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ─── 2. Service Account ───────────────────────────────────────────────────────
echo "▶ Creating service account (idempotent)..."
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="WeatherWise Cloud Run SA" \
  --project="${PROJECT}" \
  --quiet 2>/dev/null || true

echo "▶ Granting IAM roles..."
for ROLE in roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet > /dev/null
done

# ─── 3. Secret Manager ────────────────────────────────────────────────────────
echo "▶ Creating/updating secrets..."

create_or_update_secret() {
  local SECRET_NAME="$1"
  local SECRET_VALUE="$2"
  if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT}" --quiet &>/dev/null; then
    echo "  Updating secret: ${SECRET_NAME}"
    echo -n "${SECRET_VALUE}" | gcloud secrets versions add "${SECRET_NAME}" \
      --data-file=- --project="${PROJECT}" --quiet
  else
    echo "  Creating secret: ${SECRET_NAME}"
    echo -n "${SECRET_VALUE}" | gcloud secrets create "${SECRET_NAME}" \
      --data-file=- --project="${PROJECT}" --quiet
  fi
}

create_or_update_secret "weatherwise-openweather-api-key" "${OPENWEATHER_API_KEY}"
if [[ -n "${GROQ_API_KEY:-}" ]]; then
  create_or_update_secret "weatherwise-groq-api-key" "${GROQ_API_KEY}"
fi

# ─── 4. Build & Push mcp-server and agent-backend images ─────────────────────
echo "▶ Building and pushing mcp-server and agent-backend images..."

docker build --platform linux/amd64 -f Dockerfile.mcp -t "${REGISTRY}/mcp-server:latest" .
docker push "${REGISTRY}/mcp-server:latest"

docker build --platform linux/amd64 -f Dockerfile.agent -t "${REGISTRY}/agent-backend:latest" .
docker push "${REGISTRY}/agent-backend:latest"

# ─── Common deploy flags ──────────────────────────────────────────────────────
COMMON_FLAGS=(
  "--project=${PROJECT}"
  "--region=${REGION}"
  "--service-account=${SA_EMAIL}"
  "--allow-unauthenticated"
  "--min-instances=1"
  "--max-instances=3"
  "--quiet"
)

# ─── 5. Deploy weatherwise-agent-mcp ─────────────────────────────────────────
echo "▶ Deploying weatherwise-agent-mcp..."
gcloud run deploy weatherwise-agent-mcp \
  "${COMMON_FLAGS[@]}" \
  --image="${REGISTRY}/mcp-server:latest" \
  --port=8001 \
  --set-env-vars="MCP_TRANSPORT=sse,MCP_PORT=8001" \
  --set-secrets="OPENWEATHER_API_KEY=weatherwise-openweather-api-key:latest"

MCP_SERVER_URL=$(gcloud run services describe weatherwise-agent-mcp \
  --project="${PROJECT}" --region="${REGION}" --format="value(status.url)")
echo "  weatherwise-agent-mcp URL: ${MCP_SERVER_URL}"

# ─── 6. Deploy agent-backend ──────────────────────────────────────────────────
echo "▶ Deploying weatherwise-agent-backend..."

BACKEND_ENV_VARS="LLM_PROVIDER=${LLM_PROVIDER},VERTEX_PROJECT=${VERTEX_PROJECT},VERTEX_LOCATION=${VERTEX_LOCATION},MCP_SERVER_URL=${MCP_SERVER_URL}/sse"

BACKEND_SECRETS="OPENWEATHER_API_KEY=weatherwise-openweather-api-key:latest"
if [[ -n "${GROQ_API_KEY:-}" ]]; then
  BACKEND_SECRETS="${BACKEND_SECRETS},GROQ_API_KEY=weatherwise-groq-api-key:latest"
fi

gcloud run deploy weatherwise-agent-backend \
  "${COMMON_FLAGS[@]}" \
  --image="${REGISTRY}/agent-backend:latest" \
  --port=8000 \
  --set-env-vars="${BACKEND_ENV_VARS}" \
  --set-secrets="${BACKEND_SECRETS}"

BACKEND_URL=$(gcloud run services describe weatherwise-agent-backend \
  --project="${PROJECT}" --region="${REGION}" --format="value(status.url)")
echo "  weatherwise-agent-backend URL: ${BACKEND_URL}"

# ─── 7. Build & push frontend (needs BACKEND_URL baked in at build time) ──────
echo "▶ Building and pushing frontend image (with API_URL=${BACKEND_URL})..."
docker build --platform linux/amd64 -f Dockerfile.frontend \
  --build-arg API_URL="${BACKEND_URL}" \
  -t "${REGISTRY}/frontend:latest" .
docker push "${REGISTRY}/frontend:latest"

# ─── 8. Deploy frontend ───────────────────────────────────────────────────────
echo "▶ Deploying weatherwise-agent-frontend..."
gcloud run deploy weatherwise-agent-frontend \
  "${COMMON_FLAGS[@]}" \
  --image="${REGISTRY}/frontend:latest" \
  --port=3000

FRONTEND_URL=$(gcloud run services describe weatherwise-agent-frontend \
  --project="${PROJECT}" --region="${REGION}" --format="value(status.url)")

# ─── 9. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Deployment complete!"
echo "═══════════════════════════════════════════════════"
echo " weatherwise-agent-mcp:      ${MCP_SERVER_URL}"
echo " weatherwise-agent-backend:  ${BACKEND_URL}"
echo " weatherwise-agent-frontend: ${FRONTEND_URL}"
echo "═══════════════════════════════════════════════════"
echo ""
echo "To view logs:"
echo "  gcloud run services logs read weatherwise-agent-backend --region=${REGION} --project=${PROJECT}"

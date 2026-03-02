#!/usr/bin/env bash
# =============================================================================
# AskHR Chatbot — Azure Infrastructure Provisioning Script
# =============================================================================
# Prerequisites:
#   - Azure CLI installed and logged in: az login
#   - Sufficient permissions: Contributor + User Access Administrator on subscription
#   - An existing Azure OpenAI resource (set AZURE_OPENAI_RESOURCE_ID below)
#
# Usage:
#   chmod +x infra/provision.sh
#   bash infra/provision.sh
# =============================================================================

set -euo pipefail

# ─── Configuration — edit these ───────────────────────────────────────────────
RESOURCE_GROUP="rg-askhr"
LOCATION="eastus"
ACR_NAME="askhrregistry"                        # must be globally unique, alphanumeric
STORAGE_ACCOUNT="askhrstore$(date +%s | tail -c5)"  # globally unique
FILESHARE_NAME="askhr-chromadb"
IDENTITY_NAME="id-askhr"
CONTAINERAPPS_ENV="cae-askhr"
BACKEND_APP="askhr-backend"
FRONTEND_APP="askhr-frontend"

# Your pre-existing Azure OpenAI resource (full resource ID)
# Find it: az cognitiveservices account show --name <name> -g <rg> --query id -o tsv
AZURE_OPENAI_RESOURCE_ID="/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<OPENAI_RG>/providers/Microsoft.CognitiveServices/accounts/<OPENAI_RESOURCE_NAME>"

# Azure OpenAI settings (set after you deploy models in Azure portal)
AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
AZURE_OPENAI_API_VERSION="2024-02-01"

# Image tags — updated by the pipeline; defaults to latest for manual deploy
BACKEND_IMAGE="${ACR_NAME}.azurecr.io/askhr-backend:latest"
FRONTEND_IMAGE="${ACR_NAME}.azurecr.io/askhr-frontend:latest"

# ─── Helpers ──────────────────────────────────────────────────────────────────
info()    { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
success() { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m  $*"; }

# ─── 1. Resource Group ────────────────────────────────────────────────────────
info "Creating resource group: $RESOURCE_GROUP in $LOCATION"
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
success "Resource group ready."

# ─── 2. Azure Container Registry ─────────────────────────────────────────────
info "Creating ACR: $ACR_NAME"
az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --sku Basic \
    --admin-enabled false \
    --output none
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
success "ACR ready: $(az acr show --name "$ACR_NAME" --query loginServer -o tsv)"

# ─── 3. Storage Account + File Share ─────────────────────────────────────────
info "Creating storage account: $STORAGE_ACCOUNT"
az storage account create \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --output none

info "Creating file share: $FILESHARE_NAME"
STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

az storage share create \
    --name "$FILESHARE_NAME" \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY" \
    --quota 10 \
    --output none
success "Storage account and file share ready."

# ─── 4. User-Assigned Managed Identity ───────────────────────────────────────
info "Creating managed identity: $IDENTITY_NAME"
az identity create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --output none

IDENTITY_ID=$(az identity show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --query id -o tsv)

IDENTITY_CLIENT_ID=$(az identity show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --query clientId -o tsv)

IDENTITY_PRINCIPAL_ID=$(az identity show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --query principalId -o tsv)

success "Managed identity created. Client ID: $IDENTITY_CLIENT_ID"

# ─── 5. Role Assignments ──────────────────────────────────────────────────────
info "Assigning 'Cognitive Services OpenAI User' role on Azure OpenAI resource"
az role assignment create \
    --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Cognitive Services OpenAI User" \
    --scope "$AZURE_OPENAI_RESOURCE_ID" \
    --output none
success "OpenAI role assigned."

info "Assigning 'AcrPull' role on ACR"
az role assignment create \
    --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "AcrPull" \
    --scope "$ACR_ID" \
    --output none
success "AcrPull role assigned."

# ─── 6. Container Apps Environment ───────────────────────────────────────────
info "Creating Container Apps environment: $CONTAINERAPPS_ENV"
az containerapp env create \
    --name "$CONTAINERAPPS_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none

info "Attaching Azure Files storage to Container Apps environment"
az containerapp env storage set \
    --name "$CONTAINERAPPS_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --storage-name "chromadb-storage" \
    --azure-file-account-name "$STORAGE_ACCOUNT" \
    --azure-file-account-key "$STORAGE_KEY" \
    --azure-file-share-name "$FILESHARE_NAME" \
    --access-mode ReadWrite \
    --output none
success "Container Apps environment ready."

# ─── 7. Backend Container App ─────────────────────────────────────────────────
info "Creating backend Container App: $BACKEND_APP"
az containerapp create \
    --name "$BACKEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$BACKEND_IMAGE" \
    --target-port 8000 \
    --ingress external \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --user-assigned "$IDENTITY_ID" \
    --registry-identity "$IDENTITY_ID" \
    --cpu 1.0 \
    --memory 2.0Gi \
    --min-replicas 1 \
    --max-replicas 5 \
    --env-vars \
        USE_MANAGED_IDENTITY=true \
        AZURE_CLIENT_ID="$IDENTITY_CLIENT_ID" \
        AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
        AZURE_OPENAI_CHAT_DEPLOYMENT="$AZURE_OPENAI_CHAT_DEPLOYMENT" \
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT="$AZURE_OPENAI_EMBEDDING_DEPLOYMENT" \
        AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
        CHROMA_PERSIST_DIR="/mnt/chromadb" \
        CHROMA_COLLECTION_NAME="askhr_docs" \
        LOG_LEVEL="INFO" \
    --output none

info "Mounting Azure Files volume into backend"
az containerapp update \
    --name "$BACKEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --volume name="chromadb-vol",storage-type=AzureFile,storage-name=chromadb-storage \
    --mount-volume volumeName="chromadb-vol",mountPath="/mnt/chromadb" \
    --output none

BACKEND_FQDN=$(az containerapp show \
    --name "$BACKEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.fqdn -o tsv)
success "Backend deployed: https://$BACKEND_FQDN"

# ─── 8. Frontend Container App ───────────────────────────────────────────────
info "Creating frontend Container App: $FRONTEND_APP"
az containerapp create \
    --name "$FRONTEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$FRONTEND_IMAGE" \
    --target-port 8501 \
    --ingress external \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --user-assigned "$IDENTITY_ID" \
    --registry-identity "$IDENTITY_ID" \
    --cpu 0.5 \
    --memory 1.0Gi \
    --min-replicas 1 \
    --max-replicas 3 \
    --env-vars \
        BACKEND_URL="https://$BACKEND_FQDN" \
    --output none

FRONTEND_FQDN=$(az containerapp show \
    --name "$FRONTEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.fqdn -o tsv)
success "Frontend deployed: https://$FRONTEND_FQDN"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  AskHR Azure Deployment Complete"
echo "============================================================"
echo "  Chat UI (Streamlit):  https://$FRONTEND_FQDN"
echo "  REST API (FastAPI):   https://$BACKEND_FQDN"
echo "  API Docs:             https://$BACKEND_FQDN/docs"
echo "  ACR:                  ${ACR_NAME}.azurecr.io"
echo "  Managed Identity:     $IDENTITY_NAME ($IDENTITY_CLIENT_ID)"
echo "  ChromaDB File Share:  $STORAGE_ACCOUNT/$FILESHARE_NAME"
echo "============================================================"
echo ""
warn "Next steps:"
echo "  1. Push Docker images to ACR:"
echo "     az acr build -t askhr-backend:latest -r $ACR_NAME -f Dockerfile ."
echo "     az acr build -t askhr-frontend:latest -r $ACR_NAME -f frontend/Dockerfile ./frontend"
echo "  2. Set up Azure DevOps pipeline using azure-pipelines.yml"
echo "  3. POST https://$BACKEND_FQDN/api/v1/ingest to index HR documents"

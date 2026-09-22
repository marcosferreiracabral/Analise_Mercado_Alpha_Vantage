# ==============================================================================
# Script de Automacao Git & GitHub
# Alvo: https://github.com/marcosferreiraracabral/Analise_Mercado_Alpha_Vantage
# ==============================================================================

$ErrorActionPreference = "Continue"

$REPO_NAME = "Analise_Mercado_Alpha_Vantage"
$GITHUB_USER = "marcosferreiracabral"
$REMOTE_HTTPS = "https://github.com/$GITHUB_USER/$REPO_NAME.git"

Write-Host "Iniciando configuracao do repositorio Git..." -ForegroundColor Cyan

# 1. Validacao de Dependencia do Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git CLI nao encontrado no PATH. Instale o Git antes de prosseguir." -ForegroundColor Red
    exit 1
}

# 2. Inicializacao do Repositorio Local
if (-not (Test-Path ".git")) {
    Write-Host "Inicializando repositorio Git local na branch main..." -ForegroundColor Green
    git init -b main
} else {
    Write-Host "Repositorio Git local ja existente." -ForegroundColor Yellow
    git branch -M main
}

# 3. Criacao do Repositorio Remoto no GitHub (via gh CLI se autenticado)
if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Host "Verificando autenticacao no GitHub CLI..." -ForegroundColor Cyan
    & gh auth status 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Autenticado no GitHub CLI. Criando/verificando repositorio remoto..." -ForegroundColor Green
        & gh repo create "$GITHUB_USER/$REPO_NAME" --public --description "Alpha Vantage Financial Market Pipeline with GCP BigQuery & Streamlit" --source=. --remote=origin 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Repositorio remoto criado com sucesso no GitHub!" -ForegroundColor Green
        } else {
            Write-Host "Repositorio remoto ja existe ou foi configurado." -ForegroundColor Yellow
        }
    }
}

# 4. Assegurar configuracao do Remote 'origin'
$existingRemote = git remote get-url origin 2>$null
if (-not $existingRemote) {
    Write-Host "Configurando remote origin para $REMOTE_HTTPS..." -ForegroundColor Green
    git remote add origin $REMOTE_HTTPS
} else {
    Write-Host "Atualizando remote origin para $REMOTE_HTTPS..." -ForegroundColor Yellow
    git remote set-url origin $REMOTE_HTTPS
}

# 5. Stage e Commit
Write-Host "Adicionando arquivos ao index..." -ForegroundColor Cyan
git add .

$status = git status --porcelain
if ($status) {
    Write-Host "Criando commit inicial..." -ForegroundColor Green
    git commit -m "feat: initial commit for alpha vantage financial pipeline and bigquery integration"
} else {
    Write-Host "Nenhuma alteracao pendente para commit." -ForegroundColor Yellow
}

# 6. Push para o GitHub
Write-Host "Enviando commits para a branch main no GitHub..." -ForegroundColor Cyan
& git push -u origin main
if ($LASTEXITCODE -eq 0) {
    Write-Host "Push concluido com sucesso!" -ForegroundColor Green
    Write-Host "Repositorio disponivel em: https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
} else {
    Write-Host "Tentando push com rebase preventivo caso haja arquivos remotos..." -ForegroundColor Yellow
    & git pull origin main --rebase
    & git push -u origin main
}

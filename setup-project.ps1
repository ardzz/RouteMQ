# DEPRECATED (since v0.14.0):
#   The canonical install path is now: pip install routemq[cli] && routemq new my-app
#   See README.md for the recommended workflow.
#   This script is retained for the "fork the framework" path; will be removed in v0.16.0.

# RouteMQ Project Setup Script (PowerShell)
# This script initializes a fresh git repository for your project

$ErrorActionPreference = "Stop"

Write-Host "🚀 RouteMQ Project Setup" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan
Write-Host ""

# Check if git is installed
try {
    git --version | Out-Null
} catch {
    Write-Host "❌ Error: git is not installed. Please install git first." -ForegroundColor Red
    exit 1
}

# Function to remove existing git repository
function Remove-GitHistory {
    if (Test-Path ".git") {
        Write-Host "🗑️  Removing existing git history..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force ".git"
        Write-Host "✅ Git history removed" -ForegroundColor Green
    } else {
        Write-Host "ℹ️  No existing git history found" -ForegroundColor Gray
    }
}

# Function to initialize new git repository
function Initialize-GitRepo {
    Write-Host ""
    Write-Host "📦 Initializing fresh git repository..." -ForegroundColor Yellow
    git init
    git add .
    git commit -m "feat: initial commit from RouteMQ template"
    Write-Host "✅ Fresh repository initialized" -ForegroundColor Green
}

# Function to set up remote
function Setup-Remote {
    Write-Host ""
    $addRemote = Read-Host "Do you want to add a remote repository? (y/n)"

    if ($addRemote -eq "y" -or $addRemote -eq "Y") {
        $remoteUrl = Read-Host "Enter your remote repository URL (e.g., https://github.com/username/repo.git)"

        if ($remoteUrl) {
            git remote add origin $remoteUrl
            Write-Host "✅ Remote 'origin' added: $remoteUrl" -ForegroundColor Green
            Write-Host ""
            Write-Host "To push your code, run:" -ForegroundColor Cyan
            Write-Host "  git push -u origin main" -ForegroundColor White
        } else {
            Write-Host "⚠️  No remote URL provided, skipping..." -ForegroundColor Yellow
        }
    }
}

# Function to copy environment file
function Setup-Env {
    Write-Host ""
    if (Test-Path ".env.example") {
        if (!(Test-Path ".env")) {
            Write-Host "📝 Creating .env file from .env.example..." -ForegroundColor Yellow
            Copy-Item ".env.example" ".env"
            Write-Host "✅ .env file created (please configure it)" -ForegroundColor Green
        } else {
            Write-Host "ℹ️  .env file already exists" -ForegroundColor Gray
        }
    }
}

# Main execution
Write-Host "This script will:" -ForegroundColor White
Write-Host "  1. Remove existing git history"
Write-Host "  2. Initialize a fresh git repository"
Write-Host "  3. Optionally set up your remote repository"
Write-Host "  4. Set up environment configuration"
Write-Host ""

$confirm = Read-Host "Continue? (y/n)"

if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "❌ Setup cancelled" -ForegroundColor Red
    exit 0
}

Write-Host ""

# Execute setup steps
Remove-GitHistory
Initialize-GitRepo
Setup-Remote
Setup-Env

Write-Host ""
Write-Host "🎉 Setup complete! Your project is ready." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Configure your .env file"
Write-Host "  2. Run: uv sync"
Write-Host "  3. Run: routemq --init"
Write-Host "  4. Run: uv run routemq --run"
Write-Host ""
Write-Host "📚 See README.md for detailed documentation" -ForegroundColor Cyan

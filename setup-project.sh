#!/bin/bash

# RouteMQ Project Setup Script
# This script initializes a fresh git repository for your project

set -e

echo "🚀 RouteMQ Project Setup"
echo "========================"
echo ""

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "❌ Error: git is not installed. Please install git first."
    exit 1
fi

# Function to remove existing git repository
remove_git_history() {
    if [ -d ".git" ]; then
        echo "🗑️  Removing existing git history..."
        rm -rf .git
        echo "✅ Git history removed"
    else
        echo "ℹ️  No existing git history found"
    fi
}

# Function to initialize new git repository
init_git_repo() {
    echo ""
    echo "📦 Initializing fresh git repository..."
    git init
    git add .
    git commit -m "feat: initial commit from RouteMQ template"
    echo "✅ Fresh repository initialized"
}

# Function to set up remote
setup_remote() {
    echo ""
    read -p "Do you want to add a remote repository? (y/n): " add_remote

    if [[ $add_remote == "y" || $add_remote == "Y" ]]; then
        read -p "Enter your remote repository URL (e.g., https://github.com/username/repo.git): " remote_url

        if [ -n "$remote_url" ]; then
            git remote add origin "$remote_url"
            echo "✅ Remote 'origin' added: $remote_url"
            echo ""
            echo "To push your code, run:"
            echo "  git push -u origin main"
        else
            echo "⚠️  No remote URL provided, skipping..."
        fi
    fi
}

# Function to copy environment file
setup_env() {
    echo ""
    if [ -f ".env.example" ]; then
        if [ ! -f ".env" ]; then
            echo "📝 Creating .env file from .env.example..."
            cp .env.example .env
            echo "✅ .env file created (please configure it)"
        else
            echo "ℹ️  .env file already exists"
        fi
    fi
}

# Main execution
echo "This script will:"
echo "  1. Remove existing git history"
echo "  2. Initialize a fresh git repository"
echo "  3. Optionally set up your remote repository"
echo "  4. Set up environment configuration"
echo ""
read -p "Continue? (y/n): " confirm

if [[ $confirm != "y" && $confirm != "Y" ]]; then
    echo "❌ Setup cancelled"
    exit 0
fi

echo ""

# Execute setup steps
remove_git_history
init_git_repo
setup_remote
setup_env

echo ""
echo "🎉 Setup complete! Your project is ready."
echo ""
echo "Next steps:"
echo "  1. Configure your .env file"
echo "  2. Run: uv sync"
echo "  3. Run: python main.py --init"
echo "  4. Run: uv run python main.py --run"
echo ""
echo "📚 See README.md for detailed documentation"

#!/bin/bash

echo "Setting up GitHub repository..."
echo ""
echo "Please create a new repository on GitHub first:"
echo "1. Go to https://github.com/new"
echo "2. Name: ai-prompt-marketplace"
echo "3. Don't initialize with README"
echo ""
echo "Then enter your GitHub username:"
read -p "GitHub username: " username

echo ""
echo "Setting up remote..."

# Add remote origin
git remote add origin https://github.com/$username/ai-prompt-marketplace.git

# Verify remote
echo "Remote added:"
git remote -v

echo ""
echo "Ready to push! Run:"
echo "git push -u origin main"
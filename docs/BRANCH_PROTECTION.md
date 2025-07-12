# Setting Up Branch Protection for Main Branch

## Steps to Enable Branch Protection

1. **Navigate to your repository settings**:
   - Go to https://github.com/juanpasaflipz/ai-prompt-marketplace
   - Click on "Settings" tab (top right of the repository)

2. **Access branch protection rules**:
   - In the left sidebar, click on "Branches" under "Code and automation"
   - Click "Add rule" or "Add branch protection rule"

3. **Configure the protection rule**:
   - Branch name pattern: `main`
   - Enable these recommended settings:

### Recommended Settings:

#### ✅ Protect matching branches
- [x] **Require a pull request before merging**
  - [x] Require approvals (1-2 approvals recommended)
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require review from CODEOWNERS (if you have a CODEOWNERS file)

#### ✅ Status checks
- [x] **Require status checks to pass before merging**
  - [x] Require branches to be up to date before merging
  - Select status checks (once you have CI/CD running):
    - `test` (from GitHub Actions)
    - `lint` (from GitHub Actions)

#### ✅ Conversation resolution
- [x] **Require conversation resolution before merging**

#### ✅ Additional protections
- [x] **Require signed commits** (optional but recommended)
- [x] **Include administrators** (apply rules to admin users too)
- [x] **Restrict who can push to matching branches**
  - Add specific users or teams who can push directly

#### ⚠️ Optional (use with caution)
- [ ] Allow force pushes (generally not recommended)
- [ ] Allow deletions (keep disabled to prevent accidental deletion)

4. **Save the rule**:
   - Click "Create" or "Save changes"

## Creating a CODEOWNERS file (Optional)

Create a file to specify code owners for automatic review requests:
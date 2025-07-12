# Branching Strategy and Protection Rules

## Recommended Branch Structure

### 1. **main** (Production)
- **Pattern**: `main`
- **Purpose**: Production-ready code
- **Protection**: HIGHEST - Full protection with all checks
- **Rules**:
  - Require pull request with 1-2 approvals
  - Require status checks (tests, lint)
  - No direct pushes (including admins)
  - No force pushes
  - No deletions

### 2. **develop** (Development)
- **Pattern**: `develop`
- **Purpose**: Integration branch for features
- **Protection**: MEDIUM - Balanced protection
- **Rules**:
  - Require pull request with 1 approval
  - Require status checks
  - Allow admins to push directly (for hotfixes)

### 3. **release/** (Release Candidates)
- **Pattern**: `release/*`
- **Purpose**: Release preparation branches
- **Protection**: HIGH - Similar to main
- **Example**: `release/v1.0.0`, `release/v1.1.0`

### 4. **hotfix/** (Emergency Fixes)
- **Pattern**: `hotfix/*`
- **Purpose**: Critical production fixes
- **Protection**: MEDIUM - Fast-track approval
- **Example**: `hotfix/payment-bug`, `hotfix/auth-fix`

## Setting Up Multiple Branch Protection Rules

### For a Startup/Small Team:
Start simple with just **main** protection:
```
Branch pattern: main
```

### For a Growing Team:
Add **develop** protection:
```
Branch pattern: main
Branch pattern: develop
```

### For a Mature Product:
Add all patterns:
```
Branch pattern: main
Branch pattern: develop
Branch pattern: release/*
Branch pattern: hotfix/*
```

## Workflow Examples

### Feature Development
```
main
  └── develop
         └── feature/user-authentication
         └── feature/payment-integration
```

### Release Process
```
develop
  └── release/v1.0.0
         └── main (after testing)
```

### Hotfix Process
```
main
  └── hotfix/critical-bug
         └── main (fast-track merge)
         └── develop (backport fix)
```

## Recommended Settings by Branch

### Main Branch
- ✅ Require pull request (2 approvals)
- ✅ Dismiss stale reviews
- ✅ Require status checks
- ✅ Require up-to-date branches
- ✅ Include administrators
- ✅ Restrict push access
- ❌ No force pushes
- ❌ No deletions

### Develop Branch
- ✅ Require pull request (1 approval)
- ✅ Require status checks
- ✅ Require up-to-date branches
- ⚠️ Don't include administrators (optional)
- ❌ No force pushes
- ❌ No deletions

### Release Branches
- ✅ Require pull request (2 approvals)
- ✅ Require status checks
- ✅ Include administrators
- ✅ Restrict push access (release manager only)
- ❌ No force pushes
- ⚠️ Allow deletions after merge

### Hotfix Branches
- ✅ Require pull request (1 approval - expedited)
- ✅ Require critical status checks only
- ⚠️ Allow admin override for emergencies
- ❌ No force pushes

## For Your Current Stage

Since you're just starting, I recommend:

1. **Start with protecting only `main`**
   - This is your production branch
   - Apply the strictest rules here

2. **Add `develop` later when you:**
   - Have multiple developers
   - Need a staging environment
   - Want to batch features for releases

3. **Add other patterns as needed:**
   - When you start doing scheduled releases
   - When you need emergency hotfix procedures
   - When your team grows beyond 3-4 developers
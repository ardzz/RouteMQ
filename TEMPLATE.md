# Making RouteMQ a GitHub Template Repository

This guide is for repository maintainers who want to enable the "Use this template" feature on GitHub.

## What is a Template Repository?

A GitHub template repository allows users to create new repositories with the same directory structure and files, but with a clean git history. This is perfect for starter projects and frameworks like RouteMQ.

## Benefits

When RouteMQ is marked as a template:

- ✅ Users see a **"Use this template"** button on GitHub
- ✅ Easy one-click creation of new projects
- ✅ Automatically starts with a clean git history
- ✅ No need to manually remove `.git` folder
- ✅ GitHub tracks derived repositories
- ✅ Better discoverability

## How to Enable

### For Repository Owners:

1. **Navigate to your repository** on GitHub
   - Go to `https://github.com/ardzz/RouteMQ`

2. **Click on Settings** (repository settings, not profile)
   - Located in the top navigation bar

3. **Scroll to the "Template repository" section**
   - It's near the top of the settings page

4. **Check the box** that says:
   - ☑️ "Template repository"

5. **Done!** The "Use this template" button will now appear

### Visual Guide:

```
GitHub Repository Page
  └─ Settings (tab)
      └─ General
          └─ Template repository
              └─ ☑️ Template repository
                  "Allow users to create new repositories from this repository"
```

## After Enabling

Once enabled:

### Users Will See:

- A green **"Use this template"** button next to the "Code" button
- Clicking it opens a dialog to create a new repository
- The new repository is independent with its own git history

### Recommended Additional Setup:

1. **Add a clear description** to the repository
   - "A flexible MQTT routing framework - Use as template for your projects"

2. **Add relevant topics/tags**
   - `mqtt`, `framework`, `template`, `python`, `iot`, `routing`

3. **Create a good README** (already done ✅)
   - Explain it's meant to be used as a template
   - Provide "Use this template" instructions

4. **Add a LICENSE** (if not present)
   - Makes it clear how users can use the code

## Alternative: Making a Fork-able Framework

If you prefer users to fork instead:

1. Don't enable template repository
2. Keep the manual setup scripts (already included)
3. Users can still use `setup-project.sh` to clean git history

## Files in This Repository

This repository already includes:

- ✅ `setup-project.sh` - Bash script for clean setup
- ✅ `setup-project.ps1` - PowerShell script for Windows
- ✅ `INSTALL.md` - Detailed installation guide
- ✅ Updated `README.md` - Template usage instructions
- ✅ This file (`TEMPLATE.md`) - Guide for maintainers

## Testing Template Feature

After enabling:

1. **Test the template button** yourself
   - Click "Use this template"
   - Create a test repository
   - Verify it has clean history
   - Delete the test repo

2. **Check the experience**
   - Make sure README renders correctly
   - Verify setup scripts are executable
   - Ensure .env.example is present

## Best Practices

### Do:
- ✅ Keep the repository clean and well-documented
- ✅ Use .gitignore to exclude unnecessary files
- ✅ Provide clear setup instructions
- ✅ Include example configurations
- ✅ Add CI/CD templates if applicable

### Don't:
- ❌ Include sensitive data or credentials
- ❌ Have incomplete or broken code
- ❌ Include large binary files
- ❌ Leave TODO comments everywhere
- ❌ Have failing tests

## Files to Exclude from Template

Consider adding to `.gitignore`:

```gitignore
# User-specific files
.env
*.log
__pycache__/
*.pyc

# IDE files
.vscode/
.idea/
*.swp

# OS files
.DS_Store
Thumbs.db
```

## Maintaining a Template

### When Making Changes:

1. **Test thoroughly** before committing
   - Changes affect all new projects created

2. **Keep backwards compatibility** when possible
   - Users may update their projects

3. **Document breaking changes**
   - In CHANGELOG.md
   - In release notes

4. **Version appropriately**
   - Use semantic versioning
   - Tag releases

## User Workflow After Template is Enabled

1. User visits `github.com/ardzz/RouteMQ`
2. Clicks **"Use this template"**
3. Fills in:
   - Repository name
   - Description (optional)
   - Public/Private
4. Clicks **"Create repository from template"**
5. GitHub creates new repo with:
   - All RouteMQ files
   - Clean git history (single initial commit)
   - User's own remote
6. User clones and starts working

## Migration from Manual Setup

Users who previously cloned can:

1. **New projects:** Use the template button going forward
2. **Existing projects:** Continue as-is, no changes needed
3. **Want to switch:** Can still use setup scripts to clean history

## Additional Resources

- [GitHub Template Repositories Documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository)
- [Template Repository Best Practices](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions)

## Summary

**To make RouteMQ a template repository:**

```
Settings → General → Template repository → ☑️ Enable
```

**That's it!** The repository is already prepared with all necessary setup scripts and documentation.

---

**Questions?** Open an issue or check GitHub's documentation.

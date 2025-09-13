# Documentation CI/CD Automation

This directory contains scripts and workflows to automatically maintain the documentation's table of contents (`docs/SUMMARY.md`) whenever markdown files are added, modified, or removed from the documentation.

## Overview

The automation system consists of:

1. **Python Script** (`update_summary.py`) - Core logic for scanning docs and generating SUMMARY.md
2. **GitHub Actions Workflow** (`update-docs-summary.yml`) - Automated CI/CD pipeline
3. **Local Development Scripts** - Manual tools for developers

## Files

### Core Script
- `scripts/update_summary.py` - Main Python script that scans the docs directory and updates SUMMARY.md

### CI/CD Workflow
- `.github/workflows/update-docs-summary.yml` - GitHub Actions workflow that runs automatically

### Development Scripts
- `scripts/update-docs.sh` - Bash script for Unix/Linux/macOS developers
- `scripts/update-docs.bat` - Batch script for Windows developers

## How It Works

### Automatic Updates (CI/CD)

The GitHub Actions workflow automatically triggers when:
- Any markdown file in the `docs/` directory is modified
- New directories are created in `docs/`
- Changes are pushed to `main`, `master`, or `develop` branches
- Pull requests modify documentation files

**Workflow behavior:**
- **On push**: Automatically commits updated SUMMARY.md back to the repository
- **On pull request**: Adds a comment showing the changes and preview

### Manual Updates (Development)

Developers can manually update the documentation locally:

```bash
# Unix/Linux/macOS
./scripts/update-docs.sh

# Windows
scripts\update-docs.bat

# Direct Python execution
python scripts/update_summary.py
```

## Script Features

### Intelligent Scanning
- Automatically extracts titles from markdown H1 headings
- Falls back to filename-based titles when H1 is not found
- Maintains logical section ordering based on priority
- Handles nested directory structures with proper indentation

### Priority Ordering
The script prioritizes sections in this order:
1. README.md (root documentation)
2. getting-started
3. core-concepts
4. routing
5. controllers
6. middleware
7. configuration
8. database
9. redis
10. rate-limiting
11. monitoring
12. testing
13. deployment
14. examples
15. api-reference
16. troubleshooting
17. best-practices.md
18. faq.md

### Smart Title Extraction
- Reads the first H1 heading (`# Title`) from each markdown file
- Converts filenames to readable titles (e.g., `rate-limiting` → `Rate Limiting`)
- Handles special cases (e.g., `faq` → `Frequently Asked Questions (FAQ)`)

## Configuration

### Excluded Files
The script automatically excludes:
- `SUMMARY.md` (to avoid self-reference)
- `.gitkeep` files
- Any files starting with `.`

### Customization
To modify the behavior, edit `scripts/update_summary.py`:

```python
# Change excluded files
self.excluded_files = {"SUMMARY.md", ".gitkeep", "custom-exclude.md"}

# Modify section priority order
self.priority_sections = [
    "README.md",
    "your-custom-section",
    # ... rest of sections
]
```

## GitHub Actions Configuration

### Permissions Required
The workflow needs the following permissions:
- `contents: write` - To commit changes back to the repository
- `pull-requests: write` - To comment on pull requests

### Environment Variables
No special environment variables are required. The workflow uses:
- `${{ secrets.GITHUB_TOKEN }}` - Automatically provided by GitHub
- `${{ github.workspace }}` - Repository root directory

### Workflow Triggers
```yaml
on:
  push:
    paths:
      - 'docs/**/*.md'
      - 'docs/**'
    branches:
      - main
      - master  
      - develop
  pull_request:
    paths:
      - 'docs/**/*.md'
      - 'docs/**'
```

## Usage Examples

### Adding New Documentation

1. **Create new markdown file:**
   ```bash
   # Create new section
   mkdir docs/new-feature
   echo "# New Feature Guide" > docs/new-feature/README.md
   echo "# Getting Started" > docs/new-feature/getting-started.md
   ```

2. **Commit changes:**
   ```bash
   git add docs/new-feature/
   git commit -m "docs: add new feature documentation"
   git push
   ```

3. **Result:** SUMMARY.md is automatically updated via GitHub Actions

### Local Development Workflow

1. **Make documentation changes:**
   ```bash
   # Edit existing docs or add new ones
   vim docs/routing/advanced-patterns.md
   ```

2. **Update SUMMARY.md locally:**
   ```bash
   # Run the update script
   ./scripts/update-docs.sh
   ```

3. **Review and commit:**
   ```bash
   git add docs/
   git commit -m "docs: add advanced routing patterns"
   ```

## Troubleshooting

### Script Fails to Run
```bash
# Check Python installation
python --version

# Ensure you're in the project root
ls scripts/update_summary.py

# Run with verbose output
python scripts/update_summary.py --dry-run
```

### GitHub Actions Fails
1. Check workflow permissions in repository settings
2. Verify the workflow file syntax
3. Check if the repository has branch protection rules that block the bot

### Missing Files in SUMMARY.md
1. Ensure files have `.md` extension
2. Check if files are in excluded list
3. Verify file contains valid H1 heading (`# Title`)

### Wrong Section Order
1. Check the `priority_sections` list in the script
2. Ensure directory names match exactly (case-sensitive)
3. Run `--dry-run` to preview changes before applying

## Development

### Testing Changes
```bash
# Test without making changes
python scripts/update_summary.py --dry-run

# Test with specific docs directory
python scripts/update_summary.py --docs-dir ./my-docs

# View generated content
python scripts/update_summary.py --dry-run | grep -A 50 "Generated content"
```

### Adding Features
To extend the script functionality:
1. Edit `scripts/update_summary.py`
2. Test with `--dry-run`
3. Update this documentation
4. Test the GitHub Actions workflow

## Maintenance

### Regular Checks
- Verify SUMMARY.md is being updated correctly
- Monitor GitHub Actions workflow runs
- Check for any excluded files that should be included
- Update priority sections as documentation structure evolves

### Version Updates
When updating the script:
1. Test thoroughly with `--dry-run`
2. Update this documentation
3. Consider backward compatibility
4. Test in a feature branch first

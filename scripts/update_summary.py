#!/usr/bin/env python3
"""
Script to automatically update docs/SUMMARY.md based on the docs directory structure.
This script scans all markdown files and directories in the docs folder and generates
a properly formatted GitBook-style table of contents.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple

class SummaryGenerator:
    def __init__(self, docs_dir: str = "docs"):
        self.docs_dir = Path(docs_dir)
        self.base_path = Path.cwd()
        self.summary_file = self.docs_dir / "SUMMARY.md"

        # Files to exclude from the summary
        self.excluded_files = {"SUMMARY.md", ".gitkeep"}

        # Priority order for main sections (will appear first)
        self.priority_sections = [
            "README.md",
            "getting-started",
            "core-concepts",
            "routing",
            "controllers",
            "middleware",
            "configuration",
            "database",
            "redis",
            "queue",
            "rate-limiting",
            "monitoring",
            "testing",
            "deployment",
            "examples",
            "api-reference",
            "troubleshooting",
            "best-practices.md",
            "faq.md",
            "tinker.md",
            "docker-deployment.md"
        ]

    def extract_title_from_markdown(self, file_path: Path) -> str:
        """Extract the first H1 title from a markdown file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Look for the first H1 heading
            h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if h1_match:
                return h1_match.group(1).strip()

            # Fallback to filename
            return self.filename_to_title(file_path.stem)

        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            return self.filename_to_title(file_path.stem)

    def filename_to_title(self, filename: str) -> str:
        """Convert filename to a readable title."""
        # Remove common prefixes/suffixes
        title = filename.replace('-', ' ').replace('_', ' ')

        # Handle special cases
        title_mappings = {
            "README": "Overview",
            "api reference": "API Reference",
            "faq": "Frequently Asked Questions (FAQ)",
            "ci cd": "CI/CD",
            "config": "Configuration"
        }

        title_lower = title.lower()
        if title_lower in title_mappings:
            return title_mappings[title_lower]

        # Capitalize words
        return ' '.join(word.capitalize() for word in title.split())

    def scan_directory(self, directory: Path, relative_to: Path = None) -> List[Dict]:
        """Recursively scan directory for markdown files and subdirectories."""
        if relative_to is None:
            relative_to = self.docs_dir

        items = []

        if not directory.exists():
            return items

        # Get all items in directory
        all_items = list(directory.iterdir())

        # Separate files and directories
        files = [item for item in all_items if item.is_file() and item.suffix == '.md' and item.name not in self.excluded_files]
        directories = [item for item in all_items if item.is_dir() and not item.name.startswith('.')]

        # Process README.md first if it exists
        readme_file = directory / "README.md"
        if readme_file.exists() and readme_file.name not in self.excluded_files:
            relative_path = readme_file.relative_to(relative_to)
            title = self.extract_title_from_markdown(readme_file)
            items.append({
                'type': 'file',
                'title': title,
                'path': str(relative_path).replace('\\', '/'),
                'level': len(relative_path.parts) - 1
            })
            files = [f for f in files if f.name != "README.md"]

        # Process other markdown files (sorted)
        for file in sorted(files, key=lambda x: x.name.lower()):
            relative_path = file.relative_to(relative_to)
            title = self.extract_title_from_markdown(file)
            items.append({
                'type': 'file',
                'title': title,
                'path': str(relative_path).replace('\\', '/'),
                'level': len(relative_path.parts) - 1
            })

        # Process subdirectories
        for subdir in sorted(directories, key=lambda x: x.name.lower()):
            relative_path = subdir.relative_to(relative_to)

            # Check if directory has a README.md for the title
            subdir_readme = subdir / "README.md"
            if subdir_readme.exists():
                title = self.extract_title_from_markdown(subdir_readme)
            else:
                title = self.filename_to_title(subdir.name)

            # Add directory entry
            items.append({
                'type': 'directory',
                'title': title,
                'path': str(relative_path).replace('\\', '/'),
                'level': len(relative_path.parts) - 1
            })

            # Recursively scan subdirectory
            subitems = self.scan_directory(subdir, relative_to)
            items.extend(subitems)

        return items

    def sort_items(self, items: List[Dict]) -> List[Dict]:
        """Sort items based on priority and alphabetical order."""
        def get_sort_key(item):
            path_parts = item['path'].split('/')
            first_part = path_parts[0]

            # Check if it's in priority list
            if first_part in self.priority_sections:
                priority = self.priority_sections.index(first_part)
            else:
                priority = len(self.priority_sections)  # Put at end

            return (priority, item['level'], item['path'].lower())

        return sorted(items, key=get_sort_key)

    def generate_summary_content(self) -> str:
        """Generate the complete SUMMARY.md content."""
        print(f"Scanning documentation directory: {self.docs_dir}")

        # Scan all items
        all_items = self.scan_directory(self.docs_dir)

        # Remove duplicates - prefer directory entries over individual README entries
        seen_paths = set()
        filtered_items = []

        for item in all_items:
            # For README.md files that are in directories, check if we already have the directory
            if item['type'] == 'file' and item['path'].endswith('/README.md'):
                dir_path = item['path'][:-10]  # Remove '/README.md'
                # Skip if we already have this directory or if it's the root README
                if dir_path and any(existing['path'] == dir_path for existing in filtered_items):
                    continue

            # For directories, check if we already have the README
            if item['type'] == 'directory':
                readme_path = f"{item['path']}/README.md"
                # Remove any existing README entry for this directory
                filtered_items = [existing for existing in filtered_items if existing['path'] != readme_path]

            if item['path'] not in seen_paths:
                seen_paths.add(item['path'])
                filtered_items.append(item)

        # Sort items according to priority
        sorted_items = self.sort_items(filtered_items)

        # Generate content
        lines = ["# Table of contents\n"]

        for item in sorted_items:
            indent = "  " * item['level']

            if item['type'] == 'file':
                lines.append(f"{indent}* [{item['title']}]({item['path']})")
            else:
                # Directory entry - only add if it has a README.md
                readme_path = Path(self.docs_dir) / item['path'] / "README.md"
                if readme_path.exists():
                    lines.append(f"{indent}* [{item['title']}]({item['path']}/README.md)")

        return '\n'.join(lines) + '\n'

    def update_summary(self) -> bool:
        """Update the SUMMARY.md file with generated content."""
        try:
            new_content = self.generate_summary_content()

            # Check if content has changed
            if self.summary_file.exists():
                with open(self.summary_file, 'r', encoding='utf-8') as f:
                    current_content = f.read()

                if current_content.strip() == new_content.strip():
                    print("SUMMARY.md is already up to date.")
                    return False

            # Write new content
            self.summary_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.summary_file, 'w', encoding='utf-8') as f:
                f.write(new_content)

            print(f"Successfully updated {self.summary_file}")
            return True

        except Exception as e:
            print(f"Error updating SUMMARY.md: {e}")
            return False

def main():
    """Main function to run the summary generator."""
    import argparse

    parser = argparse.ArgumentParser(description='Update docs/SUMMARY.md based on directory structure')
    parser.add_argument('--docs-dir', default='docs', help='Documentation directory path')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be generated without writing')

    args = parser.parse_args()

    generator = SummaryGenerator(args.docs_dir)

    if args.dry_run:
        print("DRY RUN - Generated content:")
        print("=" * 50)
        print(generator.generate_summary_content())
        print("=" * 50)
    else:
        changed = generator.update_summary()
        if changed:
            print("SUMMARY.md has been updated!")
        else:
            print("No changes needed.")

if __name__ == "__main__":
    main()

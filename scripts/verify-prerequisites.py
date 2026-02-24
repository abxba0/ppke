#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPKE Prerequisites Verification Script

Checks if your system is ready for PPKE v2.0 refactoring.

Usage:
    python prompts/verify-prerequisites.py
"""

import sys
import subprocess
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# ANSI colors
class Colors:
    """ANSI color codes for terminal output."""

    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    """Print a formatted section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def check_pass(text: str):
    """Print a passing check result."""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def check_fail(text: str):
    """Print a failing check result."""
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def check_warn(text: str):
    """Print a warning check result."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def check_info(text: str):
    """Print an informational message."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")


class PrerequisitesChecker:
    """Check prerequisites for PPKE refactoring."""

    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.checks_warned = 0
        self.repo_root = self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find PPKE repository root."""
        current = Path.cwd()

        # Check if current directory has ppke/
        if (current / 'ppke').exists():
            return current

        # Check parent
        if (current.parent / 'ppke').exists():
            return current.parent

        # Check if we're in prompts/ directory
        if current.name == 'prompts' and (current.parent / 'ppke').exists():
            return current.parent

        return current

    def run_all_checks(self) -> bool:
        """Run all prerequisite checks."""
        print_header("PPKE v2.0 Refactoring - Prerequisites Check")

        self.check_python_version()
        self.check_git()
        self.check_ppke_codebase()
        self.check_python_packages()
        self.check_disk_space()
        self.check_vault_backup()
        self.check_git_status()

        return self._print_summary()

    def check_python_version(self):
        """Check Python version >= 3.10."""
        print(f"\n{Colors.BOLD}Python Version{Colors.END}")

        version = sys.version_info
        if version >= (3, 10):
            check_pass(f"Python {version.major}.{version.minor}.{version.micro} (>= 3.10 required)")
            self.checks_passed += 1
        else:
            check_fail(f"Python {version.major}.{version.minor}.{version.micro} (need >= 3.10)")
            self.checks_failed += 1
            check_info("Install Python 3.10+ from https://python.org")

    def check_git(self):
        """Check if git is installed."""
        print(f"\n{Colors.BOLD}Git Installation{Colors.END}")

        try:
            result = subprocess.run(['git', '--version'], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                version = result.stdout.strip()
                check_pass(f"{version}")
                self.checks_passed += 1
            else:
                check_fail("Git not found")
                self.checks_failed += 1
        except FileNotFoundError:
            check_fail("Git not installed")
            self.checks_failed += 1
            check_info("Install git from https://git-scm.com")

    def check_ppke_codebase(self):
        """Check if PPKE codebase exists."""
        print(f"\n{Colors.BOLD}PPKE Codebase{Colors.END}")

        required_files = [
            'ppke/__init__.py',
            'ppke/cli.py',
            'ppke/config.py',
            'ppke/llm/prompts.py',
            'ppke/parser/models.py',
            'ppke/pipeline/orchestrator.py',
            'ppke/output/writer.py'
        ]

        all_present = True
        for file_path in required_files:
            full_path = self.repo_root / file_path
            if full_path.exists():
                if len(required_files) <= 3 or file_path in required_files[:3]:
                    check_pass(f"{file_path}")
            else:
                check_fail(f"Missing: {file_path}")
                all_present = False

        if all_present:
            check_pass("All core PPKE files present")
            self.checks_passed += 1
        else:
            check_fail("PPKE codebase incomplete")
            self.checks_failed += 1
            check_info(f"Repository root: {self.repo_root}")

    def check_python_packages(self):
        """Check required Python packages."""
        print(f"\n{Colors.BOLD}Python Packages{Colors.END}")

        required_packages = [
            ('pydantic', '2.0'),  # For Phase 2
            ('yaml', None),       # For templates (pip install pyyaml)
            ('pytest', None),     # For testing
        ]

        optional_packages = [
            ('anthropic', '0.39'),
            ('openai', '1.0'),
            ('click', '8.0'),
            ('rich', '13.0'),
        ]

        for package, _min_version in required_packages:
            try:
                __import__(package)
                # Display pyyaml for yaml package
                display_name = 'pyyaml' if package == 'yaml' else package
                check_pass(f"{display_name} installed")
                self.checks_passed += 1
            except ImportError:
                display_name = 'pyyaml' if package == 'yaml' else package
                check_fail(f"{display_name} not installed (required)")
                self.checks_failed += 1
                check_info(f"Install: pip install {display_name}")

        # Check optional
        missing_optional = []
        for package, _min_version in optional_packages:
            try:
                __import__(package)
            except ImportError:
                missing_optional.append(package)

        if missing_optional:
            check_warn(f"Optional packages missing: {', '.join(missing_optional)}")
            self.checks_warned += 1

    def check_disk_space(self):
        """Check available disk space."""
        print(f"\n{Colors.BOLD}Disk Space{Colors.END}")

        try:
            import shutil
            stat = shutil.disk_usage(self.repo_root)
            free_gb = stat.free / (1024 ** 3)

            if free_gb >= 5:
                check_pass(f"{free_gb:.1f} GB free (>= 5 GB recommended)")
                self.checks_passed += 1
            elif free_gb >= 1:
                check_warn(f"{free_gb:.1f} GB free (5 GB recommended)")
                self.checks_warned += 1
            else:
                check_fail(f"{free_gb:.1f} GB free (need at least 1 GB)")
                self.checks_failed += 1
        except Exception as e:
            check_warn(f"Could not check disk space: {e}")
            self.checks_warned += 1

    def check_vault_backup(self):
        """Check if KnowledgeBase vault exists and suggest backup."""
        print(f"\n{Colors.BOLD}Vault Backup{Colors.END}")

        vault_path = Path.home() / 'KnowledgeBase'
        backup_path = Path.home() / 'KnowledgeBase_v1_backup'

        if not vault_path.exists():
            check_info("No existing vault found (~/KnowledgeBase)")
            check_pass("Fresh installation - no backup needed")
            self.checks_passed += 1
        elif backup_path.exists():
            check_pass("Vault backup already exists (~/KnowledgeBase_v1_backup)")
            self.checks_passed += 1
        else:
            check_warn("Vault exists but no backup found")
            check_info("Recommended: cp -r ~/KnowledgeBase ~/KnowledgeBase_v1_backup")
            self.checks_warned += 1

    def check_git_status(self):
        """Check git status."""
        print(f"\n{Colors.BOLD}Git Status{Colors.END}")

        try:
            # Check if in git repo
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                check_warn("Not a git repository")
                check_info("Recommended: git init && git add . && git commit -m 'Initial commit'")
                self.checks_warned += 1
                return

            # Check for uncommitted changes
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.stdout.strip():
                check_warn("Uncommitted changes detected")
                check_info("Recommended: Commit changes before refactoring")
                check_info("  git add .")
                check_info("  git commit -m 'Pre-refactoring checkpoint'")
                self.checks_warned += 1
            else:
                check_pass("Git repository clean")
                self.checks_passed += 1

            # Check if on a branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            current_branch = result.stdout.strip()

            if current_branch:
                check_info(f"Current branch: {current_branch}")
                if current_branch not in ('main', 'master'):
                    check_warn("Not on main/master branch")
                    check_info("Consider: git checkout -b refactor-v2")
            else:
                check_warn("Not on any branch (detached HEAD)")

        except Exception as e:
            check_warn(f"Could not check git status: {e}")
            self.checks_warned += 1

    def _print_summary(self) -> bool:
        """Print summary and return success status."""
        print_header("Summary")

        total = self.checks_passed + self.checks_failed + self.checks_warned

        print(f"{Colors.GREEN}✅ Passed:  {self.checks_passed}{Colors.END}")
        print(f"{Colors.RED}❌ Failed:  {self.checks_failed}{Colors.END}")
        print(f"{Colors.YELLOW}⚠️  Warnings: {self.checks_warned}{Colors.END}")
        print(f"\nTotal checks: {total}")

        if self.checks_failed > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ Prerequisites NOT met{Colors.END}")
            print("Please fix the failed checks before proceeding.\n")
            return False
        if self.checks_warned > 0:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  Prerequisites met with warnings{Colors.END}")
            print("You can proceed, but consider addressing the warnings.\n")
            return True
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ All prerequisites met!{Colors.END}")
        print("\nReady to start PPKE v2.0 refactoring.\n")
        print("Next step:")
        print(f"  {Colors.BLUE}python prompts/quick-start-phase-1.py{Colors.END}\n")
        return True


def main():
    """Run the prerequisites checker."""
    checker = PrerequisitesChecker()
    success = checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

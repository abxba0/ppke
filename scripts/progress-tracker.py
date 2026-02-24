#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPKE v2.0 Refactoring Progress Tracker

Tracks completion status across all 4 phases by analyzing the codebase and checklist.

Usage:
    python prompts/progress-tracker.py
    python prompts/progress-tracker.py --detailed
"""

import sys
from pathlib import Path
import argparse

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
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def progress_bar(percentage: float, width: int = 20) -> str:
    """Generate a progress bar."""
    filled = int(width * percentage / 100)
    empty = width - filled
    bar_str = '█' * filled + '░' * empty
    return f"[{bar_str}] {percentage:5.1f}%"


class ProgressTracker:
    """Track PPKE refactoring progress."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.checklist_file = repo_root / 'REFACTORING_CHECKLIST.md'

        # Define tasks for each phase
        self.phase_tasks = {
            1: [
                ('Audit prompts.py', self._check_spec_plan_exists),
                ('Audit models.py', self._check_spec_plan_exists),
                ('Audit pipeline', self._check_spec_plan_exists),
                ('Create spec-plan-v2.md', self._check_spec_plan_exists),
                ('Create LICENSE', self._check_license_exists),
                ('Create checklist', self._check_checklist_exists),
            ],
            2: [
                ('Convert to Pydantic', self._check_pydantic_models),
                ('Create schema_builder.py', self._check_file_exists('ppke/parser/schema_builder.py')),
                ('Create template base.py', self._check_file_exists('ppke/templates/base.py')),
                ('Create template loader.py', self._check_file_exists('ppke/templates/loader.py')),
                ('Create philosophy template', self._check_philosophy_template),
                ('Create legal template', self._check_legal_template),
                ('Refactor prompts.py', self._check_dynamic_prompts),
                ('Refactor orchestrator.py', self._check_dynamic_pipeline),
                ('Add --domain CLI flag', self._check_domain_flag),
            ],
            3: [
                ('Plugin discovery', self._check_plugin_discovery),
                ('Plugin validation', self._check_plugin_validator),
                ('PLUGINS.md', self._check_file_exists('PLUGINS.md')),
                ('TEMPLATE_DEVELOPMENT_GUIDE.md', self._check_file_exists('TEMPLATE_DEVELOPMENT_GUIDE.md')),
                ('Example plugin', self._check_example_plugin),
                ('ppke validate-plugin CLI', self._check_validate_plugin_cli),
            ],
            4: [
                ('Backward compatibility tests', self._check_file_exists('tests/test_backward_compatibility.py')),
                ('Template tests', self._check_file_exists('tests/test_template_system.py')),
                ('MIGRATION_GUIDE.md', self._check_file_exists('MIGRATION_GUIDE.md')),
                ('CHANGELOG.md updated', self._check_changelog),
                ('README.md updated', self._check_readme_updated),
            ],
        }

    def get_overall_progress(self) -> tuple[float, int, int]:
        """Calculate overall progress percentage."""
        total_tasks = sum(len(tasks) for tasks in self.phase_tasks.values())
        completed_tasks = 0

        for _phase, tasks in self.phase_tasks.items():
            for _task_name, check_func in tasks:
                if check_func():
                    completed_tasks += 1

        percentage = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0
        return percentage, completed_tasks, total_tasks

    def get_phase_progress(self, phase: int) -> tuple[float, int, int]:
        """Calculate progress for a specific phase."""
        tasks = self.phase_tasks.get(phase, [])
        if not tasks:
            return 0.0, 0, 0

        completed = sum(1 for _, check_func in tasks if check_func())
        total = len(tasks)
        percentage = (completed / total) * 100 if total > 0 else 0

        return percentage, completed, total

    def display_progress(self, detailed: bool = False):
        """Display progress summary."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}PPKE v2.0 Refactoring Progress{Colors.END}\n")

        # Overall progress
        overall_pct, overall_done, overall_total = self.get_overall_progress()
        print(f"{Colors.BOLD}Overall Progress:{Colors.END}")
        print(f"  {progress_bar(overall_pct)} ({overall_done}/{overall_total} tasks)\n")

        # Phase-by-phase
        phase_names = {
            1: "Audit & Specification",
            2: "Refactor Core",
            3: "Plugin Ecosystem",
            4: "System Validation"
        }

        for phase_num in [1, 2, 3, 4]:
            phase_pct, phase_done, phase_total = self.get_phase_progress(phase_num)
            phase_name = phase_names[phase_num]

            # Status indicator
            if phase_pct == 100:
                status = f"{Colors.GREEN}✅{Colors.END}"
            elif phase_pct > 0:
                status = f"{Colors.YELLOW}🔄{Colors.END}"
            else:
                status = f"{Colors.BLUE}⏳{Colors.END}"

            print(f"{Colors.BOLD}Phase {phase_num}: {phase_name:30s}{Colors.END} {status}")
            print(f"  {progress_bar(phase_pct)} ({phase_done}/{phase_total})")

            if detailed:
                self._show_phase_tasks(phase_num)

            print()

        # Next task
        next_task = self._get_next_task()
        if next_task:
            print(f"{Colors.BOLD}Next Task:{Colors.END}")
            print(f"  {Colors.CYAN}→ {next_task}{Colors.END}\n")
        else:
            print(f"{Colors.GREEN}{Colors.BOLD}🎉 All tasks complete! Ready for release!{Colors.END}\n")

    def _show_phase_tasks(self, phase: int):
        """Show detailed task list for a phase."""
        tasks = self.phase_tasks.get(phase, [])

        for task_name, check_func in tasks:
            status = "✅" if check_func() else "  "
            print(f"      {status} {task_name}")

    def _get_next_task(self) -> str:
        """Get the next incomplete task."""
        for phase in [1, 2, 3, 4]:
            tasks = self.phase_tasks[phase]
            for task_name, check_func in tasks:
                if not check_func():
                    return f"Phase {phase}: {task_name}"
        return ""

    # Check functions

    def _check_spec_plan_exists(self) -> bool:
        """Check if spec-plan-v2.md exists."""
        return (self.repo_root / 'spec-plan-v2.md').exists()

    def _check_license_exists(self) -> bool:
        """Check if LICENSE exists."""
        license_file = self.repo_root / 'LICENSE'
        if not license_file.exists():
            return False
        # Check if it's Apache 2.0
        with open(license_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return 'Apache License' in content

    def _check_checklist_exists(self) -> bool:
        """Check if REFACTORING_CHECKLIST.md exists."""
        return self.checklist_file.exists()

    def _check_pydantic_models(self) -> bool:
        """Check if models use Pydantic."""
        models_file = self.repo_root / 'ppke' / 'parser' / 'models.py'
        if not models_file.exists():
            return False

        with open(models_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Check for Pydantic imports and BaseModel
            return 'from pydantic import' in content and 'BaseModel' in content

    def _check_file_exists(self, relative_path: str):
        """Return a function that checks if a file exists."""
        def checker() -> bool:
            return (self.repo_root / relative_path).exists()
        return checker

    def _check_philosophy_template(self) -> bool:
        """Check if philosophy template exists."""
        template_dir = self.repo_root / 'ppke' / 'templates' / 'official' / 'philosophy'
        required_files = ['template.yml', 'schema.yml', 'prompts.yml']
        return template_dir.exists() and all((template_dir / f).exists() for f in required_files)

    def _check_legal_template(self) -> bool:
        """Check if legal template exists."""
        template_dir = self.repo_root / 'ppke' / 'templates' / 'official' / 'legal'
        required_files = ['template.yml', 'schema.yml', 'prompts.yml']
        return template_dir.exists() and all((template_dir / f).exists() for f in required_files)

    def _check_dynamic_prompts(self) -> bool:
        """Check if prompts.py loads dynamically."""
        prompts_file = self.repo_root / 'ppke' / 'llm' / 'prompts.py'
        if not prompts_file.exists():
            return False

        with open(prompts_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Check for template loading
            return 'load_prompt' in content or 'template.prompts' in content

    def _check_dynamic_pipeline(self) -> bool:
        """Check if orchestrator uses dynamic stages."""
        orch_file = self.repo_root / 'ppke' / 'pipeline' / 'orchestrator.py'
        if not orch_file.exists():
            return False

        with open(orch_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Check for domain parameter and template loading
            return 'domain' in content and ('load_template' in content or 'template.stages' in content)

    def _check_domain_flag(self) -> bool:
        """Check if CLI has --domain flag."""
        cli_file = self.repo_root / 'ppke' / 'cli.py'
        if not cli_file.exists():
            return False

        with open(cli_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return '--domain' in content or "@click.option('--domain'" in content

    def _check_plugin_discovery(self) -> bool:
        """Check if plugin discovery is implemented."""
        loader_file = self.repo_root / 'ppke' / 'templates' / 'loader.py'
        if not loader_file.exists():
            return False

        with open(loader_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return 'discover_templates' in content

    def _check_plugin_validator(self) -> bool:
        """Check if plugin validator exists."""
        validator_file = self.repo_root / 'ppke' / 'templates' / 'validator.py'
        if not validator_file.exists():
            return False

        with open(validator_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return 'validate_template' in content

    def _check_example_plugin(self) -> bool:
        """Check if example custom plugin exists."""
        plugin_dir = Path.home() / '.ppke' / 'plugins' / 'scientific_research'
        return plugin_dir.exists() and (plugin_dir / 'template.yml').exists()

    def _check_validate_plugin_cli(self) -> bool:
        """Check if validate-plugin CLI command exists."""
        cli_file = self.repo_root / 'ppke' / 'cli.py'
        if not cli_file.exists():
            return False

        with open(cli_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return 'def validate_plugin' in content or '@cli.command()' in content and 'validate-plugin' in content

    def _check_changelog(self) -> bool:
        """Check if CHANGELOG.md has v2.0 entry."""
        changelog = self.repo_root / 'CHANGELOG.md'
        if not changelog.exists():
            return False

        with open(changelog, 'r', encoding='utf-8') as f:
            content = f.read()
            return '2.0.0' in content or '[2.0.0]' in content

    def _check_readme_updated(self) -> bool:
        """Check if README mentions multi-domain."""
        readme = self.repo_root / 'README.md'
        if not readme.exists():
            return False

        with open(readme, 'r', encoding='utf-8') as f:
            content = f.read()
            return '--domain' in content or 'multi-domain' in content.lower()


def main():
    """Run the progress tracker CLI."""
    parser = argparse.ArgumentParser(description='Track PPKE v2.0 refactoring progress')
    parser.add_argument('--detailed', '-d', action='store_true', help='Show detailed task lists')
    args = parser.parse_args()

    # Find repo root
    script_dir = Path(__file__).parent.parent
    repo_root = script_dir if (script_dir / 'ppke').exists() else Path.cwd()

    tracker = ProgressTracker(repo_root)
    tracker.display_progress(detailed=args.detailed)


if __name__ == '__main__':
    main()

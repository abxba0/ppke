#!/bin/bash
#
# PPKE v2.0 Phase Execution Wrapper
#
# Usage:
#   ./prompts/run-phase.sh <phase_number>
#   ./prompts/run-phase.sh all
#
# Examples:
#   ./prompts/run-phase.sh 1        # Run Phase 1 only
#   ./prompts/run-phase.sh all      # Run all phases sequentially
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${BOLD}${BLUE}============================================================${NC}"
    echo -e "${BOLD}${BLUE}$1${NC}"
    echo -e "${BOLD}${BLUE}============================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# Determine script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Verify we're in PPKE repo
if [ ! -d "$REPO_ROOT/ppke" ]; then
    print_error "Not in PPKE repository. Please run from repository root."
    exit 1
fi

cd "$REPO_ROOT"

# Parse arguments
PHASE="$1"

if [ -z "$PHASE" ]; then
    print_error "Usage: $0 <phase_number|all>"
    echo ""
    echo "Examples:"
    echo "  $0 1       # Run Phase 1"
    echo "  $0 2       # Run Phase 2"
    echo "  $0 all     # Run all phases"
    exit 1
fi

# Function to run a specific phase
run_phase() {
    local phase_num=$1

    case $phase_num in
        1)
            print_header "Phase 1: Audit & Specification"
            print_info "Running automated audit..."
            python prompts/quick-start-phase-1.py
            ;;
        2)
            print_header "Phase 2: Refactor Core"
            print_warning "Phase 2 requires manual execution or AI assistant."
            print_info "Please read: prompts/phase-2-refactor-core.md"
            print_info ""
            print_info "Key steps:"
            print_info "  1. Convert dataclasses to Pydantic"
            print_info "  2. Create template system"
            print_info "  3. Refactor pipeline"
            print_info "  4. Update CLI"
            print_info ""
            read -p "Press Enter when Phase 2 is complete, or Ctrl+C to cancel..."
            ;;
        3)
            print_header "Phase 3: Plugin Ecosystem"
            print_warning "Phase 3 requires manual execution or AI assistant."
            print_info "Please read: prompts/phase-3-plugin-ecosystem.md"
            print_info ""
            print_info "Key steps:"
            print_info "  1. Implement plugin discovery"
            print_info "  2. Create PLUGINS.md"
            print_info "  3. Build example plugin"
            print_info "  4. Add CLI commands"
            print_info ""
            read -p "Press Enter when Phase 3 is complete, or Ctrl+C to cancel..."
            ;;
        4)
            print_header "Phase 4: System Validation"
            print_warning "Phase 4 requires manual testing."
            print_info "Please read: prompts/phase-4-system-validation.md"
            print_info ""
            print_info "Key steps:"
            print_info "  1. Run backward compatibility tests"
            print_info "  2. Test multi-domain functionality"
            print_info "  3. Performance benchmarks"
            print_info "  4. Security audit"
            print_info "  5. Create migration guide"
            print_info ""
            read -p "Press Enter when Phase 4 is complete, or Ctrl+C to cancel..."
            ;;
        *)
            print_error "Invalid phase number: $phase_num"
            exit 1
            ;;
    esac

    # Show progress after each phase
    echo ""
    python prompts/progress-tracker.py
}

# Main execution
if [ "$PHASE" == "all" ]; then
    print_header "PPKE v2.0 Complete Refactoring"
    print_warning "This will run all 4 phases sequentially."
    print_warning "Estimated time: 56-78 hours of work"
    print_info ""
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi

    # Run all phases
    for phase in 1 2 3 4; do
        run_phase $phase

        if [ $phase -lt 4 ]; then
            echo ""
            print_info "Phase $phase complete. Ready for Phase $((phase + 1))?"
            read -p "Press Enter to continue or Ctrl+C to stop..."
        fi
    done

    print_header "All Phases Complete!"
    print_success "PPKE v2.0 refactoring finished!"
    print_info "Next steps:"
    print_info "  1. Review all changes"
    print_info "  2. Run: pytest tests/ -v"
    print_info "  3. Tag release: git tag v2.0.0"

else
    # Run single phase
    run_phase "$PHASE"

    # Suggest next phase
    if [ "$PHASE" -lt 4 ]; then
        echo ""
        print_info "Next: ./prompts/run-phase.sh $((PHASE + 1))"
    else
        print_success "All phases complete! Ready for release!"
    fi
fi

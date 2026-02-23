@echo off
REM PPKE v2.0 Phase Execution Wrapper (Windows)
REM
REM Usage:
REM   prompts\run-phase.bat <phase_number>
REM   prompts\run-phase.bat all
REM
REM Examples:
REM   prompts\run-phase.bat 1        # Run Phase 1 only
REM   prompts\run-phase.bat all      # Run all phases sequentially
REM

setlocal enabledelayedexpansion

REM Verify we're in PPKE repository
if not exist "ppke\" (
    echo [ERROR] Not in PPKE repository. Please run from repository root.
    exit /b 1
)

REM Parse arguments
set PHASE=%1

if "%PHASE%"=="" (
    echo [ERROR] Usage: %0 ^<phase_number^|all^>
    echo.
    echo Examples:
    echo   %0 1       # Run Phase 1
    echo   %0 2       # Run Phase 2
    echo   %0 all     # Run all phases
    exit /b 1
)

if "%PHASE%"=="all" goto :run_all

REM Run single phase
call :run_phase %PHASE%
if %PHASE% lss 4 (
    echo.
    echo [INFO] Next: prompts\run-phase.bat %PHASE%+1
) else (
    echo [SUCCESS] All phases complete! Ready for release!
)
goto :eof

:run_all
echo ============================================================
echo PPKE v2.0 Complete Refactoring
echo ============================================================
echo.
echo [WARNING] This will run all 4 phases sequentially.
echo [WARNING] Estimated time: 56-78 hours of work
echo.
set /p CONTINUE="Continue? (y/N): "
if /i not "%CONTINUE%"=="y" (
    echo [INFO] Cancelled
    exit /b 0
)

for %%p in (1 2 3 4) do (
    call :run_phase %%p

    if %%p lss 4 (
        echo.
        echo [INFO] Phase %%p complete. Ready for Phase !NEXT_PHASE!?
        pause
    )
)

echo ============================================================
echo All Phases Complete!
echo ============================================================
echo [SUCCESS] PPKE v2.0 refactoring finished!
echo [INFO] Next steps:
echo   1. Review all changes
echo   2. Run: pytest tests/ -v
echo   3. Tag release: git tag v2.0.0
goto :eof

:run_phase
set PHASE_NUM=%1

echo.
echo ============================================================

if %PHASE_NUM%==1 (
    echo Phase 1: Audit ^& Specification
    echo ============================================================
    echo.
    echo [INFO] Running automated audit...
    python prompts\quick-start-phase-1.py
) else if %PHASE_NUM%==2 (
    echo Phase 2: Refactor Core
    echo ============================================================
    echo.
    echo [WARNING] Phase 2 requires manual execution or AI assistant.
    echo [INFO] Please read: prompts\phase-2-refactor-core.md
    echo.
    echo [INFO] Key steps:
    echo   1. Convert dataclasses to Pydantic
    echo   2. Create template system
    echo   3. Refactor pipeline
    echo   4. Update CLI
    echo.
    pause
) else if %PHASE_NUM%==3 (
    echo Phase 3: Plugin Ecosystem
    echo ============================================================
    echo.
    echo [WARNING] Phase 3 requires manual execution or AI assistant.
    echo [INFO] Please read: prompts\phase-3-plugin-ecosystem.md
    echo.
    echo [INFO] Key steps:
    echo   1. Implement plugin discovery
    echo   2. Create PLUGINS.md
    echo   3. Build example plugin
    echo   4. Add CLI commands
    echo.
    pause
) else if %PHASE_NUM%==4 (
    echo Phase 4: System Validation
    echo ============================================================
    echo.
    echo [WARNING] Phase 4 requires manual testing.
    echo [INFO] Please read: prompts\phase-4-system-validation.md
    echo.
    echo [INFO] Key steps:
    echo   1. Run backward compatibility tests
    echo   2. Test multi-domain functionality
    echo   3. Performance benchmarks
    echo   4. Security audit
    echo   5. Create migration guide
    echo.
    pause
) else (
    echo [ERROR] Invalid phase number: %PHASE_NUM%
    exit /b 1
)

REM Show progress after each phase
echo.
python prompts\progress-tracker.py

goto :eof

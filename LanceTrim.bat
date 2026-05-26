@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "VENV_PYTHON="
if exist ".venv\Scripts\python.exe" set "VENV_PYTHON=.venv\Scripts\python.exe"
if not defined VENV_PYTHON if exist "venv\Scripts\python.exe" set "VENV_PYTHON=venv\Scripts\python.exe"

if defined VENV_PYTHON (
    set "PYTHON=!VENV_PYTHON!"
    echo [info] Venv detecte : !VENV_PYTHON!
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERREUR] Python introuvable dans le PATH.
        echo Installer Python 3.10+ depuis https://www.python.org/downloads/
        echo Cocher "Add Python to PATH" lors de l'installation.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

"%PYTHON%" -c "import trimtokens" 2>nul
if errorlevel 1 (
    if exist "src\trimtokens\__init__.py" (
        set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
        echo [info] Mode dev : PYTHONPATH=src
    ) else (
        echo [ERREUR] trimtokens n'est pas installe et src/ est absent.
        echo Installer via : pip install trimtokens[ocr,gui]
        pause
        exit /b 1
    )
)

if /i "%~1"=="cli" goto :launch_cli
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
goto :launch_gui

:launch_gui
echo [info] Lancement interface graphique...
"%PYTHON%" -m trimtokens.gui
set "EXIT_CODE=!errorlevel!"
goto :end

:launch_cli
shift
echo [info] Lancement CLI...
"%PYTHON%" -m trimtokens.cli %1 %2 %3 %4 %5 %6 %7 %8 %9
set "EXIT_CODE=!errorlevel!"
goto :end

:show_help
echo.
echo LanceTrim.bat - Lanceur Windows pour TrimTokens
echo.
echo Usage :
echo   LanceTrim.bat              Lance l'interface graphique
echo   LanceTrim.bat cli ^<args^>   Lance la CLI avec arguments
echo   LanceTrim.bat --help       Affiche cette aide
echo.
echo Exemples :
echo   LanceTrim.bat
echo   LanceTrim.bat cli document.pdf
echo   LanceTrim.bat cli "./dossier/" --recursive --out "./clean/"
echo.
set "EXIT_CODE=0"
goto :end

:end
if not "!EXIT_CODE!"=="0" (
    echo.
    echo [ERREUR] Code de sortie : !EXIT_CODE!
    pause
)
endlocal & exit /b %EXIT_CODE%

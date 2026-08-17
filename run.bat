@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
if "%1"=="sync" goto sync
if "%1"=="build" goto build
if "%1"=="test" goto test
if "%1"=="all" goto all
if "%1"=="feasibility" goto feasibility
python -m park_observer.cli build --output site --feasibility-input data\assessments\example.json || exit /b 1
python -m park_observer.cli validate --site site || exit /b 1
python -m park_observer.cli serve --site site --port 8765
exit /b %errorlevel%
:sync
python -m park_observer.cli sync
exit /b %errorlevel%
:build
python -m park_observer.cli build --output site --feasibility-input data\assessments\example.json || exit /b 1
python -m park_observer.cli validate --site site
exit /b %errorlevel%
:test
python -m unittest discover -s tests -v || exit /b 1
node --check static\app.js
exit /b %errorlevel%
:all
python -m park_observer.cli all --output site --feasibility-input data\assessments\example.json
exit /b %errorlevel%
:feasibility
python -m park_observer.cli feasibility --input data\assessments\example.json --output outputs\feasibility_result.json
exit /b %errorlevel%

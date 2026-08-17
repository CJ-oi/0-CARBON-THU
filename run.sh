#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
command_name="${1:-serve}"
case "$command_name" in
  sync) python -m park_observer.cli sync ;;
  build) python -m park_observer.cli build --output site --feasibility-input data/assessments/example.json && python -m park_observer.cli validate --site site ;;
  test) python -m unittest discover -s tests -v && node --check static/app.js ;;
  all) python -m park_observer.cli all --output site --feasibility-input data/assessments/example.json ;;
  feasibility) python -m park_observer.cli feasibility --input "${2:-data/assessments/example.json}" --output outputs/feasibility_result.json ;;
  serve|*) python -m park_observer.cli build --output site --feasibility-input data/assessments/example.json && python -m park_observer.cli validate --site site && python -m park_observer.cli serve --site site --port "${2:-8765}" ;;
esac

param(
  [ValidateSet("serve","sync","build","test","all","feasibility")]
  [string]$Command = "serve",
  [string]$Input = "data/assessments/example.json",
  [int]$Port = 8765
)
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
Set-Location $PSScriptRoot
switch ($Command) {
  "sync" { python -m park_observer.cli sync }
  "build" { python -m park_observer.cli build --output site --feasibility-input $Input; python -m park_observer.cli validate --site site }
  "test" { python -m unittest discover -s tests -v; node --check static/app.js }
  "all" { python -m park_observer.cli all --output site --feasibility-input $Input }
  "feasibility" { python -m park_observer.cli feasibility --input $Input --output outputs/feasibility_result.json }
  default {
    python -m park_observer.cli build --output site --feasibility-input $Input
    python -m park_observer.cli validate --site site
    python -m park_observer.cli serve --site site --port $Port
  }
}

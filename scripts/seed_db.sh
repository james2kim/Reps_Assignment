#!/usr/bin/env bash
set -e
echo "Seeding relational data..."
python -m backend.app.ingestion.seed_relational_data

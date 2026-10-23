"""Explicit, local-only prototype runner. No application or external services."""
import argparse
import json
from pathlib import Path

from . import prepare_context

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('input', type=Path, help='JSON object with records and selected_ids')
parser.add_argument('--enable-experiment', action='store_true')
parser.add_argument('--birth-order', action='store_true')
parser.add_argument('--gender-role-experiences', action='store_true')
args = parser.parse_args()
try:
    data = json.loads(args.input.read_text())
    print(json.dumps(prepare_context(data.get('records', {}), data.get('selected_ids', []),
          experiment_enabled=args.enable_experiment,
          options={'birth_order': args.birth_order, 'gender_role_experiences': args.gender_role_experiences}), indent=2))
except (ValueError, OSError, AttributeError) as error:
    parser.exit(2, f'Invalid experimental context: {error}\n')

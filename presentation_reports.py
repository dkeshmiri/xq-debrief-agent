"""Validate source-report visuals without accepting arbitrary URLs or HTML."""
from copy import deepcopy
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def report_visuals(bundle):
    def text(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('Report labels must be nonempty text of at most 2000 characters.')

    source = bundle.get('source')
    text(source)
    visuals = bundle.get('visuals')
    if not isinstance(visuals, dict) or not 1 <= len(visuals) <= 30:
        raise ValueError('Supply between 1 and 30 report visuals.')
    for key, chart in visuals.items():
        text(key)
        if not isinstance(chart, dict):
            raise ValueError('Report visuals must be objects.')
        text(chart.get('title')); text(chart.get('note'))
        if chart.get('kind') == 'discussion':
            points = chart.get('points')
            if not isinstance(points, list) or not 1 <= len(points) <= 8:
                raise ValueError('Supply between 1 and 8 discussion points.')
            for point in points: text(point)
        elif chart.get('kind') == 'report_gallery':
            items = chart.get('items')
            if not isinstance(items, list) or not 1 <= len(items) <= 8:
                raise ValueError('Supply between 1 and 8 report images.')
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError('Report images must be objects.')
                for field in ('title', 'alt', 'attribution'): text(item.get(field))
                image = item.get('image')
                if (not isinstance(image, str) or not re.fullmatch(
                        r'/static/presentation-assets/[a-z0-9-]+/[a-z0-9-]+\.png', image)
                        or not (ROOT / image.lstrip('/')).is_file()):
                    raise ValueError('Choose an installed report image.')
        else:
            raise ValueError('Unknown report visual type.')
    return deepcopy(visuals), source

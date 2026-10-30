"""Validate data-only investor graphics independently of assessment schemas."""
from copy import deepcopy
from math import isfinite


def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError(f'{label} must be nonempty text of at most 2000 characters.')


def investor_visuals(bundle):
    source = bundle.get('source')
    text(source, 'Source')
    visuals = bundle.get('visuals')
    if not isinstance(visuals, dict) or not 1 <= len(visuals) <= 30:
        raise ValueError('Supply between 1 and 30 investor graphics.')
    for key, chart in visuals.items():
        text(key, 'Chart key')
        if not isinstance(chart, dict) or chart.get('kind') != 'investor':
            raise ValueError('Investor bundles must use investor graphics.')
        if chart.get('layout') not in ('cards', 'steps', 'bars'):
            raise ValueError('Unknown investor graphic layout.')
        for field in ('title', 'note', 'source', 'takeaway'):
            text(chart.get(field), field)
        items = chart.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 8:
            raise ValueError('Each graphic needs between 1 and 8 items.')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Graphic items must be objects.')
            text(item.get('label'), 'Label')
            if chart['layout'] != 'bars':
                text(item.get('value'), 'Value')
                text(item.get('detail'), 'Detail')
                continue
            text(item.get('unit'), 'Unit')
            bars = item.get('bars')
            if not isinstance(bars, list) or not 1 <= len(bars) <= 8:
                raise ValueError('Each bar group needs between 1 and 8 bars.')
            for bar in bars:
                if not isinstance(bar, dict):
                    raise ValueError('Each bar must be an object.')
                text(bar.get('label'), 'Bar label')
                value = bar.get('value')
                if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1e15:
                    raise ValueError('Bar values must be finite, nonnegative numbers up to 1e15.')
    return deepcopy(visuals), source

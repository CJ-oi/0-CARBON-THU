from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
NE_PATH = Path('/opt/pyvenv/lib/python3.13/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp')
CHINA_PATH = Path('/opt/pyvenv/lib/python3.13/site-packages/countryinfo/data/china.json')


def round_coords(obj, digits=4):
    if isinstance(obj, (list, tuple)):
        return [round_coords(x, digits) for x in obj]
    if isinstance(obj, float):
        return round(obj, digits)
    return obj


def main() -> None:
    world = gpd.read_file(NE_PATH)
    features = []
    for _, row in world.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        # A light simplification is enough for a web overview while preserving coastlines.
        geom = geom.simplify(0.08, preserve_topology=True)
        features.append({
            'type': 'Feature',
            'properties': {
                'name': str(row.get('name') or ''),
                'iso_a3': str(row.get('iso_a3') or ''),
                'continent': str(row.get('continent') or ''),
            },
            'geometry': round_coords(mapping(geom)),
        })

    china_data = json.loads(CHINA_PATH.read_text(encoding='utf-8'))
    china_feature = china_data['geoJSON']['features'][0]
    china_geom = shape(china_feature['geometry']).simplify(0.025, preserve_topology=True)
    china = {
        'type': 'Feature',
        'properties': {'name': 'China', 'iso_a3': 'CHN'},
        'geometry': round_coords(mapping(china_geom)),
    }

    payload = {
        'generated_from': 'Natural Earth low-resolution countries and CountryInfo China geometry',
        'coordinate_reference_system': 'EPSG:4326',
        'world': {'type': 'FeatureCollection', 'features': features},
        'china': china,
        'views': {
            '全国': {'west': 72.0, 'east': 136.5, 'south': 17.0, 'north': 54.5},
            '国家级': {'west': 72.0, 'east': 136.5, 'south': 17.0, 'north': 54.5},
            '广东': {'west': 108.8, 'east': 118.2, 'south': 19.0, 'north': 26.2},
            '全球': {'west': -180.0, 'east': 180.0, 'south': -58.0, 'north': 84.0},
        },
    }
    out = ROOT / 'static/assets/maps/map_geometry.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(out, out.stat().st_size)


if __name__ == '__main__':
    main()

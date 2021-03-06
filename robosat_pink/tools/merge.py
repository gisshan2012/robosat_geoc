import sys
import argparse

import geojson

from tqdm import tqdm
import shapely.geometry

from robosat_pink.spatial.core import make_index, project, union
from robosat_pink.graph.core import UndirectedGraph
from app.config import setting as SETTING


def add_parser(subparser):
    parser = subparser.add_parser(
        "merge", help="merged adjacent GeoJSON features", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("features", type=str,
                        help="GeoJSON file to read features from")
    parser.add_argument("--threshold", type=int, required=True,
                        help="minimum distance to adjacent features, in m")
    parser.add_argument(
        "out", type=str, help="path to GeoJSON to save merged features to")

    parser.set_defaults(func=main)


def main(args):
    with open(args.features) as fp:
        collection = geojson.load(fp)

    shapes = [shapely.geometry.shape(feature["geometry"])
              for feature in collection["features"]]
    del collection

    graph = UndirectedGraph()
    idx = make_index(shapes)

    def buffered(shape):
        projected = project(shape, "epsg:4326", "epsg:3857")
        buffered = projected.buffer(args.threshold)
        unprojected = project(buffered, "epsg:3857", "epsg:4326")
        return unprojected

    def unbuffered(shape):
        projected = project(shape, "epsg:4326", "epsg:3857")
        # if int(round(projected.area)) < 100:
        #     return None
        unbuffered = projected.buffer(-1 * args.threshold)
        unprojected = project(unbuffered, "epsg:3857", "epsg:4326")
        return unprojected

    for i, shape in enumerate(tqdm(shapes, desc="Building graph", unit="shapes", ascii=True)):
        embiggened = buffered(shape)

        graph.add_edge(i, i)

        nearest = [j for j in idx.intersection(
            embiggened.bounds, objects=False) if i != j]

        for t in nearest:
            if embiggened.intersects(shapes[t]):
                graph.add_edge(i, t)

    components = list(graph.components())
    assert sum([len(v) for v in components]) == len(
        shapes), "components capture all shape indices"

    features = []

    for component in tqdm(components, desc="Merging components", unit="component", ascii=True):
        embiggened = [buffered(shapes[v]) for v in component]
        merged = unbuffered(union(embiggened))
        if not merged:
            continue
        if merged.is_valid:
            # Orient exterior ring of the polygon in counter-clockwise direction.
            if isinstance(merged, shapely.geometry.polygon.Polygon):
                merged = shapely.geometry.polygon.orient(merged, sign=1.0)
            elif isinstance(merged, shapely.geometry.multipolygon.MultiPolygon):
                merged = [shapely.geometry.polygon.orient(
                    geom, sign=1.0) for geom in merged.geoms]
                merged = shapely.geometry.MultiPolygon(merged)
            else:
                print(
                    "Warning: merged feature is neither Polygon nor MultiPoylgon, skipping", file=sys.stderr)
                continue

            # equal-area projection; round to full m^2, we're not that precise anyway
            area = int(round(project(merged, "epsg:4326", "epsg:3857").area))
            if area < SETTING.MIN_BUILDING_AREA:
                continue

            feature = geojson.Feature(geometry=shapely.geometry.mapping(
                merged))  # , properties={"area": area}
            features.append(feature)
        else:
            print("Warning: merged feature is not valid, skipping",
                  file=sys.stderr)

    collection = geojson.FeatureCollection(features)

    with open(args.out, "w") as fp:
        geojson.dump(collection, fp)

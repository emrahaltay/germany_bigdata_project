import matplotlib.pyplot as plt
from shapely.geometry import Polygon as ShapelyPolygon, MultiPolygon
from shapely.prepared import prep
import osmnx as ox
import h3

GERMANY_GDF = ox.geocode_to_gdf("Germany")
GERMANY_SHAPELY = GERMANY_GDF.geometry.values[0]

# Kapsama için hazır geometri: çok detaylı sınırı hafifçe sadeleştir (≈5 m tolerans)
GERMANY_SHAPELY = GERMANY_SHAPELY.buffer(0).simplify(5e-5, preserve_topology=True)
GERMANY_PREP = prep(GERMANY_SHAPELY)

# Basitleştirilmiş sınır: kırpma ve çizim için dış çevre koordinatları
if isinstance(GERMANY_SHAPELY, MultiPolygon):
    sorted_parts = sorted(GERMANY_SHAPELY.geoms, key=lambda p: p.area, reverse=True)
    OUTLINE_GEOM = sorted_parts[0]
else:
    OUTLINE_GEOM = GERMANY_SHAPELY
GERMANY_BOUNDARY = [[lat, lng] for lng, lat in OUTLINE_GEOM.exterior.coords]

LEVELS = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
}

def find_cells(resolution):
    result = set()
    seen = set()
    stack = []

    # Almanya içinde olduğu bilinen bir noktadan başla
    interior_pt = GERMANY_SHAPELY.representative_point()
    seed = h3.latlng_to_cell(interior_pt.y, interior_pt.x, resolution)
    stack.append(seed)
    seen.add(seed)

    while stack:
        cell = stack.pop()
        boundary = h3.cell_to_boundary(cell)
        hex_poly = ShapelyPolygon([(lng, lat) for lat, lng in boundary])
        if not GERMANY_PREP.intersects(hex_poly):
            continue
        result.add(cell)
        for n in h3.grid_disk(cell, 1):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return sorted(result)

def generate_kml(resolution, level):
    cells = find_cells(resolution)

    placemarks = []
    for i, cell in enumerate(sorted(cells)):
        hexagon_name = f"{level}_HEX_{i+1}"
        boundary = h3.cell_to_boundary(cell)
        hex_poly = ShapelyPolygon([(lng, lat) for lat, lng in boundary])
        if GERMANY_PREP.covers(hex_poly):
            clipped = hex_poly
        else:
            clipped = GERMANY_SHAPELY.intersection(hex_poly)
            if clipped.is_empty:
                continue

        def poly_ring(clipped_poly):
            ring = " ".join(f"{x},{y},0.0" for x, y in clipped_poly.exterior.coords)
            inner = ""
            for interior in clipped_poly.interiors:
                inner += f"""
          <innerBoundaryIs>
            <LinearRing>
              <coordinates>
                {" ".join(f"{x},{y},0.0" for x, y in interior.coords)}
              </coordinates>
            </LinearRing>
          </innerBoundaryIs>"""
            return ring, inner

        polygons_xml = ""
        if isinstance(clipped, MultiPolygon):
            parts = clipped.geoms
        else:
            parts = [clipped]
        for part in parts:
            if part.is_empty:
                continue
            ring, inner = poly_ring(part)
            polygons_xml += f"""
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                {ring}
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>{inner}
        </Polygon>"""

        if not polygons_xml:
            continue

        placemarks.append(f"""    <Placemark>
      <name>{hexagon_name}</name>
      <styleUrl>#hexStyle</styleUrl>
      <MultiGeometry>{polygons_xml}
      </MultiGeometry>
    </Placemark>""")

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Germany H3 Hexagons - Level {level}</name>
    <Style id="hexStyle">
      <LineStyle>
        <colorMode>normal</colorMode>
        <width>1</width>
      </LineStyle>
      <PolyStyle>
        <color>4D00FF00</color>
        <colorMode>normal</colorMode>
        <fill>1</fill>
        <outline>1</outline>
      </PolyStyle>
    </Style>
{chr(10).join(placemarks)}
  </Document>
</kml>"""
    return kml

def plot_germany_hexagons(resolution, level, outfile):
    cells = find_cells(resolution)

    fig, ax = plt.subplots(figsize=(10, 12))

    for cell in sorted(cells):
        boundary = h3.cell_to_boundary(cell)
        hex_poly = ShapelyPolygon([(lng, lat) for lat, lng in boundary])
        if GERMANY_PREP.covers(hex_poly):
            clipped = hex_poly
        else:
            clipped = GERMANY_SHAPELY.intersection(hex_poly)
            if clipped.is_empty:
                continue
        parts = clipped.geoms if isinstance(clipped, MultiPolygon) else [clipped]
        for part in parts:
            if part.is_empty:
                continue
            xs, ys = part.exterior.xy
            ax.fill(xs, ys, alpha=0.35, linewidth=0.4,
                    edgecolor="black", facecolor="lightblue")

    # Germany boundary
    blngs = [p[1] for p in GERMANY_BOUNDARY]
    blats = [p[0] for p in GERMANY_BOUNDARY]
    ax.plot(blngs, blats, color="red", linewidth=2, label="Germany boundary")

    ax.set_title(f"Germany H3 Hexagons - Level {level} (Resolution {resolution})")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="upper left")
    ax.set_aspect(1.0 / (110.0 * 111000.0 / 100000.0))
    ax.grid(True, linestyle="--", alpha=0.5)

    fig.tight_layout()
    fig.savefig(outfile, dpi=150)
    plt.close(fig)
    print(f"    -> {outfile}")

if __name__ == "__main__":
    for level, res in LEVELS.items():
        print(f"Level {level} -> Resolution {res} ...", end=" ")
        kml = generate_kml(res, level)
        outfile = f"germany_h3_level{level}_res{res}.kml"
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(kml)
        count = kml.count("<Placemark>")
        print(f"{count} hexagons -> {outfile}")
        plot_germany_hexagons(res, level, f"germany_h3_level{level}_res{res}.png")

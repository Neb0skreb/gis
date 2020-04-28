import json
import os
import gdal
import ogr
import subprocess
from osgeo import ogr
import glob

for file in glob.glob('*.tif'):
    dg_file = file


ELEVATION_LIMIT_M = 10000
def _read_dem_data_n_nod(dem):
    """
    Reads and amends DEM's data and NoData value. Both should be in
    [-ELEVATION_LIMIT_M, ELEVATION_LIMIT_M] interval. All values off this interval
    replaced with NoData
    """
    nod = gdal.Info(dem, format='json')['bands'][0]['noDataValue']
    if not -ELEVATION_LIMIT_M < nod < ELEVATION_LIMIT_M:
        nod = ELEVATION_LIMIT_M

    data = dem.ReadAsArray()
    data[data > ELEVATION_LIMIT_M] = nod
    data[data < -ELEVATION_LIMIT_M] = nod

    return data, nod


def write_dem_to_file(template, data, file_name, nod=None):
    # Open source file
    gt = template.GetGeoTransform()
    proj = template.GetProjection()

    # Get rasterarray
    blurredArray = data

    # Register driver
    driver = gdal.GetDriverByName('GTIFF')
    driver.Register()

    # Get source metadata
    cols = template.RasterXSize
    rows = template.RasterYSize
    bands = template.RasterCount
    band = template.GetRasterBand(1)
    datatype = band.DataType

    # Create output image
    output = driver.Create(file_name, cols, rows, bands, datatype, ['COMPRESS=LZW'])
    output.SetGeoTransform(gt)
    output.SetProjection(proj)

    # Get band from newly created image
    outBand = output.GetRasterBand(1)
    outBand.SetNoDataValue(nod if nod else band.GetNoDataValue())

    # Write to file
    outBand.WriteArray(blurredArray, 0, 0)

WORK_DIR = './generated'

def gen_cfm(dg_file):
    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)

    dg_dem = gdal.Open(dg_file)
    dg_arr, nod = _read_dem_data_n_nod(dg_dem)

    mask_file = f'{WORK_DIR}/boundary_mask.tif'
    to_boundary = 1 * (dg_arr != nod) - 1 * (dg_arr == nod)
    write_dem_to_file(dg_dem, to_boundary, mask_file)
    process_mask('boundary', mask_file, smpl=0.75)

def store(file_name, data):

    with open(file_name, 'w') as file:
        json.dump(data, file, ensure_ascii=True)
#


def process_mask(name, mask_file, smpl=None):
    contour_file = f'{WORK_DIR}/{name}_countour.geojson'
    contour_wgs_file = f'{WORK_DIR}/{name}_countour_wgs.geojson'
    subprocess.call("gdal_contour -i 10 -f GeoJSON".split(' ') + [mask_file, contour_file])

    simplify_opt = ["-simplify", f'{smpl}'] if smpl else []
    subprocess.call(["ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:4326", contour_wgs_file, contour_file] + simplify_opt)

    with open(contour_wgs_file) as data_file:
        contours = json.load(data_file)

    features = contours['features']

    good_features = []
    for f in features:
        coords = f['geometry']['coordinates']

        geom = {
            'type': 'Polygon',
            'coordinates': [coords]
        }
        poly = ogr.CreateGeometryFromJson(json.dumps(geom))
        area = poly.GetArea()


        good_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {"name": f'{len(good_features) + 1}'}
            })


    store(f'{WORK_DIR}/{name}_final.geojson', {
        "type": "FeatureCollection",
        "features": good_features
    })

gen_cfm(dg_file)



fileslist = glob.glob('*.geojson')
for elem in fileslist:

    with open(elem) as f:
        wkt1 = json.load(f)
    with open('./generated/boundary_final.geojson') as f:
        wkt2 = json.load(f)

    total_polygon = None

    if wkt1['type'] == 'Feature':
        json_geom_1 = json.dumps(wkt1['geometry'])
        geom1 = ogr.CreateGeometryFromJson(json_geom_1)

    if wkt1['type'] == 'FeatureCollection':
        for feature in wkt1['features']:
            geom1 = ogr.CreateGeometryFromJson(json.dumps(feature['geometry']))



    for feature in wkt2['features']:
        geom2 = ogr.CreateGeometryFromJson(json.dumps(feature['geometry']))

        if total_polygon:
            total_polygon = total_polygon.Union(geom2)
        else:
            total_polygon = geom2

    diff_geom = geom1.Difference(total_polygon)
    deff_json = json.loads(diff_geom.ExportToJson())

    # store('new_' + elem, deff_json)
    if not deff_json['coordinates']:
        print(elem + " hasn't intersections with .tif")
    else :
        store('new_'+elem, deff_json)



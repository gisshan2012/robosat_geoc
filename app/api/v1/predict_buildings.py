from sqlalchemy import or_
from app.models.base import queryBySQL, db as DB
from app.libs.redprint import Redprint
from app.models.predict_buildings import PredictBuildings
from app.models.base import queryBySQL
from flask import jsonify
from flask import request
from geomet import wkb

import json

api = Redprint('predict_buildings')


@api.route("", methods=['GET'])
def onegeojson():
    result = {
        "code": 1,
        "data": None,
        "msg": "ok"
    }
    extent = request.args.get("extent")
    if not extent:
        result["code"] = 0
        result["msg"] = "参数有误"
        return jsonify(result)
    # coords = extent.split(',')
    sql = '''SELECT
	jsonb_build_object ( 'type', 'FeatureCollection', 'features', jsonb_agg ( features.feature ) ) 
FROM
	(
	SELECT
		jsonb_build_object ( 'type', 'Feature', 'id', gid, 'geometry', ST_AsGeoJSON ( geom ) :: jsonb, 'properties', to_jsonb ( inputs ) - 'geom' ) AS feature 
	FROM
		(
		SELECT gid,geom AS geom 
		FROM "predict_buildings" WHERE
			geom @
		ST_MakeEnvelope ( {extent}, {srid} )) inputs 
	) features; '''
    queryData = queryBySQL(sql.format(extent=extent, srid=4326))
    if not queryData:
        result["code"] = 0
        result["msg"] = "查询语句有问题"
        return jsonify(result)
    row = queryData.fetchone()
    result["data"] = row

    return jsonify(result)


@api.route("/<gid>", methods=['GET'])
def get(gid):
    result = {
        "code": 1,
        "data": None,
        "msg": "ok"
    }
    sql = '''select st_asgeojson(geom) as geojson from predict_buildings where gid ={gid}'''
    queryData = queryBySQL(sql.format(gid=gid))
    if not queryData:
        result["code"] = 0
        result["msg"] = "查询语句有问题"
        return jsonify(result)
    if queryData.rowcount == 0:
        result["code"] = 0
        result["msg"] = "未查询到内容"
        return jsonify(result)
    row = queryData.fetchone()
    result["data"] = json.loads(row["geojson"])
    return jsonify(result)


@api.route('', methods=['POST'])
def create_buildings(geojsonObj):
    result = {
        "code": 1,
        "data": None,
        "msg": "ok"
    }
    # check params
    if request.json:
        paramsDic = request.json
        params = json.loads(json.dumps(paramsDic))
        geojson = params['geojson']
    else:
        geojson = geojsonObj

    buildings = []
    for feature in geojson["features"]:
        # featureDump = json.dumps(feature)
        # newFeat = '{"type":"FeatureCollection","features":['+featureDump+']}'

        # newFeature = json.loads(newFeat)
        newBuild = PredictBuildings()
        newBuild.task_id = feature["properties"]['task_id']
        newBuild.extent = feature["properties"]['extent']
        newBuild.user_id = feature["properties"]['user_id']
        buildings.append(newBuild)

    # insert into
    with DB.auto_commit():
        DB.session.bulk_save_objects(buildings)
        return jsonify(result)


def insert_buildings(geojsonObj):
    if not geojsonObj:
        return False

    # geojson to buildings array
    buildings = []
    for feature in geojsonObj["features"]:
        geometry = feature['geometry']
        newBuild = PredictBuildings()
        newBuild.task_id = feature["properties"]['task_id']
        newBuild.extent = feature["properties"]['extent']
        newBuild.user_id = feature["properties"]['user_id']
        newBuild.geom = wkb.dumps(geometry).hex()
        buildings.append(newBuild)

    # insert into
    with DB.auto_commit():
        DB.session.bulk_save_objects(buildings)
        return True
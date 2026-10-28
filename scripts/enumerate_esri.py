import json,csv,urllib.request,urllib.parse,concurrent.futures as cf
B="https://services.arcgis.com/s8wtJX9suxFen6TA/ArcGIS/rest/services"
def g(u):
    for i in range(3):
        try: return json.load(urllib.request.urlopen(u,timeout=60))
        except Exception as e: err=e
    return {"error":str(err)}
hub={}
off=0
while True:
    d=g(f"https://data-floridaswater.opendata.arcgis.com/api/search/v1/collections/dataset/items?limit=100&startindex={off}")
    fs=d.get("features",[])
    for f in fs:
        p=f["properties"];u=(p.get("url") or "").rstrip("/")
        hub.setdefault(u,[]).append((f.get("id"),p.get("title")))
    if len(fs)<100: break
    off+=100
svcs=g(B+"?f=json")["services"]
def do(s):
    url=f"{B}/{s['name']}/FeatureServer"; sv=g(url+"?f=json"); rows=[]
    for kind in ("layers","tables"):
        for l in sv.get(kind,[]):
            lu=f"{url}/{l['id']}"; li=g(lu+"?f=json"); c=g(lu+"/query?where=1%3D1&returnCountOnly=true&f=json")
            ei=li.get("editingInfo") or {}
            h=hub.get(lu) or hub.get(url) or []
            rows.append(dict(service=s["name"],layer_id=l["id"],layer_name=l.get("name"),kind=kind[:-1],
              geometry_type=li.get("geometryType",""),feature_count=c.get("count",""),max_record_count=li.get("maxRecordCount",""),
              change_tracking=sv.get("syncEnabled",False) or "ChangeTracking" in (sv.get("capabilities") or ""),
              last_edit_date=ei.get("lastEditDate",""),edit_fields=bool(li.get("editFieldsInfo")),
              hub_item_id=";".join(x[0] for x in h),hub_title=";".join(x[1] for x in h),url=lu))
    if not rows: rows.append(dict(service=s["name"],url=url,layer_name="(no layers / error)"))
    return rows
out=[]
with cf.ThreadPoolExecutor(4) as ex:
    for r in ex.map(do,svcs): out+=r
k=["service","layer_id","layer_name","kind","geometry_type","feature_count","max_record_count","change_tracking","last_edit_date","edit_fields","hub_item_id","hub_title","url"]
w=csv.DictWriter(open("esri_inventory.csv","w",newline=""),fieldnames=k);w.writeheader();w.writerows(out)
print("hub items",sum(len(v) for v in hub.values()),"services",len(svcs),"rows",len(out))

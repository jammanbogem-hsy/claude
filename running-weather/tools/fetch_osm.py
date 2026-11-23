"""행당동 주변 OSM 데이터를 OSM API에서 조각(5×5)으로 받아 osm.pkl로 합친다.
사용법: python3 tools/fetch_osm.py <작업폴더>   →   python3 tools/build_map.py <작업폴더>/osm.pkl data/haengdang-map.js
지도 데이터 © OpenStreetMap contributors (ODbL)."""
import subprocess, time, os, sys, glob, pickle
import xml.etree.ElementTree as ET
work = sys.argv[1]; os.makedirs(f"{work}/tiles", exist_ok=True)
lat0, lat1, lon0, lon1, n = 37.527, 37.567, 127.017, 127.058, 5
for i in range(n):
    for j in range(n):
        a, b = lat0 + (lat1 - lat0) * i / n, lat0 + (lat1 - lat0) * (i + 1) / n
        c, d = lon0 + (lon1 - lon0) * j / n, lon0 + (lon1 - lon0) * (j + 1) / n
        f = f"{work}/tiles/t{i}{j}.osm"
        if os.path.exists(f) and os.path.getsize(f) > 1000: continue
        subprocess.run(["curl", "-s", "-m", "120", "-A", "runweather-classroom-demo/1.0", "-o", f,
                        f"https://api.openstreetmap.org/api/0.6/map?bbox={c:.5f},{a:.5f},{d:.5f},{b:.5f}"], check=True)
        time.sleep(1)
nodes, ways, rels = {}, {}, {}
for f in sorted(glob.glob(f"{work}/tiles/*.osm")):
    for ev, el in ET.iterparse(f):
        tags = lambda: {t.get('k'): t.get('v') for t in el.findall('tag')}
        if el.tag == 'node': nodes[int(el.get('id'))] = (float(el.get('lat')), float(el.get('lon')), tags()); el.clear()
        elif el.tag == 'way': ways[int(el.get('id'))] = ([int(x.get('ref')) for x in el.findall('nd')], tags()); el.clear()
        elif el.tag == 'relation': rels[int(el.get('id'))] = ([(m.get('type'), int(m.get('ref')), m.get('role')) for m in el.findall('member')], tags()); el.clear()
pickle.dump((nodes, ways, rels), open(f"{work}/osm.pkl", "wb"))
print(len(nodes), "nodes", len(ways), "ways", len(rels), "relations")

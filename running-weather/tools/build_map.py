"""OSM 데이터(osm.pkl)에서 런웨더 지도 데이터(data/haengdang-map.js)를 만든다.
지도 데이터 © OpenStreetMap contributors (ODbL). 좌표는 행당역 기준 m (x=동쪽, y=남쪽)."""
import pickle, math, heapq, json, random, sys, collections
from shapely.geometry import LineString, Polygon, box, Point, MultiLineString
from shapely.ops import polygonize, unary_union, linemerge
from shapely.strtree import STRtree

SRC, OUT = sys.argv[1], sys.argv[2]
nodes, ways, rels = pickle.load(open(SRC, 'rb'))
LAT0, LON0, KX, KY = 37.55701, 127.02881, 88368.0, 110989.0
def ll2xy(la, lo): return ((lo - LON0) * KX, (LAT0 - la) * KY)
def nxy(n): la, lo, _ = nodes[n]; return ll2xy(la, lo)
BB = box(-1040, -1100, 2570, 3320)
def wline(w): return [nxy(n) for n in ways[w][0] if n in nodes]

# ---------- 물 ----------
def rel_lines(rid):
    out = []
    for typ, ref, role in rels[rid][0]:
        if typ == 'way' and ref in ways: out.append(LineString(wline(ref)))
    return out
centerlines = [LineString(wline(w)) for w, (nd, t) in ways.items() if t.get('waterway') == 'river' and len(nd) > 1]
water_lines = []
for rid, (m, t) in rels.items():
    if t.get('type') == 'multipolygon' and (t.get('natural') == 'water' or t.get('waterway') == 'riverbank') and t.get('water') in ('river', None):
        water_lines += [l for l in rel_lines(rid) if len(l.coords) > 1]
noded = unary_union([l.intersection(BB) for l in water_lines] + [BB.exterior])
faces = list(polygonize(noded))
cl = unary_union(centerlines)
# 강 중심선이 지나가는 면만 물로 본다. 단, 건물이 많이 들어 있는 면은 강둑 선이 끊겨 잘못 생긴 면이라 뺀다.
_bc = [Polygon([nxy(n) for n in nd]).centroid for w, (nd, t) in ways.items() if 'building' in t and nd[0] == nd[-1] and len(nd) > 3 and all(n in nodes for n in nd)]
_btree = STRtree(_bc)
river_polys = []
for f in faces:
    if not f.buffer(-2).intersects(cl): continue
    nb = sum(1 for i in _btree.query(f) if f.contains(_bc[i]))
    print('  face area', round(f.area), 'buildings', nb)
    if nb < 15: river_polys.append(f)
lakes = []
for w, (nd, t) in ways.items():
    if (t.get('natural') == 'water' or t.get('waterway') == 'riverbank') and nd[0] == nd[-1] and len(nd) > 3:
        p = Polygon(wline(w)).buffer(0)
        if p.area > 50 and p.intersects(BB): lakes.append(p.intersection(BB))
water = unary_union(river_polys + lakes)
print('water area km2', round(water.area / 1e6, 3), 'faces', len(faces), 'river faces', len(river_polys))

# ---------- 초록 ----------
GREEN_KEYS = {('leisure','park'):'park', ('leisure','garden'):'park', ('leisure','playground'):'park', ('leisure','pitch'):'pitch', ('leisure','sports_centre'):'pitch',
              ('landuse','grass'):'grass', ('landuse','forest'):'forest', ('landuse','recreation_ground'):'park', ('landuse','meadow'):'grass', ('landuse','village_green'):'grass',
              ('natural','wood'):'forest', ('natural','scrub'):'forest', ('natural','grassland'):'grass'}
def gkind(t):
    for (k, v), g in GREEN_KEYS.items():
        if t.get(k) == v: return g
greens = []
named_parks = []
for w, (nd, t) in ways.items():
    g = gkind(t)
    if g and nd[0] == nd[-1] and len(nd) > 3:
        p = Polygon(wline(w)).buffer(0)
        if p.area > 30 and p.intersects(BB): greens.append((g, p.intersection(BB))); 
        if t.get('name') and p.area > 6000: named_parks.append((t['name'], p))
for rid, (m, t) in rels.items():
    g = gkind(t)
    if g and t.get('type') == 'multipolygon':
        ls = [l for l in rel_lines(rid) if len(l.coords) > 1]
        polys = list(polygonize(unary_union(ls)))
        if polys:
            outer = unary_union(polys).buffer(0)
            greens.append((g, outer.intersection(BB)))
            if t.get('name') and outer.area > 6000: named_parks.append((t['name'], outer))
print('greens', len(greens))

# ---------- 건물 ----------
DEF_H = {'apartments':42, 'commercial':20, 'school':15, 'house':7, 'residential':12, 'retail':8, 'public':14, 'kindergarten':7, 'train_station':12, 'industrial':10, 'roof':5, 'church':14, 'hospital':30, 'university':20, 'office':30}
rnd = random.Random(7)
def bheight(t, area):
    try:
        if 'height' in t: return max(3, float(t['height'].replace('m', '').strip()))
    except ValueError: pass
    try:
        if 'building:levels' in t: return max(3, float(t['building:levels']) * 3.1)
    except ValueError: pass
    b = t.get('building', 'yes')
    if b in DEF_H: return DEF_H[b] * (0.85 + rnd.random() * 0.3)
    return (22 if area > 1500 else 13 if area > 400 else 8) * (0.8 + rnd.random() * 0.4)
buildings = []
def add_bld(poly, t):
    if poly.is_empty or poly.area < 12 or not BB.contains(poly.centroid): return
    poly = poly.simplify(0.6)
    if poly.geom_type == 'MultiPolygon': poly = max(poly.geoms, key=lambda g: g.area)
    buildings.append((poly, bheight(t, poly.area), t.get('building', 'yes')))
for w, (nd, t) in ways.items():
    if 'building' in t and nd[0] == nd[-1] and len(nd) > 3: add_bld(Polygon(wline(w)).buffer(0), t)
for rid, (m, t) in rels.items():
    if 'building' in t:
        polys = list(polygonize(unary_union([l for l in rel_lines(rid) if len(l.coords) > 1])))
        if polys: add_bld(unary_union(polys).buffer(0), t)
print('buildings', len(buildings))

# ---------- 길·철도 ----------
CLS = {'trunk':('x',22), 'trunk_link':('x',8), 'motorway':('x',24), 'motorway_link':('x',8), 'primary':('p',18), 'primary_link':('p',8), 'secondary':('s',14), 'secondary_link':('s',7),
       'tertiary':('t',11), 'tertiary_link':('t',6), 'residential':('r',7), 'unclassified':('r',7), 'living_street':('r',6), 'service':('v',4.5), 'pedestrian':('w',6),
       'footway':('f',2.5), 'path':('f',2.2), 'steps':('f',2), 'track':('f',3), 'cycleway':('c',3.5), 'corridor':('i',3), 'platform':('f',3)}
def layer(t):
    try: return int(float(t.get('layer', '0')))
    except ValueError: return 0
roads = []
for w, (nd, t) in ways.items():
    h = t.get('highway')
    if h not in CLS or len(nd) < 2: continue
    c, wd = CLS[h]
    br = t.get('bridge') in ('yes', 'viaduct', 'boardwalk')
    tu = t.get('tunnel') in ('yes', 'building_passage', 'passage') or t.get('indoor') == 'yes' or t.get('covered') == 'yes' or layer(t) < 0
    roads.append(dict(w=w, c=c, wd=wd, br=br, tu=tu, ly=layer(t), name=t.get('name', ''), pts=wline(w)))
RAILCOL = [('2호선','#33A23D'), ('5호선','#996CAC'), ('경의','#77C4A3'), ('중앙','#77C4A3'), ('분당','#F5A200'), ('수인','#F5A200'), ('3호선','#EF7C1C')]
rail_route_col = {}
for rid, (m, t) in rels.items():
    if t.get('type') == 'route' and t.get('route') in ('subway', 'train', 'light_rail'):
        col = t.get('colour') or next((c for k, c in RAILCOL if k in t.get('name', '')), None)
        if col:
            for typ, ref, role in m:
                if typ == 'way': rail_route_col.setdefault(ref, col)
rails = []
for w, (nd, t) in ways.items():
    if t.get('railway') in ('rail', 'subway', 'light_rail') and len(nd) > 1:
        col = rail_route_col.get(w) or next((c for k, c in RAILCOL if k in t.get('name', '')), '#8A9097')
        tu = t.get('tunnel') in ('yes',) or layer(t) < 0
        br = t.get('bridge') in ('yes', 'viaduct')
        rails.append(dict(w=w, col=col, tu=tu, br=br, ly=layer(t), pts=wline(w), name=t.get('name', '')))
print('roads', len(roads), 'rails', len(rails), collections.Counter(r['col'] for r in rails))

# ---------- 언덕 (응봉산) ----------
PEAK = ll2xy(37.5476323, 127.0298604); HILL_R, HILL_H = 250, 70
def hillH(x, y):
    d = math.hypot(x - PEAK[0], y - PEAK[1]); return HILL_H * math.cos(math.pi * d / (2 * HILL_R)) ** 2 if d < HILL_R else 0

# ---------- 길 찾기 그래프 ----------
WALK = {'footway':1.0, 'path':1.0, 'pedestrian':1.0, 'cycleway':0.95, 'track':1.0, 'steps':1.7, 'corridor':1.05, 'living_street':1.05, 'residential':1.1,
        'service':1.15, 'unclassified':1.1, 'tertiary':1.2, 'tertiary_link':1.2, 'secondary':1.35, 'secondary_link':1.35, 'primary':1.45, 'primary_link':1.45}
green_union = unary_union([g for k, g in greens if k in ('park', 'forest', 'grass')]).buffer(15)
river_side = water.buffer(140)
G = collections.defaultdict(list); E = {}
bridge_polys = []
for w, (nd, t) in ways.items():
    if t.get('bridge') in ('yes', 'viaduct') and (t.get('highway') in CLS or t.get('railway')) and len(nd) > 1:
        wd = CLS.get(t.get('highway'), ('', 10))[1] if t.get('highway') else 9
        if wd >= 6: bridge_polys.append((LineString(wline(w)).buffer(wd / 2 + 1.5, cap_style=2), layer(t), t.get('name') or t.get('highway') or t.get('railway')))
btree = STRtree([b[0] for b in bridge_polys])
for w, (nd, t) in ways.items():
    h = t.get('highway')
    if h not in WALK or t.get('foot') == 'no' or t.get('access') in ('private', 'no'): continue
    isbr = t.get('bridge') in ('yes', 'viaduct', 'boardwalk'); ly = layer(t)
    tun = t.get('tunnel') in ('yes', 'building_passage', 'passage') or t.get('indoor') == 'yes' or t.get('covered') == 'yes'
    for a, b in zip(nd, nd[1:]):
        if a not in nodes or b not in nodes: continue
        pa, pb = nxy(a), nxy(b); L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if L == 0: continue
        mid = Point((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        f = WALK[h]
        if green_union.contains(mid) or river_side.contains(mid): f *= 0.82
        cov = tun; covname = t.get('name', '') if tun else ''
        if not cov and not isbr:
            for i in btree.query(mid):
                bp, bl, bn = bridge_polys[i]
                if bp.contains(mid): cov = True; covname = bn; break
        G[a].append((b, L * f)); G[b].append((a, L * f))
        E[(a, b)] = E[(b, a)] = dict(L=L, br=isbr, ly=ly, cov=cov, covname=covname, way=w, name=t.get('name', ''))
# 가장 큰 연결 덩어리만 길 찾기에 쓴다 (따로 떨어진 짧은 길로 붙지 않게)
_seen = set(); _best = set()
for _s in G:
    if _s in _seen: continue
    _c = set(); _st = [_s]
    while _st:
        _u = _st.pop()
        if _u in _c: continue
        _c.add(_u); _st += [v for v, _ in G[_u]]
    _seen |= _c
    if len(_c) > len(_best): _best = _c
node_list = [n for n in G if n in _best]; node_pts = [nxy(n) for n in node_list]
ntree = STRtree([Point(p) for p in node_pts])
def snap(la, lo):
    p = Point(ll2xy(la, lo)); i = ntree.nearest(p); return node_list[i]
def dijkstra(s, goal):
    dist = {s: 0}; prev = {}; pq = [(0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == goal: break
        if d > dist[u]: continue
        for v, c in G[u]:
            nd_ = d + c
            if nd_ < dist.get(v, 1e18): dist[v] = nd_; prev[v] = u; heapq.heappush(pq, (nd_, v))
    path = [goal]
    while path[-1] != s: path.append(prev[path[-1]])
    return path[::-1]
def route(wps):
    ids = [snap(*w) for w in wps]; full = [ids[0]]
    for a, b in zip(ids, ids[1:]): full += dijkstra(a, b)[1:]
    return full
def pts_of(path):
    out = []
    for i, n in enumerate(path):
        x, y = nxy(n)
        e = E.get((path[i - 1], n)) if i else E.get((n, path[1])) if len(path) > 1 else None
        h = hillH(x, y)
        flag = 0
        if e and e['br']: flag = 1
        if e and e['cov']: flag = 2
        out.append([round(x, 1), round(y, 1), flag])
    return out
def plen(path): return sum(E[(a, b)]['L'] for a, b in zip(path, path[1:]))

ST = dict(haengdang=(37.55701, 127.02881), eungbong=(37.55198, 127.03527), hanyang=(37.55573, 127.04366), ttukseom=(37.54720, 127.04717),
          wangsimni=(37.56017, 127.03620), seoulforest=(37.54373, 127.04519), seongsu=(37.54460, 127.05590))
OUTD = dict(points={})
import json as _j
EXTRA = _j.loads(open(sys.argv[3]).read()) if len(sys.argv) > 3 else {}
def find_way_mid(name_sub, key='name'):
    best = None
    for w, (nd, t) in ways.items():
        if name_sub in t.get(key, '') and len(nd) > 1:
            if best is None or len(nd) > len(ways[best][0]): best = w
    nd = ways[best][0]; n = nd[len(nd) // 2]; la, lo, _ = nodes[n]; return (la, lo)
def ll_of_xy(x, y): return (LAT0 - y / KY, LON0 + x / KX)
OUTD['debug'] = {}
yongbi = (37.5453, 127.0310)   # 용비교 가운데 (중랑천 위)
salgoji = (37.55336, 127.04633)
lake = [w for w, (nd, t) in ways.items() if t.get('name') == '서울숲호수'][0]
lp = Polygon(wline(lake)); minx, miny, maxx, maxy = lp.bounds
lake_ring = [ll_of_xy(minx - 40, (miny + maxy) / 2), ll_of_xy((minx + maxx) / 2, maxy + 40), ll_of_xy(maxx + 40, (miny + maxy) / 2), ll_of_xy((minx + maxx) / 2, miny - 40)]
jw = find_way_mid('중랑천서자전거길')
# 한강 북쪽 자전거길에서 동쪽 끝 근처
hb = max((n for w, (nd, t) in ways.items() if '한강북자전거길' in t.get('name', '') for n in nd if n in nodes and nodes[n][1] < 127.0545), key=lambda n: nodes[n][1])
hb_ll = nodes[hb][:2]
hb_w = min((n for w, (nd, t) in ways.items() if '한강북자전거길' in t.get('name', '') for n in nd if n in nodes and nodes[n][1] > 127.0345), key=lambda n: nodes[n][1])
hbw_ll = nodes[hb_w][:2]
COURSES = {
  'A': [ST['haengdang'], ST['eungbong'], jw, salgoji, ST['hanyang'], ST['haengdang']],
  'B': [ST['haengdang'], yongbi, *lake_ring, lake_ring[0], yongbi, ST['haengdang']],
  'C': [ST['haengdang'], ST['eungbong'], yongbi, hbw_ll, hb_ll, ST['ttukseom'], salgoji, ST['hanyang'], ST['haengdang']],
}
courses = {}
for k, wps in COURSES.items():
    p = route(wps); courses[k] = dict(pts=pts_of(p), len=round(plen(p) / 1000, 2))
    print('course', k, courses[k]['len'], 'km', len(p), 'nodes')
POI = dict(A=[(ST['eungbong'], '응봉역 앞'), (jw, '중랑천 산책로'), (salgoji, '살곶이다리'), (ST['hanyang'], '한양대역'), (ST['haengdang'], '행당역 도착')],
           B=[(yongbi, '용비교 건너기'), (lake_ring[1], '서울숲 호수'), (yongbi, '용비교 다시 건너기'), (ST['haengdang'], '행당역 도착')],
           C=[(yongbi, '용비교 건너기'), (hbw_ll, '한강 북쪽 자전거길'), (hb_ll, '성수동 쪽으로 꺾기'), (ST['ttukseom'], '뚝섬역'), (salgoji, '살곶이다리'), (ST['haengdang'], '행당역 도착')])

# ---------- 비를 피하는 구간 찾기 ----------
cov_edges = {(a, b) for (a, b), e in E.items() if e['cov'] and a < b}
adj = collections.defaultdict(set)
for a, b in cov_edges: adj[a].add(b); adj[b].add(a)
seen = set(); comps = []
for s in adj:
    if s in seen: continue
    st = [s]; comp = set()
    while st:
        u = st.pop()
        if u in comp: continue
        comp.add(u); st += list(adj[u])
    seen |= comp
    def far(src):
        d = {src: 0}; pr = {}; q = [src]
        while q:
            u = q.pop(0)
            for v in adj[u]:
                if v not in d: d[v] = d[u] + E[(u, v)]['L']; pr[v] = u; q.append(v)
        t = max(d, key=d.get); return t, d[t], pr
    a, _, _ = far(s); b, L, pr = far(a)
    path = [b]
    while path[-1] != a: path.append(pr[path[-1]])
    names = collections.Counter(E[(u, v)]['covname'] for u, v in zip(path, path[1:]) if E[(u, v)]['covname'])
    comps.append(dict(path=path[::-1], L=L, name=names.most_common(1)[0][0] if names else ''))
hd = snap(*ST['haengdang'])
cands = []
for c in comps:
    if c['L'] < 120: continue
    ap = dijkstra(hd, c['path'][0]); apL = plen(ap)
    if apL > 3200: continue
    cands.append((c, ap, apL))
cands.sort(key=lambda z: -(z[0]['L'] * 2 - z[2] * .15))
for c, ap, apL in cands[:12]:
    x, y = nxy(c['path'][0]); print('cov', round(c['L']), 'm', c['name'], 'approach', round(apL), 'at', round(x), round(y))
rain = []
PREF = ['고산자로', '내부순환로', '2호선']
picked = [next(z for z in cands if z[0]['name'] == nm) for nm in PREF if any(z[0]['name'] == nm for z in cands)]
for z in cands:
    if len(picked) >= 3: break
    if z not in picked: picked.append(z)
for c, ap, apL in picked:
    mids = [Point(nxy(n)) for n in c['path'][::max(1, len(c['path']) // 8)]]
    riverside = sum(water.distance(m) < 130 for m in mids) > len(mids) / 2
    rain.append(dict(name=c['name'], L=round(c['L']), main=pts_of(c['path']), approach=pts_of(ap), apLen=round(apL), river=riverside))
    print('rain pick', c['name'], round(c['L']), 'riverside', riverside)

# ---------- 나무 ----------
obst = unary_union([b[0] for b in buildings] + [LineString(r['pts']).buffer(r['wd'] / 2 + (5 if r['c'] in ('f', 'c', 'w') else 2)) for r in roads if r['c'] not in ('i',) and not r['tu']]).buffer(0)  # 산책로 옆은 넓게 비워 둔다
otree_geom = obst
trees = []
rr = random.Random(3)
for k, g in greens:
    if g.is_empty: continue
    dens = {'forest': 1 / 140, 'park': 1 / 320, 'grass': 1 / 1200, 'pitch': 0}[k]
    n = int(g.area * dens)
    if n == 0: continue
    minx, miny, maxx, maxy = g.bounds; tries = 0; got = 0
    while got < n and tries < n * 6:
        tries += 1
        p = Point(minx + rr.random() * (maxx - minx), miny + rr.random() * (maxy - miny))
        if g.contains(p) and not water.contains(p) and not otree_geom.contains(p): trees.append((round(p.x), round(p.y))); got += 1
for n, (la, lo, t) in nodes.items():
    if t.get('natural') == 'tree':
        x, y = ll2xy(la, lo)
        if BB.contains(Point(x, y)): trees.append((round(x), round(y)))
print('trees', len(trees))

# ---------- 라벨 ----------
labels = []
for n, (la, lo, t) in nodes.items():
    if t.get('place') in ('quarter', 'neighbourhood', 'suburb'):
        x, y = ll2xy(la, lo)
        if BB.contains(Point(x, y)): labels.append(dict(t=t['name'], x=round(x), y=round(y), k='place'))
seen_names = set()
for nm, p in sorted(named_parks, key=lambda z: -z[1].area):
    if nm in seen_names or not BB.contains(p.representative_point()): continue
    seen_names.add(nm); c = p.representative_point()
    labels.append(dict(t=nm, x=round(c.x), y=round(c.y), k='park', big=p.area > 80000))
labels.append(dict(t='응봉산', x=round(PEAK[0]), y=round(PEAK[1]), k='peak', big=True))
for nm, (x, y) in [('한강', ll2xy(37.5365, 127.0300)), ('중랑천', ll2xy(37.5516, 127.0368)), ('서울숲 호수', lp.centroid.coords[0])]:
    labels.append(dict(t=nm, x=round(x), y=round(y), k='water', big=nm != '서울숲 호수'))
stations = [dict(t=nm, x=round(ll2xy(*ll)[0]), y=round(ll2xy(*ll)[1])) for nm, ll in
            [('행당역', ST['haengdang']), ('응봉역', ST['eungbong']), ('한양대역', ST['hanyang']), ('뚝섬역', ST['ttukseom']), ('왕십리역', ST['wangsimni']), ('서울숲역', ST['seoulforest']), ('성수역', ST['seongsu'])]]
# 이름 있는 큰길: 이름별로 가장 긴 선 하나
named_roads = {}
for r in roads:
    if r['name'] and r['c'] in ('x', 'p', 's', 't') and not r['tu']:
        L = LineString(r['pts']).length
        if L > named_roads.get(r['name'], (0,))[0]: named_roads[r['name']] = (L, r['w'])

# ---------- 내보내기 (정수 m, 차분 부호화) ----------
def enc(pts):
    out = []; px = py = 0
    for x, y in pts:
        ix, iy = int(round(x)), int(round(y)); out += [ix - px, iy - py]; px, py = ix, iy
    return out
def polys_of(g):
    if g.is_empty: return []
    gs = g.geoms if hasattr(g, 'geoms') else [g]
    out = []
    for p in gs:
        if p.geom_type != 'Polygon' or p.area < 20: continue
        p = p.simplify(0.8)
        out.append([enc(list(p.exterior.coords)[:-1])] + [enc(list(i.coords)[:-1]) for i in p.interiors])
    return out
def clipline(pts):
    g = LineString(pts).intersection(BB.buffer(40))
    if g.is_empty: return []
    gs = g.geoms if hasattr(g, 'geoms') else [g]
    return [list(l.simplify(0.5).coords) for l in gs if l.geom_type == 'LineString' and len(l.coords) > 1]
data = dict(
  origin=[LAT0, LON0, KX, KY], bounds=[-1040, -1100, 2570, 3320], hill=[round(PEAK[0]), round(PEAK[1]), HILL_R, HILL_H],
  water=polys_of(water), green={k: [pp for _, g in greens if _ == k for pp in polys_of(g)] for k in ('park', 'forest', 'grass', 'pitch')},
  buildings=[[enc(list(p.exterior.coords)[:-1]), round(h), {'apartments':1, 'commercial':2, 'school':3, 'house':4}.get(k, 0)] for p, h, k in buildings if p.geom_type == 'Polygon'],
  roads=[[r['c'], r['wd'], int(r['br']), int(r['tu']), r['ly'], [enc(l) for l in clipline(r['pts'])], r['name'] if r['name'] and named_roads.get(r['name'], (0, None))[1] == r['w'] else ''] for r in roads],
  rails=[[r['col'], int(r['br']), int(r['tu']), [enc(l) for l in clipline(r['pts'])]] for r in rails],
  trees=enc(trees), labels=labels, stations=stations,
  courses={k: dict(len=v['len'], pts=v['pts'], pois=[[round(ll2xy(*ll)[0]), round(ll2xy(*ll)[1]), t] for ll, t in POI[k]]) for k, v in courses.items()},
  rain=rain,
)
data['roads'] = [r for r in data['roads'] if r[5]]; data['rails'] = [r for r in data['rails'] if r[3]]
s = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
open(OUT, 'w').write('/* 런웨더 행당 지도 데이터. 지도 데이터 © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright). tools/build_map.py로 생성 */\nwindow.MAPDATA=' + s + ';\n')
print('wrote', OUT, len(s) // 1024, 'KB')

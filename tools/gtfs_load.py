import argparse, os, sqlite3, csv
TABLES=[
 ('agency',['agency_id','agency_name','agency_url','agency_timezone','agency_lang','agency_phone','agency_fare_url','agency_email']),
 ('stops',['stop_id','stop_code','stop_name','stop_desc','stop_lat','stop_lon','zone_id','stop_url','location_type','parent_station','stop_timezone','wheelchair_boarding']),
 ('routes',['route_id','agency_id','route_short_name','route_long_name','route_desc','route_type','route_url','route_color','route_text_color']),
 ('trips',['route_id','service_id','trip_id','trip_headsign','trip_short_name','direction_id','block_id','shape_id','wheelchair_accessible','bikes_allowed']),
 ('stop_times',['trip_id','arrival_time','departure_time','stop_id','stop_sequence','stop_headsign','pickup_type','drop_off_type','shape_dist_traveled','timepoint']),
 ('calendar',['service_id','monday','tuesday','wednesday','thursday','friday','saturday','sunday','start_date','end_date']),
 ('calendar_dates',['service_id','date','exception_type']),
 ('shapes',['shape_id','shape_pt_lat','shape_pt_lon','shape_pt_sequence','shape_dist_traveled']),
 ('feed_info',['feed_publisher_name','feed_publisher_url','feed_lang','feed_start_date','feed_end_date','feed_version'])]

def ensure_schema(conn):
 cur=conn.cursor()
 for name,cols in TABLES:
  cur.execute(f'DROP TABLE IF EXISTS {name}')
  cur.execute(f"CREATE TABLE {name} ({', '.join([c+' TEXT' for c in cols])})")
 cur.execute('CREATE INDEX IF NOT EXISTS idx_stops_id ON stops(stop_id)')
 cur.execute('CREATE INDEX IF NOT EXISTS idx_trips_id ON trips(trip_id)')
 cur.execute('CREATE INDEX IF NOT EXISTS idx_routes_id ON routes(route_id)')
 cur.execute('CREATE INDEX IF NOT EXISTS idx_stoptimes_trip ON stop_times(trip_id)')
 cur.execute('CREATE INDEX IF NOT EXISTS idx_stoptimes_stop ON stop_times(stop_id)')
 cur.execute('CREATE INDEX IF NOT EXISTS idx_stoptimes_seq ON stop_times(stop_sequence)')
 conn.commit()

def parse_time_to_seconds(s):
 if not s: return None
 parts=s.split(':')
 if len(parts)!=3: return None
 try: h,m,sec=map(int,parts)
 except: return None
 return h*3600+m*60+sec

def load_table(conn, gtfs_dir, name, cols):
 path=os.path.join(gtfs_dir, f'{name}.txt')
 if not os.path.exists(path): print('Aviso: no existe',path); return
 print('Cargando',name)
 with open(path, newline='', encoding='utf-8') as f:
  reader=csv.DictReader(f); rows=[]
  for row in reader:
   vals=[row.get(c,'') for c in cols]
   if name=='stop_times':
    at=parse_time_to_seconds(row.get('arrival_time','') or '')
    dt=parse_time_to_seconds(row.get('departure_time','') or '')
    if at is not None: vals[cols.index('arrival_time')]=at
    if dt is not None: vals[cols.index('departure_time')]=dt
    ss=row.get('stop_sequence',''); vals[cols.index('stop_sequence')]=''.join(ch for ch in ss if ch.isdigit()) or '0'
   rows.append(vals)
  qmarks=','.join(['?']*len(cols))
  conn.executemany(f"INSERT INTO {name}({','.join(cols)}) VALUES({qmarks})", rows)
  conn.commit()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--gtfs_dir', required=True); ap.add_argument('--sqlite', required=True); args=ap.parse_args()
 os.makedirs(os.path.dirname(args.sqlite), exist_ok=True)
 conn=sqlite3.connect(args.sqlite); ensure_schema(conn)
 for name,cols in TABLES: load_table(conn,args.gtfs_dir,name,cols)
 print('Carga GTFS completa en', args.sqlite)

if __name__=='__main__': main()

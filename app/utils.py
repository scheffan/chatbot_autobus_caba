import math
from datetime import datetime,timedelta

def haversine(lat1,lon1,lat2,lon2):
 R=6371000.0
 import math as m
 phi1,phi2=m.radians(lat1),m.radians(lat2)
 dphi=m.radians(lat2-lat1); dl=m.radians(lon2-lon1)
 a=m.sin(dphi/2)**2+m.cos(phi1)*m.cos(phi2)*m.sin(dl/2)**2
 return 2*R*m.atan2(m.sqrt(a),m.sqrt(1-a))

def sec_to_hm(s):
 m=round(s/60); return f"{m} min"

def now_local():
 return datetime.now()

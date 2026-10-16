"""Analyse sleep_glucose_server.py output (path hard-coded below; personal data stays out of git)."""
import json, numpy as np, pandas as pd
d=pd.DataFrame([json.loads(l) for l in open(r"C:/Users/hecol/AppData/Local/Temp/gt/sleep.jsonl") if l.startswith("{")])
d["start"]=pd.to_datetime(d.start,format="ISO8601"); d["end"]=pd.to_datetime(d.end,format="ISO8601")
d["sh"]=d.start.dt.hour; d["eh"]=d.end.dt.hour
print(d.groupby("origin").agg(n=("hours","size"),first=("start","min"),last=("start","max"),med_hours=("hours","median"),cgm=("cgm_coverage","median")))
print("\nstart hour histogram:",d.sh.value_counts().sort_index().to_dict())
print("end hour histogram:",d.eh.value_counts().sort_index().to_dict())
print("sessions with CGM coverage>=0.7 & >=3h:",((d.cgm_coverage>=0.7)&(d.hours>=3)).sum())

n=d[(d.cgm_coverage>=0.7)&(d.hours>=4)].copy()
print("\n=== main sleep with CGM:",len(n),"nights; with food logged during sleep (suspect dating):",int((n.meals_during>0).sum()))
n=n[n.meals_during==0].copy()
n["drift"]=n.bg_end-n.bg_start; n["drift_h"]=n.drift/n.hours
print(f"nights analysed: {len(n)} ({n.start.min():%Y-%m-%d} … {n.start.max():%Y-%m-%d}); median sleep {n.hours.median():.1f} h, starts {n.start.dt.hour.median():.0f}:00")
print(f"glucose asleep: mean {n.bg_mean.median():.1f}; start {n.bg_start.median():.1f} -> end {n.bg_end.median():.1f} (median change {n.drift.median():+.1f}, IQR {n.drift.quantile(.25):+.1f}…{n.drift.quantile(.75):+.1f})")
print(f"nights with any reading <3.9: {(n.min_below_3_9>0).mean():.0%}  (median minutes when it happens {n.loc[n.min_below_3_9>0,'min_below_3_9'].median():.0f}); nights with >1 h above 10: {(n.min_above_10>60).mean():.0%}")
print(f"compression-flagged points on {(n.compression_points>0).mean():.0%} of nights; jump-flagged on {(n.jump_points>0).mean():.0%}")
n["state"]=np.where((n.carbs_4h_before<5)&(n.bolus_4h_before<0.3)&(n.iob_at_start<0.5)&(n.doses_during==0),"clean",
          np.where(n.carbs_4h_before>=5,"food <4 h before","insulin on board/dose during"))
print("\nby pre-sleep state:")
for k,g in n.groupby("state"):
    print(f"  {k:28s} n={len(g):2d} start {g.bg_start.median():4.1f} end {g.bg_end.median():4.1f} change {g.drift.median():+.1f} ({g.drift_h.median():+.2f}/h)  low nights {(g.min_below_3_9>0).mean():.0%}  >10 for 1h+ {(g.min_above_10>60).mean():.0%}  carbs4h {g.carbs_4h_before.median():.0f} g  IOB {g.iob_at_start.median():.1f}")
# profile by hours from sleep start, clean nights only, relative to start
def prof(g):
    rows=[]
    for _,r in g.iterrows():
        p={int(k):v for k,v in r.profile_30min.items()}; base=p.get(0) or p.get(1)
        if base is None: continue
        rows.append({k/2:v-base for k,v in p.items()})
    return pd.DataFrame(rows)
for k in ["clean","food <4 h before","insulin on board/dose during"]:
    P=prof(n[n.state==k])
    if len(P)==0: continue
    med=P.median(); cnt=P.count()
    print(f"\n  {k}: change from sleep start, median by hour asleep:")
    print("   "+"  ".join(f"{h:.0f}h {med[h]:+.1f}(n{cnt[h]})" for h in sorted(med.index) if h%1==0 and h<=10 and cnt[h]>=4))
# dawn: last 2 h before waking vs 2 h before that, clean or not
def dawn(r):
    p={int(k):v for k,v in r.profile_30min.items()}
    if not p: return np.nan
    last=max(p); 
    if last<8: return np.nan
    return p[last]-p.get(last-4,np.nan)
n["last2h"]=n.apply(dawn,axis=1)
print(f"\nlast 2 h before waking: median change {n.last2h.median():+.2f} (rising on {(n.last2h>0.5).mean():.0%} of nights, n={n.last2h.notna().sum()}); clean nights only {n.loc[n.state=='clean','last2h'].median():+.2f}")
from scipy.stats import spearmanr
for f in ["carbs_4h_before","iob_at_start","bolus_4h_before","last_meal_fat","bg_start","hours"]:
    x=n[[f,"drift"]].dropna(); r,p=spearmanr(x[f],x.drift); print(f"  overnight change vs {f:16s} rho {r:+.2f} p={p:.3f} n={len(x)}")
x=n[["iob_at_start","bg_min"]].dropna(); r,p=spearmanr(x.iob_at_start,x.bg_min); print(f"  lowest asleep vs IOB at sleep  rho {r:+.2f} p={p:.3f}")

print("\n=== lows: when (clock) and how")
rows=[]
for _,r in n.iterrows():
    p={int(k):v for k,v in r.profile_30min.items()}
    if not p: continue
    kmin=min(p,key=p.get)
    rows.append({"clock":(r.start+pd.Timedelta(minutes=30*kmin)).hour,"low":r.min_below_3_9>0,"state":r.state,"bg_min":r.bg_min,"compr":r.compression_points>0,"bg_start":r.bg_start})
L=pd.DataFrame(rows)
print("clock hour of each night's lowest 30-min bin (low nights):",L[L.low].clock.value_counts().sort_index().to_dict())
print("clock hour of lowest bin (all nights):",L.clock.value_counts().sort_index().to_dict())
print("low nights with dashboard compression flags:",int((L.low&L.compr).sum()),"of",int(L.low.sum()))
print("low nights by start level:",L.groupby(pd.cut(L.bg_start,[0,6,8,30])).low.mean().round(2).to_dict())
# clean nights by clock hour (absolute)
def clock_prof(g):
    out={}
    for _,r in g.iterrows():
        p={int(k):v for k,v in r.profile_30min.items()}
        for k,v in p.items():
            h=(r.start+pd.Timedelta(minutes=30*k)).hour
            out.setdefault(h,[]).append(v)
    return {h:(round(np.median(v),1),len(v)) for h,v in sorted(out.items())}
print("\nclean nights, median glucose by clock hour (value, half-hour bins):",clock_prof(n[n.state=="clean"]))
print("all nights, median glucose by clock hour:",clock_prof(n))

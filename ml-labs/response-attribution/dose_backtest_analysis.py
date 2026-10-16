"""Analyse dose_backtest_server.py output: python dose_backtest_analysis.py backtest.jsonl"""
import sys
import json, numpy as np, pandas as pd
rows=[json.loads(l) for l in open(sys.argv[1])]
d=pd.DataFrame(rows); d["t"]=pd.to_datetime(d.t,format="ISO8601")
print(d[d.t.dt.strftime("%Y-%m-%d %H")=="2026-10-01 09"][["t","carbs","prod","prod_hist","prod_n","prod_w","icr_dose","regime","regime_hist","regime_n","given"]].to_string())
c=d[(~d.more_food)&(~d.prior_food)&(d.given_late==0)&(d.prior_units<=0.5)&(d.given>0)&d.bg0.notna()&d.bg3h.notna()&d.bg4h.notna()].copy()
print("\nclean labelled episodes:",len(c),"novorapid",int(c.novorapid.sum()))
c["Δ3"]=c.bg3h-c.bg0; c["Δ4"]=c.bg4h-c.bg0
print("median BG change 0→3h %.2f, 0→4h %.2f"%(c["Δ3"].median(),c["Δ4"].median()))
def evaluate(c,isf,horizon):
    ideal=c.given+c[horizon]/isf
    out={}
    for v in ["prod","regime","icr_dose","prod_hist","given"]:
        x=(c[v]-ideal).dropna(); out[v]=f"bias {x.median():+.2f} MAE {x.abs().mean():.2f} n={len(x)}"
    return out
for isf in (1.5,2.6,3.5):
    for h in ("Δ3","Δ4"):
        for scope,sub in [("novorapid",c.novorapid),("fiasp",~c.novorapid)]:
            r=evaluate(c[sub],isf,h); print(f"ISF {isf} {h} {scope:4s}:", " | ".join(f"{k}: {v}" for k,v in r.items()))

print("\n--- all NovoRapid-period sittings with a bolus")
p=d[d.novorapid&(d.given>0)&d["prod"].notna()].copy()
p["tot"]=p.given+p.given_late
print("n",len(p),"| median prod − given %+.2f | prod − (given+late) %+.2f | share prod>given %.0f%%"%((p["prod"]-p.given).median(),(p["prod"]-p.tot).median(),100*(p["prod"]>p.given).mean()))
q=p[~p.more_food & p.bg4h.notna() & p.bg0.notna()]
print("without more food n",len(q),"Δ4h median %+.2f, late insulin share %.0f%%"%((q.bg4h-q.bg0).median(),100*(q.given_late>0).mean()))
# implied ICR on clean NovoRapid episodes
cp=c[c.novorapid].copy()
for isf in (1.5,2.6,3.5):
    ideal=cp.given+cp["Δ4"]/isf; icr=(cp.carbs/ideal).where(ideal>0.5)
    print(f"ISF {isf}: implied NovoRapid ICR median {icr.median():.1f} g/U (IQR {icr.quantile(.25):.1f}-{icr.quantile(.75):.1f}) n={icr.notna().sum()}")
print("configured ICR median over these:",cp.icr_cfg.median(), " carbs/given median:",(cp.carbs/cp.given).median().round(1))
pall=p[p.carbs>=20]; print("all NovoRapid sittings carbs/given median %.1f (n=%d)"%((pall.carbs/pall.tot).median(),len(pall)))

print("\n--- label = given + late + Δ4/ISF, NovoRapid sittings without more food")
q=q.copy(); q["Δ4"]=q.bg4h-q.bg0
rng=np.random.default_rng(0)
for isf in (1.5,2.6,3.5):
    ideal=q.given+q.given_late+q["Δ4"]/isf
    res={}
    for v in ["prod","regime","icr_dose","given"]:
        e=(q[v]-ideal).to_numpy()
        res[v]=(np.median(e),np.abs(e).mean())
    # paired bootstrap prod vs regime
    a=np.abs(q["prod"]-ideal).to_numpy(); b=np.abs(q["regime"]-ideal).to_numpy()
    bs=[np.mean(rng.choice(a-b,len(a))) for _ in range(2000)]
    print(f"ISF {isf}: "+" | ".join(f"{k}: bias {m:+.2f} MAE {s:.2f}" for k,(m,s) in res.items())+f" | MAE(prod)-MAE(regime) {np.mean(a-b):+.2f} CI90 {np.percentile(bs,[5,95]).round(2)}")
print("how often regime differs from prod by ≥0.5 U:", f"{(abs(q['regime']-q['prod'])>=0.5).mean():.0%}", "median regime−prod %+.2f"%(q['regime']-q['prod']).median())
pp=d[d.novorapid & d["prod"].notna()]; print("all NovoRapid sittings: regime−prod median %+.2f, |diff|≥0.5 in %.0f%%"%((pp.regime-pp["prod"]).median(),100*(abs(pp.regime-pp["prod"])>=0.5).mean()))

print("\n--- what explains the miss (ideal − prod), ISF 2.6, NovoRapid, no more food")
from scipy.stats import spearmanr
q["miss"]=q.given+q.given_late+q["Δ4"]/2.6-q["prod"]
q["trend"]=q.bg0-q.bg_m30; q["fat_ratio"]=q.fat/q.carbs; q["hour"]=q.t.dt.hour+q.t.dt.minute/60
q["kcal_per_g"]=q.kcal/q.carbs
feats=["carbs","fat_ratio","kcal_per_g","protein","hour","bg0","trend","prod_n","prod_w"]
for f in feats:
    x=q[[f,"miss"]].dropna(); r,p=spearmanr(x[f],x["miss"])
    bs=[]; arr=x.to_numpy()
    for _ in range(1000):
        s=arr[rng.integers(0,len(arr),len(arr))]; bs.append(spearmanr(s[:,0],s[:,1])[0])
    print(f"  {f:11s} rho {r:+.2f} CI90 {np.percentile(bs,[5,95]).round(2)} n={len(x)}")
q["miss_per_g"]=q.miss/q.carbs
print("  by carbs size: ",q.groupby(pd.cut(q.carbs,[0,30,50,80,300])).miss.median().round(2).to_dict())
print("  by after_sleep:",q.groupby("after_sleep").miss.median().round(2).to_dict(), q.after_sleep.value_counts().to_dict())
print("  by start trend:",q.groupby(pd.cut(q.trend,[-9,-0.5,0.5,9])).miss.median().round(2).to_dict())

print("\n--- prequential (time-ordered) residual model on top of prod")
def prequential(q, feats, isf, min_train=25, ridge=2.0):
    q=q.sort_values("t").copy()
    q["ideal"]=q.given+q.given_late+q["Δ4"]/isf
    X=np.column_stack([np.ones(len(q))]+[q[f].to_numpy() for f in feats]); y=(q.ideal-q["prod"]).to_numpy()
    preds=np.full(len(q),np.nan)
    for i in range(min_train,len(q)):
        Xt,yt=X[:i],y[:i]; mu=Xt[:,1:].mean(0); sd=Xt[:,1:].std(0)+1e-9
        Z=np.column_stack([np.ones(i),(Xt[:,1:]-mu)/sd]); P=np.eye(Z.shape[1])*ridge; P[0,0]=0
        b=np.linalg.solve(Z.T@Z+P,Z.T@yt); z=np.r_[1,(X[i,1:]-mu)/sd]; preds[i]=z@b
    m=~np.isnan(preds); base=np.abs(y[m]).mean(); new=np.abs(y[m]-preds[m]).mean()
    d_=np.abs(y[m])-np.abs(y[m]-preds[m]); bs=[np.mean(rng.choice(d_,len(d_))) for _ in range(2000)]
    return base,new,np.percentile(bs,[5,95]),m.sum()
q["log_carbs"]=np.log(q.carbs); q["sleep"]=q.after_sleep.astype(float); q["trend"]=q.trend.fillna(0)
sets={"trend":["trend"],"size":["log_carbs"],"fat":["fat_ratio"],"sleep":["sleep"],"trend+size+fat+sleep":["trend","log_carbs","fat_ratio","sleep"],"all+hour":["trend","log_carbs","fat_ratio","sleep","hour"]}
for isf in (1.5,2.6,3.5):
    for name,f in sets.items():
        base,new,ci,n=prequential(q,f,isf)
        print(f"ISF {isf} {name:22s} MAE prod {base:.2f} -> {new:.2f}  gain CI90 {ci.round(2)} (n={n})")

print("\n--- pooled across regimes (regime as a feature)")
a=d[(d.given>0)&d["prod"].notna()&(~d.more_food)&d.bg4h.notna()&d.bg0.notna()].copy()
a["Δ4"]=a.bg4h-a.bg0; a["trend"]=(a.bg0-a.bg_m30).fillna(0); a["log_carbs"]=np.log(a.carbs); a["fat_ratio"]=a.fat/a.carbs
a["sleep"]=a.after_sleep.astype(float); a["novorapidf"]=a.novorapid.astype(float); a["hour"]=a.t.dt.hour+a.t.dt.minute/60
print("n",len(a),"novorapid",int(a.novorapid.sum()))
for isf in (1.5,2.6,3.5):
    for name,f in {"fat":["fat_ratio","novorapidf"],"size":["log_carbs","novorapidf"],"trend":["trend","novorapidf"],"sleep":["sleep","novorapidf"],"4 features":["trend","log_carbs","fat_ratio","sleep","novorapidf"]}.items():
        base,new,ci,n=prequential(a,f,isf,min_train=40)
        print(f"ISF {isf} {name:11s} MAE {base:.2f} -> {new:.2f} gain CI90 {ci.round(2)} n={n}")

print("\n--- miss by how the carbs were estimated (ISF 2.6, all regimes, no more food)")
a["ideal"]=a.given+a.given_late+a["Δ4"]/2.6; a["err"]=a["prod"]-a.ideal; a["uerr"]=a.given+a.given_late-a.ideal
print(a.groupby("source").agg(n=("err","size"),calc_MAE=("err",lambda x:x.abs().mean()),calc_bias=("err","median"),you_MAE=("uerr",lambda x:x.abs().mean())).round(2).to_string())


print()
print("--- PROSPECTIVE: frozen shadow (dose_shadow.py) vs production, sittings after the freeze")
if "shadow" in d.columns:
    f=d[(d.t>=pd.Timestamp("2026-10-02"))&(d.given>0)&d["prod"].notna()&d["shadow"].notna()&(~d.more_food)&d.bg4h.notna()&d.bg0.notna()].copy()
    print("n",len(f),"(decide only with n >= 40)")
    if len(f)>=5:
        for isf in (1.5,2.6,3.5):
            ideal=f.given+f.given_late+(f.bg4h-f.bg0)/isf
            ep=np.abs(f["prod"]-ideal).to_numpy(); es=np.abs(f["shadow"]-ideal).to_numpy()
            bs=[np.mean(rng.choice(ep-es,len(ep))) for _ in range(2000)]
            print(f"ISF {isf}: MAE production {ep.mean():.2f} | shadow {es.mean():.2f} | gain CI90 {np.percentile(bs,[5,95]).round(2)}")
else:
    print("no shadow column: the server is running a deployment without dose_shadow.py")

"""Render the finite-grid spectral envelope and band-local SGWB sensitivities."""
import json
import numpy as np
from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib.colors import HexColor
from study import ROOT, YEAR, H_LVK, lisa, lvk, pta, spectrum


def draw():
    points = np.genfromtxt(ROOT/"results/points.csv", delimiter=",", names=True)
    bench = json.loads((ROOT/"data/benchmark.json").read_text())
    f = np.geomspace(1e-9, 2000, 540)
    models = np.array([spectrum(f,p["N"],3,*[p[k] for k in ("Tn","Alpha","Beta","vwLTE","kappaLTE")])
                       for p in points])
    benchmark = spectrum(f,3,6,*[bench[k] for k in ("Tp","alpha","betaH","vw","kappa")])
    d = Drawing(800, 345)
    fg, subtle, grid = map(HexColor, ["#252722","#56594f","#d5d6cf"])
    d.add(Rect(0,0,800,345,fillColor=HexColor("#faf9f4"),strokeWidth=0,strokeColor=None))
    x0,x1,y0,y1=77,775,47,300
    def xy(hz, amplitude):
        return (x0+(np.log10(hz)+9)/(np.log10(2000)+9)*(x1-x0),
                y0+(np.log10(amplitude)+50)/48*(y1-y0))
    def label(x,y,s,size=12,color=fg,align="start"):
        d.add(String(x,y,s,fontName="Helvetica",fontSize=size,fillColor=color,textAnchor=align))
    def line(hz, amp, color, width):
        coords = np.column_stack(xy(hz,amp)).ravel().tolist()
        d.add(PolyLine(coords,strokeColor=HexColor(color),strokeWidth=width,fillColor=None))
    for exp in range(-50,0,10):
        y = xy(1,10.**exp)[1]
        d.add(Line(x0,y,x1,y,strokeColor=grid,strokeWidth=.6))
        label(x0-10,y-3,"1e"+str(exp),10,subtle,"end")
    for exp in (-9,-7,-5,-3,-1,1,3):
        x=xy(10.**exp,1)[0]
        d.add(Line(x,y0,x,y0-4,strokeColor=subtle,strokeWidth=.8))
        label(x,y0-17,"1e"+str(exp),10,subtle,"middle")
    band_x=np.r_[f,f[::-1]]
    band_y=np.r_[models.min(axis=0),models.max(axis=0)[::-1]]
    d.add(Polygon(np.column_stack(xy(band_x,np.maximum(band_y,1e-50))).ravel().tolist(),
                  fillColor=HexColor("#c6d9d2"),strokeColor=None))
    line(f,benchmark,"#205e50",2.0)
    fp,no=pta()
    fl=np.geomspace(1e-4,.1,220)
    line(fp,no/np.sqrt(2*15*YEAR*fp),"#873b29",2)
    line(fl,lisa(fl)/np.sqrt(4*YEAR*fl),"#873b29",2)
    fd,_,sigma,_=lvk()
    edges=np.geomspace(20,fd.max()+1/32,100)
    information=np.histogram(fd,bins=edges,weights=1/sigma**2)[0]
    valid=information>0
    centers=np.sqrt(edges[:-1]*edges[1:])[valid]
    noise=H_LVK**2*np.sqrt(np.diff(np.log(edges))[valid]/information[valid])
    line(centers,noise,"#873b29",1.6)
    label(x0,322,"Present-day energy density, h² Omega",15)
    label((x0+x1)/2,7,"Observed frequency (Hz)",12,fg,"middle")
    for hz,level,name in [(5e-9,5e-6,"NANOGrav"),(.002,3e-9,"LISA"),(75,1e-5,"LVK")]:
        label(*xy(hz,level),name,12,HexColor("#873b29"),"middle")
    return d


if __name__ == "__main__":
    renderSVG.drawToFile(draw(), str(ROOT/"results/reach.svg"))

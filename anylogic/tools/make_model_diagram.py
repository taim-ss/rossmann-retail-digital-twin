"""Draw the model's two actual PML branches; this is a schematic, not an IDE screenshot."""
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]


def main():
    root=ET.parse(ROOT/"model/P2_Rossmann_Replenishment.alp").getroot()
    blocks={e.findtext("Name"):e.findtext("ActiveObjectClass/ClassName")
            for e in root.findall("Model/ActiveObjectClasses/ActiveObjectClass/EmbeddedObjects/EmbeddedObject")}
    assert blocks=={"dayTick":"Source","daySink":"Sink","orderSource":"Source","leadDelay":"Delay","orderSink":"Sink"}
    image=Image.new("RGB",(1800,1030),"#EEF2F2")
    d=ImageDraw.Draw(image)
    def font(size,bold=False):
        return ImageFont.truetype("C:/Windows/Fonts/"+("segoeuib.ttf" if bold else "segoeui.ttf"),size)
    def text(x,y,value,size=26,fill="#25414D",bold=False):
        d.text((x,y),value,font=font(size,bold),fill=fill)
    def arrow(x1,y1,x2,y2):
        d.line((x1,y1,x2,y2),fill="#708995",width=5)
        d.polygon([(x2,y2),(x2-16,y2-10),(x2-16,y2+10)],fill="#708995")
    def box(x,y,name,title,details,colour="#FFFFFF"):
        d.rounded_rectangle((x,y,x+440,y+190),radius=20,fill=colour,outline="#A9BEC2",width=2)
        text(x+24,y+20,title,22,"#1B6D6A",True)
        text(x+24,y+59,name,33,bold=True)
        for i,line in enumerate(details):
            text(x+24,y+112+30*i,line,21)
    d.rectangle((0,0,1800,160),fill="#132D39")
    text(55,37,"INSIDE THE REPLENISHMENT MODEL",42,"#FFFFFF",True)
    text(57,101,"Five Process Modeling Library blocks. One daily state transition. An independent visual layer.",25,"#B9D6DA")
    text(70,202,"01  DAILY INVENTORY LOOP",25,bold=True)
    box(70,255,"dayTick","SOURCE",["One token at midday","Serve demand → review → order"])
    box(1260,255,"daySink","SINK",["Complete each daily token","Write final metrics on last day"])
    arrow(520,350,1240,350)
    text(620,293,"Demand = served + lost",25,bold=True)
    text(620,379,"Warm-up: review + lead time",22)
    text(70,500,"02  PURCHASE ORDERS AND DELIVERIES",25,bold=True)
    box(70,550,"orderSource","MANUAL SOURCE",["One Order agent per purchase","Quantity enters onOrder"])
    box(665,550,"leadDelay","DELAY",["Assumed delivery lead time","Independent java.util.Random"])
    box(1260,550,"orderSink","SINK",["Delivery enters onHand","Quantity leaves onOrder"])
    arrow(525,645,645,645);arrow(1120,645,1240,645)
    d.rounded_rectangle((70,795,1700,935),radius=20,fill="#DCE9E7")
    text(95,815,"Ordering rule",24,"#1B6D6A",True)
    text(95,852,"Forecast: future forecast sum + error buffer     |     Static: historical mean × protection window + buffer",23)
    text(95,891,"Order = max(0, target − onHand − onOrder). All inventory and cost parameters are assumptions.",23)
    text(70,972,"Generated from the ALP block inventory; schematic figure. Agent-built educational work under Taim Salimoun's direction.",20,"#617B87")
    path=ROOT/"model/model-flow.png"
    image.save(path)
    print(path)


if __name__=="__main__":
    main()

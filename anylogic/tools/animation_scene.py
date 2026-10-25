"""Native AnyLogic store presentation. Read-only expressions; no events or RNG.

The floor plan and customer paths are illustrative. Inventory labels and shelf bars
read the live PML model. No customer animation value is an operational KPI.
"""
import math
import xml.etree.ElementTree as ET


def colour(value):
    return int(value.lstrip("#"), 16) - 16777216


def install(b, main):
    scene = main.find("Presentation/Level/Presentation")
    scene.clear()

    def shape(parent, kind, name, x, y, z=0):
        e = b.ident(b.tag(parent, kind), name, x, y)
        e.find("ShowLabel").text = "false"
        b.tag(e, "DrawMode", "SHAPE_DRAW_2D3D")
        b.tag(e, "Z", z)
        return e

    def rect(parent, name, x, y, w, h, fill, stroke=None, depth=0, **dynamic):
        e = shape(parent, "Rectangle", name, x, y)
        for key, value in (("EmbeddedIcon", "false"), ("ZHeight", depth), ("LineWidth", 1),
                           ("LineColor", colour(stroke) if stroke else None), ("LineMaterial", "null"),
                           ("LineStyle", "SOLID"), ("Width", w), ("Height", h), ("Rotation", 0),
                           ("FillColor", colour(fill)), ("FillMaterial", "null")):
            b.tag(e, key, value)
        for key, value in dynamic.items():
            b.tag(e, key + "Code", value)
        return e

    def text(parent, name, x, y, content, size=14, fill="#243647", bold=False, expression=None):
        e = shape(parent, "Text", name, x, y)
        e.find("DrawMode").text = "SHAPE_DRAW_2D"
        b.tag(e, "Text", content)
        if expression:
            b.tag(e, "TextCode", expression)
        b.tag(e, "Color", colour(fill))
        f = b.tag(e, "Font")
        for k, v in (("Name", "SansSerif"), ("Size", size), ("Style", int(bold))):
            b.tag(f, k, v)
        b.tag(e, "Alignment", "LEFT")
        return e

    def disk(parent, name, x, y, radius, fill):
        e = shape(parent, "Polyline", name, x, y, 15)
        for k, v in (("LineWidth", 1), ("LineColor", None), ("LineMaterial", "null"),
                     ("LineStyle", "SOLID"), ("FillColor", colour(fill)), ("FillMaterial", "null")):
            b.tag(e, k, v)
        pts = b.tag(e, "Points")
        for i in range(16):
            p = b.tag(pts, "Point")
            for k, v in (("X", round(radius*math.cos(i*math.pi/8), 3)),
                         ("Y", round(radius*math.sin(i*math.pi/8), 3)), ("Z", 0)):
                b.tag(p, k, v)
        b.tag(e, "Closed", "true")
        return e

    def group(parent, name, x, y, **dynamic):
        e = shape(parent, "Group", name, x, y)
        b.tag(e, "Rotation", 0)
        for k, v in dynamic.items():
            b.tag(e, k + "Code", v)
        return b.tag(e, "Presentation")

    rect(scene, "background", 0, 0, 1640, 850, "#E9EEF1")
    rect(scene, "header", 0, 0, 1640, 88, "#132D39")
    text(scene, "title", 32, 22, "THE FORECAST-DRIVEN STORE", 28, "#FFFFFF", True)
    text(scene, "subtitle", 34, 59, "Store 164  /  Rossmann sales replay  /  Native AnyLogic PML", 15, "#B9D6DA")
    text(scene, "buildlabel", 1240, 28, "AGENT-BUILT  |  EDUCATIONAL", 14, "#8DD0C5", True)
    text(scene, "edition", 1240, 53, "AnyLogic Personal Learning Edition", 12, "#B9D6DA")
    floor = group(scene, "storeFloor", 0, 100)
    rect(floor, "yard", 25, 0, 1150, 88, "#D9E1E5")
    text(floor, "docklabel", 44, 16, "DELIVERY DOCK", 12, bold=True)
    rect(floor, "building", 40, 95, 1120, 550, "#F8F7F2", "#9DAFBA", 3)
    rect(floor, "stockRoom", 44, 99, 616, 94, "#E6E1D4", depth=2)
    rect(floor, "staffRoom", 664, 99, 492, 94, "#DFE6EA", depth=2)
    text(floor, "stockLabel", 60, 106, "BACKROOM", 11, bold=True)
    text(floor, "staffLabel", 690, 124, "STAFF / OPERATIONS", 15, fill="#6D8190")
    for i in range(20):
        rect(floor, f"pallet{i}", 64+i*28, 128, 23, 43, "#D4C7AE", "#AD9D80", 4,
             Height=f"43*Math.min(1,Math.max(0,onHand-40000)/60000)")
    rect(floor, "backwall", 44, 194, 1112, 4, "#9DAFBA", depth=25)
    rect(floor, "dockDoor", 120, 93, 140, 8, "#6C929E")
    shelves = [("household",60,208,470,30,"#A7C28A","HOUSEHOLD & CLEANING"),
               ("baby",590,208,290,30,"#E5C980","BABY"),
               ("health",920,208,220,30,"#76B8AA","HEALTH & VITAMINS"),
               ("cosmetics",140,284,420,32,"#D8A4B3","COSMETICS & SKIN CARE"),
               ("hair",600,284,280,32,"#B6A3CE","HAIR CARE"),
               ("hygiene",140,372,420,32,"#91BFCD","HYGIENE"),
               ("food",600,372,280,32,"#DEB28E","FOOD & DRINKS"),
               ("seasonal",200,500,200,50,"#D99D98","SEASONAL / PROMO")]
    for name,x,y,w,h,fill,label in shelves:
        rect(floor, name+"Base", x,y,w,h,"#E8E7E0","#A7ADB0",18)
        rect(floor, name+"Fill",x+3,y+3,w-6,h-6,fill,depth=19,
             Width=f"{w-6}*Math.min(1,Math.max(0,onHand)/40000)")
        text(floor,name+"Name",x+8,y+9,label,11,bold=True)
    for i in range(4):
        x = 665+80*i
        rect(floor,f"lane{i}",x,436,70,176,"#E9EDEF")
        rect(floor,f"belt{i}",x+23,554,13,49,"#506777",depth=15)
        rect(floor,f"desk{i}",x+37,554,12,49,"#90A2AC",depth=15)
        disk(floor,f"cashier{i}",x+59,580,8,"#1B6D6A")
        disk(floor,f"lamp{i}",x+58,543,4,"#61B49B")
        text(floor,f"laneName{i}",x+14,618,f"TILL {i+1}",10,bold=True)
    text(floor,"checkoutLabel",670,416,"CHECKOUT",11,bold=True)
    rect(floor,"photo",460,598,140,36,"#D4DEE2",depth=10)
    text(floor,"photoLabel",470,610,"PHOTO / SERVICE",11)
    rect(floor,"baskets",156,606,30,26,"#B5C6CC",depth=5)
    rect(floor,"entrance",80,641,70,8,"#468CAA")
    rect(floor,"exit",1010,641,70,8,"#4F9D83")
    text(floor,"inLabel",80,663,"ENTRANCE",11,bold=True)
    text(floor,"outLabel",1010,663,"EXIT",11,bold=True)
    # Deterministic trajectories sampled for readability, intentionally no PML events.
    # Routes go through aisle gaps, then four illustrated cashier queues.
    for i in range(36):
        lane = 688+80*(i%4)
        if i%2:
            route=[(115,630),(95,590),(95,256),(580,256),(580,344),(95,344),
                   (95,427),(lane,427),(lane,510),(lane,540),(lane,605),(1045,630),(1045,660)]
        else:
            route=[(115,630),(95,590),(95,256),(1100,256),(1100,344),(580,344),
                   (580,427),(lane,427),(lane,510),(lane,540),(lane,605),(1045,630),(1045,660)]
        phase=f"((time()*3.0+{i*0.137:.4f})%1.0)"
        def coordinate(axis):
            positions=",".join(str(p[axis]) for p in route)
            return ("((java.util.function.DoubleSupplier)()->{ double s="+phase+f"*{len(route)-1}; "
                    f"int k=Math.min({len(route)-2},(int)s); double[] p=new double[]{{{positions}}}; "
                    "return p[k]+(p[k+1]-p[k])*(s-k); }).getAsDouble()")
        cust=group(floor,f"customer{i}",115,630,X=coordinate(0),Y=coordinate(1),
                   Visible="visualOn && nDays>0 && demand[Math.min(nDays-1,Math.max(0,dayCount-1))]>0")
        disk(cust,f"body{i}",0,0,7,["#397B92","#BB7655","#6D698D","#537B68"][i%4])
        disk(cust,f"head{i}",0,-2,3,"#F1D5BA")
        rect(cust,f"bag{i}",5,3,5,6,"#C5B487",depth=4)
    truck=group(floor,"deliveryTruck",200,40,
                X="200+600*Math.max(0,1-((time()*1.0)%7.0))",
                Visible="visualOn && (time()%7.0)<1.1")
    rect(truck,"cargo",0,0,125,40,"#43858B","#2E6369",20)
    rect(truck,"cab",-32,3,30,37,"#244853",depth=20)
    rect(truck,"windshield",-28,6,17,25,"#B7DADF",depth=21)
    for x in (-20,20,100):
        rect(truck,f"wheel{x+20}",x,35,15,8,"#253C47",depth=3)
    text(truck,"truckBrand",12,14,"REPLENISH",11,"#FFFFFF",True)
    # Right-hand live model dashboard.
    rect(scene,"dashboard",1200,108,416,654,"#FFFFFF")
    text(scene,"liveTitle",1224,132,"LIVE INVENTORY",17,bold=True)
    text(scene,"date",1224,169,"",19,bold=True,expression=
         '(firstDay==null?"Loading data...":firstDay.plusDays(Math.max(0,dayCount-1)).toString())')
    text(scene,"forecast",1224,204,"",14,expression=
         '"Forecast: "+(forecastSource==0?"ORACLE":forecastSource==1?"SEASONAL NAIVE":"ML")')
    text(scene,"stockCaption",1224,249,"ON HAND  /  TURNOVER UNITS",11,fill="#72858F",bold=True)
    text(scene,"stockValue",1224,273,"",32,fill="#1B6D6A",bold=True,
         expression='String.format(java.util.Locale.ROOT,"%,.0f",onHand)')
    text(scene,"orderCaption",1224,330,"ON ORDER",11,fill="#72858F",bold=True)
    text(scene,"orderValue",1224,353,"",25,bold=True,
         expression='String.format(java.util.Locale.ROOT,"%,.0f",onOrder)')
    text(scene,"serviceCaption",1224,409,"FILL RATE  /  SCORED DAYS",11,fill="#72858F",bold=True)
    text(scene,"serviceValue",1224,433,"",27,bold=True,
         expression='kpiDays==0?"WARM-UP":String.format(java.util.Locale.ROOT,"%.1f%%",100*sumSold/Math.max(1,sumDemand))')
    text(scene,"ordersLabel",1224,488,"",14,expression='"Orders: "+orders+"   Deliveries: "+deliveries')
    text(scene,"stockout",1224,518,"",14,expression='"Stock-out days: "+stockoutDays')
    text(scene,"policyLabel",1224,557,"",13,expression='"Rule: "+(policy==1?"STATIC":"ORDER-UP-TO")')
    text(scene,"assumptions",1224,592,"ASSUMPTIONS",12,fill="#AC714E",bold=True)
    text(scene,"lt",1224,619,"",12,expression='"Lead time "+leadTimeDays+" d  |  Review "+reviewDays+" d"')
    text(scene,"units",1224,646,"1 unit = EUR 1 turnover (normalization)",12)
    text(scene,"layoutDisclaimer",1224,690,"Schematic floor plan; no actual store layout.",11,fill="#72858F")
    rect(scene,"footer",24,780,1592,48,"#DCE6E8")
    text(scene,"disclaimer",40,793,
         "Illustrative sampled customers, cashier queues and truck motion. Shelf fill reads model stock; category mix is assumed.",13)
    text(scene,"disclaimer2",40,814,
         "Daily inventory and deliveries come from the PML simulation. Visual movement adds no events, agents or random draws.",11,fill="#57717D")


def configure_experiment(b, model):
    """An animated real-time copy of Simulation; batch experiments stay virtual."""
    import copy
    exps = model.find("Experiments")
    animation = copy.deepcopy(exps.find("SimulationExperiment"))
    animation.find("Id").text = str(int(animation.findtext("Id"))+800000)
    animation.find("Name").text = "Animation"
    pp=animation.find("PresentationProperties")
    pp.find("ExecutionMode").text="realTimeScaled"
    pp.find("Title").text="The forecast-driven store | P2"
    pp.find("EnableDeveloperPanel").text="false"
    pp.find("ShowDeveloperPanelOnStart").text="false"
    b.tag(pp,"RealTimeScale",0.5)
    for name,value in (("forecastSource","2"),("visualOn","true")):
        par=next(e for e in animation.find("Parameters") if e.findtext("ParameterName")==name)
        b.code(par,"ParameterValue",value)
    exps.append(animation)
    model.find("Frame/Width").text="1640"
    model.find("Frame/Height").text="850"

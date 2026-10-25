"""Render the inspected Markdown report and genuine native figures as an A4 PDF."""
from pathlib import Path
import html
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak

ROOT=Path(__file__).resolve().parents[1]


def inline(value):
    value=html.escape(value)
    value=re.sub(r"\*\*(.*?)\*\*",r"<b>\1</b>",value)
    value=re.sub(r"`(.*?)`",r'<font face="Courier">\1</font>',value)
    value=re.sub(r"\[([^\]]+)\]\(([^)]+)\)",r"\1",value)
    return value


def main():
    for name,file in (("Segoe","segoeui.ttf"),("SegoeBold","segoeuib.ttf")):
        pdfmetrics.registerFont(TTFont(name,str(Path("C:/Windows/Fonts")/file)))
    pdfmetrics.registerFontFamily("Segoe",normal="Segoe",bold="SegoeBold",italic="Segoe",boldItalic="SegoeBold")
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Body",fontName="Segoe",fontSize=9.6,leading=14,spaceAfter=7,textColor=colors.HexColor("#283E4A")))
    styles.add(ParagraphStyle(name="H1a",fontName="SegoeBold",fontSize=23,leading=29,spaceAfter=16,textColor=colors.HexColor("#153D48")))
    styles.add(ParagraphStyle(name="H2a",fontName="SegoeBold",fontSize=14,leading=19,spaceBefore=15,spaceAfter=8,textColor=colors.HexColor("#1B6D6A")))
    styles.add(ParagraphStyle(name="H3a",fontName="SegoeBold",fontSize=11,leading=15,spaceBefore=11,spaceAfter=6,textColor=colors.HexColor("#153D48")))
    styles.add(ParagraphStyle(name="Cell",parent=styles["Body"],fontSize=7.5,leading=11,spaceAfter=0))
    story=[]
    story.append(Paragraph("THE FORECAST-DRIVEN STORE",styles["H1a"]))
    story.append(Paragraph("A transparent retail replenishment experiment<br/>Store 164 · SQL / Python / Excel / AnyLogic",styles["H2a"]))
    story.append(Paragraph("Taim Salimoun directed the Claude/Codex agent team. Educational work using AnyLogic Personal Learning Edition.",styles["Body"]))
    hero=ROOT/"model/store-view.png"
    if hero.exists():
        image=Image(str(hero))
        image.drawHeight=495*image.imageHeight/image.imageWidth
        image.drawWidth=495
        story.extend([Spacer(1,12),image,Spacer(1,8)])
    story.append(Paragraph("Rossmann supplies sales, not observed inventory or orders. Inventory parameters, costs and the floor plan are assumptions. Native and replica evidence are labelled separately.",styles["Body"]))
    story.append(PageBreak())
    lines=(ROOT/"docs/report.md").read_text(encoding="utf-8").splitlines()
    i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:
            i+=1
            continue
        if line.startswith("|"):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith("|"):
                cells=[x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+",c) for c in cells):
                    rows.append([Paragraph(inline(c),styles["Cell"]) for c in cells])
                i+=1
            if rows:
                count=max(len(r) for r in rows)
                rows=[r+[""]*(count-len(r)) for r in rows]
                table=Table(rows,colWidths=[495/count]*count,repeatRows=1,hAlign="LEFT")
                table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#DCE9E7")),
                                           ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F4F7F8")]),
                                           ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),
                                           ("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),7),
                                           ("BOTTOMPADDING",(0,0),(-1,-1),7)]))
                story.extend([table,Spacer(1,8)])
            continue
        if line.startswith("# "):
            style="H1a"
            line=line[2:]
        elif line.startswith("## "):
            style="H2a"
            line=line[3:]
        elif line.startswith("### "):
            style="H3a"
            line=line[4:]
        else:
            style="Body"
            if line.startswith("- "):
                line="• "+line[2:]
            elif line.startswith("!["):
                i+=1
                continue
        story.append(Paragraph(inline(line),styles[style]))
        i+=1
    story.append(PageBreak())
    for caption,path in (("Service versus stock — Python replica",ROOT/"results/analysis/frontier/service_vs_stock.png"),
                         ("Sensitivity to assumed lead time — Python replica",ROOT/"results/analysis/frontier/stock_needed_vs_leadtime.png")):
        story.append(Paragraph(caption,styles["H2a"]))
        image=Image(str(path))
        image.drawHeight=495*image.imageHeight/image.imageWidth
        image.drawWidth=495
        story.append(image)
    target=ROOT/"model/model-description.pdf"
    def footer(canvas,doc):
        canvas.setFont("Segoe",8)
        canvas.setFillColor(colors.HexColor("#6B7E88"))
        canvas.drawString(50,28,"Agent-built educational model · Assumption-driven inventory study")
        canvas.drawRightString(A4[0]-50,28,str(doc.page))
    SimpleDocTemplate(str(target),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=46,bottomMargin=48,
                      title="The forecast-driven store — model description",author="Taim Salimoun; Claude/Codex agent team").build(story,onFirstPage=footer,onLaterPages=footer)
    print(target)


if __name__=="__main__":
    main()

"""Native daily inventory Java snippets; presentation code cannot modify them."""
N_DAYS = ("(int)(java.time.temporal.ChronoUnit.DAYS.between(java.time.LocalDate.parse(firstDate),"
          "java.time.LocalDate.parse(lastDate)))+1")

LOADER = r'''getEngine().setStopTime(Double.POSITIVE_INFINITY);
if (policy<0 || policy>1 || forecastSource<0 || forecastSource>2 || reviewDays<1 || leadTimeDays<1 || !Double.isFinite(serviceZ) || unitPrice<=0 || margin<0 || margin>=1)
 throw new IllegalArgumentException("Invalid P2 parameter");
firstDay = java.time.LocalDate.parse(firstDate);
nDays = (int)(java.time.temporal.ChronoUnit.DAYS.between(firstDay, java.time.LocalDate.parse(lastDate)))+1;
demand = new double[nDays]; fc = new double[3][nDays];
boolean[] haveD = new boolean[nDays]; boolean[][] haveF = new boolean[3][nDays];
java.util.function.Function<String, java.util.List<String[]>> rd = (name) -> {
 try { java.util.List<String[]> out = new java.util.ArrayList<>();
  for (String ln : java.nio.file.Files.readAllLines(java.nio.file.Paths.get(dataDirectory, name), java.nio.charset.StandardCharsets.UTF_8)) out.add(ln.split(","));
  return out; }
 catch (java.io.IOException ex) { throw new IllegalStateException("Cannot read "+name+" in "+dataDirectory, ex); } };
for (String[] r : rd.apply("store_day_demand.csv")) {
 if (r[0].equals("date") || Integer.parseInt(r[1].trim())!=storeId) continue;
 int k = (int)java.time.temporal.ChronoUnit.DAYS.between(firstDay, java.time.LocalDate.parse(r[0]));
 if (k>=0 && k<nDays) { demand[k]=Double.parseDouble(r[2]); haveD[k]=true; } }
{ java.time.LocalDate a = java.time.LocalDate.parse(trainStart), b = java.time.LocalDate.parse(trainEnd);
 double sm = 0, sq2 = 0; int c2 = 0;
 for (String[] r : rd.apply("store_day_demand.csv")) {
  if (r[0].equals("date") || Integer.parseInt(r[1].trim())!=storeId) continue;
  java.time.LocalDate dt = java.time.LocalDate.parse(r[0]);
  if (dt.isBefore(a) || dt.isAfter(b)) continue;
  double v = Double.parseDouble(r[2]); sm += v; sq2 += v*v; c2++; }
 if (c2<100) throw new IllegalStateException("Too few training days for the static rule: "+c2);
 staticMean = sm/c2; staticSd = Math.sqrt(Math.max(0, sq2/c2 - staticMean*staticMean)); }
String[] files = {"forecast_oracle.csv","forecast_naive.csv","forecast_ml.csv"};
for (int s=0;s<3;s++) for (String[] r : rd.apply(files[s])) {
 if (r[0].equals("date") || Integer.parseInt(r[1].trim())!=storeId) continue;
 int k = (int)java.time.temporal.ChronoUnit.DAYS.between(firstDay, java.time.LocalDate.parse(r[0]));
 if (k>=0 && k<nDays) { fc[s][k]=Double.parseDouble(r[2]); haveF[s][k]=true; } }
for (int k=0;k<nDays;k++) { if (!haveD[k]) throw new IllegalStateException("Missing demand day "+k);
 for (int s=0;s<3;s++) if (!haveF[s][k]) throw new IllegalStateException("Missing forecast "+s+" day "+k); }
double sq = 0; int cnt = 0; String want = forecastSource==1 ? "naive" : "ml";
if (forecastSource!=0) for (String[] r : rd.apply("forecast_error_distribution.csv")) {
 if (r[0].equals("model") || !r[0].equals(want) || Integer.parseInt(r[1].trim())!=storeId) continue;
 int h = Integer.parseInt(r[4].trim()); if (h<errHorizonMin || h>errHorizonMax) continue;
 double e = Double.parseDouble(r[8]); sq += e*e; cnt++; }
sigma = forecastSource==0 ? 0.0 : Math.sqrt(sq/Math.max(1,cnt));
leadRng = new java.util.Random(20000L+repSeed);
int warm = reviewDays+(int)Math.ceil(leadTimeDays);
onHand = 0; for (int k=0;k<warm && k<nDays;k++) onHand += demand[k];
onHandStart = onHand; onOrder = 0; dayCount = 0; kpiDays = 0; orders = 0; drawsLogged = 0;
sumDemand = sumSold = sumLost = sumOnHand = holdCost = shortCost = ordCost = 0; stockoutDays = 0;
nativeLog.setLength(0); nativeLog.append("P2_META,store="+storeId+",data=ROSSMANN_DERIVED_NOT_REDISTRIBUTABLE,inventory_parameters=ASSUMPTION\n");
nativeLog.append("P2_CONFIG,"+repSeed+","+forecastSource+","+nDays+","+reviewDays+","+leadTimeDays+","+serviceZ+","+holdingRate+","+margin+","+orderCost+","+unitPrice+","+sigma+","+cnt+","+onHandStart+","+policy+","+staticMean+","+staticSd+"\n");'''

TICK = r'''int d = dayCount++;
double dem = demand[d];
double sold = Math.min(onHand, dem); double lost = dem - sold; onHand -= sold;
int warm = reviewDays+(int)Math.ceil(leadTimeDays);
if (d>=warm) { kpiDays++; sumDemand+=dem; sumSold+=sold; sumLost+=lost; if (lost>1e-9) stockoutDays++;
 sumOnHand+=onHand; holdCost+=onHand*unitPrice*(1-margin)*holdingRate/365.0; shortCost+=lost*margin*unitPrice; }
double qty = 0; int lt = 0;
if (d % reviewDays == 0) {
 double u = leadRng.nextDouble();
 lt = (int)Math.round(leadTimeDays) + (u<0.25 ? -1 : (u>0.75 ? 1 : 0)); if (lt<1) lt=1;
 if (drawsLogged<5) { nativeLog.append("P2_CRN,"+repSeed+","+forecastSource+","+drawsLogged+","+u+","+lt+"\n"); drawsLogged++; }
 double target = 0;
 if (policy==1) { target = staticMean*warm + serviceZ*staticSd*Math.sqrt(reviewDays+leadTimeDays); }
 else { for (int k=d+1; k<=d+warm && k<nDays; k++) target += fc[forecastSource][k];
  target += serviceZ*sigma*Math.sqrt(reviewDays+leadTimeDays); }
 if (d+lt < nDays) { qty = Math.max(0.0, target-(onHand+onOrder));
  if (qty>0) { onOrder += qty; pendingQty = qty; pendingLead = lt; pendingDay = d; orderSource.inject(1);
   if (d>=warm) { orders++; ordCost += orderCost; } } } }
nativeLog.append("P2_DAY,"+d+","+dem+","+fc[forecastSource][Math.min(d,nDays-1)]+","+sold+","+lost+","+onHand+","+onOrder+","+qty+","+lt+"\n");'''

FINISH = r'''if (dayCount==nDays) {
 double fill = sumDemand>0 ? sumSold/sumDemand : 1.0;
 double meanOnHand = kpiDays>0 ? sumOnHand/kpiDays : 0.0;
 double total = holdCost+shortCost+ordCost;
 nativeLog.append("P2_DONE,"+repSeed+","+forecastSource+","+kpiDays+","+sumDemand+","+sumSold+","+sumLost+","+fill+","+stockoutDays+","+meanOnHand+","+orders+","+holdCost+","+shortCost+","+ordCost+","+total+","+sigma+","+onHandStart+","+time()+","+policy+","+serviceZ+","+leadTimeDays+"\n");
 try { java.nio.file.Path dir = java.nio.file.Paths.get(outputDirectory); java.nio.file.Files.createDirectories(dir);
  java.nio.file.Files.writeString(dir.resolve("p2-store"+storeId+"-pol"+policy+"-src"+forecastSource+"-z"+String.format(java.util.Locale.ROOT,"%.2f",serviceZ)+"-L"+String.format(java.util.Locale.ROOT,"%.0f",leadTimeDays)+"-seed"+repSeed+".log"), nativeLog.toString(), java.nio.charset.StandardCharsets.UTF_8);
 } catch (java.io.IOException ex) { throw new IllegalStateException("Cannot write run log: "+outputDirectory, ex); }
 getEngine().setStopTime(time()); }'''

RECEIVE = r'''Order o = (Order)agent; onHand += o.qty; onOrder -= o.qty; deliveries++;
nativeLog.append("P2_RECV,"+(int)Math.floor(time())+","+o.placedDay+","+o.qty+","+o.leadDays+"\n");'''

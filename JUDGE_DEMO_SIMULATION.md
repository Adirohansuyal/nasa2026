# 🎬 EARTHPULSE-X — Judge Demo Simulation Script

> **Purpose:** Ye file har page ka demo script hai. Har page ke liye likha hai ki:
> - Is page ka kya purpose hai
> - Judges ko kya dikhana hai
> - Kya click karna hai
> - Kya bolna hai (exact script)
> - Kaunse concepts explain karne hain
>
> Demo ke time bas is file ko follow karo, page by page.

---

## 📋 TABLE OF CONTENTS

1. [NASA Ka Challenge](#1-nasa-ka-challenge)
2. [Background: Satellites Aur Variables](#2-satellites-aur-variables)
3. [Background: Statistical Concepts](#3-statistical-concepts)
4. [PAGE 1 — Home / Mission Control](#page-1--home--mission-control)
5. [PAGE 2 — UG-ESI Mission Control (Interactive Workflow)](#page-2--ug-esi-mission-control)
6. [PAGE 3 — Earth Observation (Satellite Explorer)](#page-3--earth-observation)
7. [PAGE 4 — Trend Detective (NASA 4 Questions)](#page-4--trend-detective)
8. [PAGE 5 — Anomaly Intelligence (District Maps)](#page-5--anomaly-intelligence)
9. [PAGE 6 — Interaction Network (Variable Relationships)](#page-6--interaction-network)
10. [PAGE 7 — Physics & Uncertainty (Data Quality)](#page-7--physics--uncertainty)
11. [PAGE 8 — AI Scientist (Evidence-Grounded Chat)](#page-8--ai-scientist)
12. [Glossary](#glossary)
13. [Judge Q&A Ready Answers](#judge-qa)

---

## 1. NASA KA CHALLENGE

NASA ka official challenge hai: **"Be An Earth System Trend Detective!"**

Matlab: NASA Earth observation satellite data use karke identify karo:

| Sawaal | Matlab |
|---|---|
| **WHAT is changing?** | Temperature badh rahi hai? Vegetation bigad raha hai? Soil dry ho raha hai? |
| **WHERE is it changing?** | Kaunse districts mein zyada change hai? |
| **HOW MUCH is changing?** | Kitne °C per year? Kitne mm per month? |
| **Is it statistically significant?** | Ya sirf random fluctuation hai? |

**Humara jawaab:** EARTHPULSE-X — ek tool jo NASA satellite data se ye chaaro sawaalon ka answer deta hai, with proper statistical rigour aur evidence-grounded AI explanations.

---

## 2. SATELLITES AUR VARIABLES

### 🛰️ NASA ke Satellites — Simple Mein

NASA space mein satellites rakhta hai jo Earth ko continuously observe karte hain. Har satellite kuch alag measure karta hai. Humne 3 satellites se 5 variables liye:

---

#### 🌡️ MODIS (Moderate Resolution Imaging Spectroradiometer)

**Kya hai:** NASA ka satellite instrument jo Terra aur Aqua satellites pe mounted hai. Ye Earth ke surface ka temperature aur vegetation "greenness" measure karta hai.

**Kaise kaam karta hai:**
- **LST ke liye:** Earth ke surface se aane wali thermal radiation (heat) ko measure karta hai.
- **NDVI ke liye:** Plants red light absorb karte hain aur near-infrared light reflect karte hain. Is ratio se NDVI nikalta hai.

**Variable 1: LST (Land Surface Temperature)**
- Ye air temperature nahi hai — ye **zameen ki surface** ka temperature hai
- Unit: Kelvin (K) — 0°C = 273.15 K, to ~300K = ~27°C
- Example: agar LST 290K hai to zameen ki surface ~17°C pe hai
- **Practical matlab:** garmi badh rahi hai ya nahi, urban heat island, agriculture impact

**Variable 2: NDVI (Normalized Difference Vegetation Index)**
- Ye batata hai ki area mein **kitna green vegetation** hai
- Formula: `(NIR - Red) / (NIR + Red)`
- Value 0 se 1:
  - **0.1–0.3:** barren soil, kam plants
  - **0.3–0.5:** moderate vegetation (grassland, crops)
  - **0.5–0.8:** dense forest, healthy vegetation
- **Practical matlab:** forest health, agriculture, deforestation, desertification

---

#### 💧 SMAP (Soil Moisture Active Passive)

**Kya hai:** NASA ka satellite jo soil mein kitni moisture (paani) hai wo measure karta hai.

**Kaise kaam karta hai:** Soil ki surface se aane wali microwave radiation ko measure karta hai. Paani aur dry soil ki microwave signature alag hoti hai.

**Variable 3: SMAP AM (Morning Soil Moisture)**
- Satellite subah ~6 AM ko Uttarakhand ke upar se guarta hai
- Unit: m³/m³ — cubic meter soil mein kitna cubic meter paani
- Typical range: 0.10–0.30 (10%–30% paani)
- **Practical matlab:** drought condition, irrigation need, flood risk

**Variable 4: SMAP PM (Evening Soil Moisture)**
- Same satellite shaam ~6 PM ko dobara guarta hai
- Dono readings compare karne se pata chalta hai ki measurement consistent hai

---

#### 🌧️ GPM (Global Precipitation Measurement)

**Kya hai:** NASA ka satellite jo worldwide rainfall measure karta hai.

**Kaise kaam karta hai:** Clouds se aane wali microwave radiation ko measure karta hai. Raindrops ki size aur density se precipitation rate nikalta hai.

**Variable 5: GPM Monthly Precipitation**
- Har month ka total rainfall, millimeters (mm) mein
- Uttarakhand monsoon (Jul–Sep) mein 200-400 mm/month common hai
- **Practical matlab:** monsoon pattern change, drought/flood indicator

---

#### 📊 Summary Table

| Satellite | Variable | Kya Measure Karta Hai | Unit | Example |
|---|---|---|---|---|
| MODIS | LST | Zameen ki surface temperature | Kelvin (K) | ~295K (22°C) |
| MODIS | NDVI | Vegetation greenness | Index (0-1) | ~0.45 |
| SMAP | SMAP AM | Morning soil moisture | m³/m³ | ~0.20 |
| SMAP | SMAP PM | Evening soil moisture | m³/m³ | ~0.18 |
| GPM | Precipitation | Monthly total rainfall | mm | ~100 mm/month |

---

## 3. STATISTICAL CONCEPTS

### 📈 OLS Linear Regression (Ordinary Least Squares)

**Simple matlab:** Ek seedhi line draw karo data points ke through — best fit line.

**Kya batata hai:**
- **Slope:** kitna change per time step
- **R²:** line data ko kitna % explain karti hai (0–1)
  - R² = 0.9 → 90% variation explained
  - R² = 0.3 → sirf 30% explained, baaki noise/seasonality
- **p-value:** slope significantly 0 se different hai ya nahi

**Problem:** Outliers se sensitive hai.

---

### 📊 Mann-Kendall Trend Test

**Simple matlab:** Har pair of months ko compare karo — pichla month zyada tha ya current? Agar consistently badh raha hai to "increasing", consistently kam to "decreasing".

**Kyu use karte hain:**
- **Non-parametric:** normal distribution assume nahi karta
- **No linearity assumption:** monotonic trend detect karta hai
- **Robust:** outliers se kam affected

**Output:**
- **τ (tau):** −1 se +1, trend strength
- **p-value:** < 0.05 → statistically significant

---

### 📏 Sen's Slope (Theil-Sen Estimator)

**Simple matlab:** Har pair ke beech ka slope calculate karo, phir unka **median** lo. Outliers se affected nahi hota.

**Kyu OLS se behtar hai:**
- OLS ek outlier se shift ho jata hai
- Sen's slope mein outlier ka asar median pe nahi padta
- Environmental data mein outliers common hain

**Output:**
- **Slope:** per time step (e.g., per month)
- **95% Confidence Interval:** Agar CI 0 ko exclude karta hai to trend robustly non-zero hai

**Example:** LST: Sen's slope = −0.0144 K/month → ×12 = **−0.173 K/year**

---

### 🔄 Autocorrelation (Lag-1)

**Simple matlab:** Is mahine ki value pichle mahine ki value pe depend karti hai ya nahi?

**Kyu matter karta hai:**
- Mann-Kendall test assume karta hai observations **independent** hain
- Lekin monthly temperature mein autocorrelation hoti hai
- Agar ignore karte to **false positives** milte
- LST naive p = 4×10⁻⁵ → corrected p = 0.003 (120x less confident!)

| Variable | Lag-1 Autocorrelation | Strength |
|---|---|---|
| LST | 0.549 | Strong |
| NDVI | 0.502 | Strong |
| SMAP AM | 0.454 | Moderate |
| SMAP PM | 0.501 | Strong |
| GPM | 0.088 | Weak |

---

### 🔧 Modified Mann-Kendall (Hamed & Rao 1998)

**Simple matlab:** Original Mann-Kendall + autocorrelation correction.

1. Lag-1 autocorrelation calculate karo
2. **Effective sample size** adjust karo (126 → ~50 ho sakta hai)
3. Chhota effective sample size = larger p-value = more conservative

---

### 🎯 FDR (False Discovery Rate) — Benjamini-Hochberg

**Simple matlab:** Multiple tests kar rahe ho to koi ek random "significant" dikh jata hai. FDR correct karta hai.

**Kyu zaroori hai:** 20 tests karo alpha=0.05 pe → 1 guaranteed false positive. FDR ye control karta hai.

---

### ⚡ CUSUM Change-Point Detection

**Simple matlab:** Data mein kab pattern suddenly shift hua. Cumulative sum of deviations track karta hai.

---

### 🔗 Spearman Rank Correlation

**Simple matlab:** Do variables ek saath move karte hain ya nahi?

**Kyu Pearson nahi:**
- Pearson linear relationship maangta hai
- Spearman non-linear (but monotonic) relationship bhi detect karta hai
- Environmental data often non-linear

**Lag-aware version:**
- Lag 0: same month
- Lag 1: X is month → Y next month (X predicts Y 1 month later?)

---

### 📉 Robust Z-Score

**Simple matlab:** Ek value normal se kitni different hai? Mean+std nahi — **median+MAD** use karta hai (outlier-proof).

**Formula:** `0.6745 × (current − historical median) / MAD`

**Threshold:** |Z| > 3.5 → high anomaly

---

### 🌡️ Climatology & Deseasonalised Anomaly

**Climatology:** Har calendar month ka 10-year average (normal value).
**Anomaly:** Observed value minus climatological normal.
- July 2023 LST = 308K, July climatology = 305K → Anomaly = +3K (3K warmer than normal)

---

---

## 4. PAGE-BY-PAGE DEMO SCRIPT

---

## PAGE 1 — Home / Mission Control

**File:** `app.py`
**Time:** 1.5 min

### Is page ka purpose
Ye landing page hai. Pehla impression. NASA challenge frame karta hai, UG-ESI methodology dikhata hai, aur live data metrics dikhata hai.

### Kya dikhana hai

1. **Hero banner** — "EARTHPULSE-X" title, subtitle "Uncertainty-Guided Earth System Intelligence", aur stat pills (Uttarakhand, 2015-2025, 3 satellites, 126 months)

2. **Live data metrics** — 5 KPI tiles (LST, NDVI, SMAP AM, SMAP PM, GPM) with latest month values

3. **NASA Challenge section** — 4 question cards (WHAT, WHERE, HOW MUCH, SIGNIFICANT)

4. **Key Findings** — 5 verdict cards from trend results:
   - 🌡️ LST: 📉 Significant decrease
   - 🌿 NDVI: 📈 Significant increase
   - 💧 SMAP AM/PM: ⚪ No significant trend
   - 🌧️ GPM: ⚪ No significant trend

5. **UG-ESI Methodology** — 4 contribution cards

6. **System Architecture** — 7-step flow diagram

7. **Earth System Observation Trends** — interactive variable selector + time series chart

8. **Multi-Variable Overview** — faceted chart with all 4 variables

9. **Data Quality & Coverage** — coverage chart

### Kya bolna hai

> "Welcome to EARTHPULSE-X. NASA ka challenge tha — Be An Earth System Trend Detective. Matlab satellite data se identify karo ki kya badal raha hai, kahan, kitna, aur significant hai ya nahi."

> "Humne Uttarakhand liya — 2015 se 2025 tak, 126 mahine ka data. 3 NASA satellites: MODIS se temperature aur vegetation, SMAP se soil moisture, GPM se rainfall."

**Key Findings cards dikhao:**
> "Dekho — LST significant decreasing, NDVI significant increasing. Teen variables mein koi significant trend nahi. Absence of significance bhi finding hai."

**Architecture flow dikhao:**
> "Humara approach — UG-ESI. Ye humari proposed methodology hai. NASA ne ye mandatory nahi kiya. Humne unke basic requirements ko extend kiya — variable selection se lekar AI-grounded explanation tak."

### Concepts explain karne hain
- MODIS, SMAP, GPM kya hai (Section 2 se)
- UG-ESI kya hai (4 contributions)
- "Absence of significance is also a finding"

---

## PAGE 2 — UG-ESI Mission Control

**File:** `pages/01_Mission_Control.py`
**Time:** 3 min

### Is page ka purpose
Ye humara core interactive workflow page hai. 4 UG-ESI contributions ko ek saath end-to-end chalata hai: variable selection → trend analysis → interaction graph → AI research report.

### Is page ko kyu dikhana hai
Judges ko ye dikhana ki ye sirf dashboard nahi — ye ek working scientific workflow hai. User objective select kare, system variables rank kare, trend analysis kare, interaction graph banaye, aur AI report generate kare.

### Step 1: Adaptive Variable Selection

**Kya click karna hai:**
- "RESEARCH OBJECTIVE" dropdown se "🏜️ Drought Investigation" select karo

**Kya dikhata hai:**
- 5 variable cards with composite scores
- GPM highest score (drought ke liye precipitation most relevant)
- LST, SMAP PM, SMAP AM moderate
- NDVI lower

**Kya bolna hai:**
> "Pehla contribution — Adaptive Variable Selection. Humne ek objective choose kiya: drought investigation. System ne saare 5 variables ko score kiya data quality, signal strength, variability, aur objective relevance pe. Notice karo — GPM sabse high score hai kyunki drought ke liye precipitation sabse relevant hai."

> "Important: humne variables p-value pe select nahi kiye. Wo selection bias hota. Humne data quality aur signal properties pe rank kiya."

**"Explain this variable selection" button dabao:**
> "AI ab un scores ko plain language mein explain karega."

### Step 2: Multi-Scale Trend Intelligence

**Kya click karna hai:**
- Variable dropdown se "🌡️ Land Surface Temperature" select karo

**Kya dikhata hai:**
- 4 KPI tiles: Trend Direction, Annual Change (Sen's), MK p-value, OLS R²
- Time series with OLS trend line + Sen's slope line
- Seasonal climatology bar chart
- Deseasonalised anomaly bar chart
- Change points table (CUSUM detected)

**Kya bolna hai:**
> "Doosra contribution — Multi-Scale Trend Intelligence. System ne 3 methods ek saath chalaye: Mann-Kendall test, Sen's slope, aur OLS regression."

> "Sen's slope kya hai? Har pair ka slope nikalke median lete hain. Outlier-proof. LST ka Sen's slope = −0.173 K per year."

> "95% confidence interval bhi diya hai. Agar CI 0 ko exclude karta hai to trend real hai."

> "Anomaly chart dekho — har month ka observed value minus 10-year average for that month. Green = above normal, red = below normal."

### Step 3: Uncertainty-Guided Interaction Graph

**Kya click karna hai:**
- Lag slider: 3 months (default)
- Confidence threshold: 0.30 (default)

**Kya dikhata hai:**
- 4 metrics: relationships tested, FDR significant, high-confidence edges, lags tested
- Network graph with nodes and colored edges (green=positive, red=negative)
- Edge table with correlation, q-value, confidence, temporal stability

**Kya bolna hai:**
> "Teesra contribution — Uncertainty-Guided Interaction Graph. Ye page batata hai ki variables ek doosre se kaise connected hain."

> "Spearman correlation use kiya — Pearson nahi. Spearman better hai kyunki non-linear relationships bhi detect karta hai."

> "Har edge pe ek confidence score hai — effect size + statistical certainty + data volume + temporal stability. Ye batata hai ki relationship kitni reliable hai."

> "FDR correction apply kiya — 70+ relationships test kiye, multiple testing correction zaroori tha."

### Step 4: Evidence-Grounded Research Report

**Kya click karna hai:**
- "🧠 GENERATE UG-ESI RESEARCH REPORT" button

**Kya dikhata hai:**
- AI generates a structured report: Key Findings → Variable Relationships → Data Reliability → Limitations → Research Verdict

**Kya bolna hai:**
> "Chautha contribution — Evidence-Grounded AI Scientist. AI ko actual statistical results diye hain — variable selection scores, trend results, interaction graph. AI inhe synthesize karke report banata hai."

> "Dekho — har claim data-backed hai. AI kahin bhi invented numbers nahi deta. Ye fundamental difference hai — AI scientist explain karta hai, fabricate nahi karta."

### Concepts explain karne hain
- Adaptive variable selection: kya hai, kyu p-value pe select nahi kiya
- Sen's slope vs OLS: kyu robust
- Spearman vs Pearson: kyu non-parametric
- Edge confidence: kya factors combine hote hain
- Evidence-grounded AI: AI invent nahi karta

---

## PAGE 3 — Earth Observation

**File:** `pages/02_Earth_Observation.py`
**Time:** 2 min

### Is page ka purpose
Ye page NASA satellite data ko geographic map pe dikhata hai. NetCDF spatial data ko lat/lon coordinates pe render karta hai with district boundaries overlay. Judges ko actual satellite imagery dikhata hai.

### Kya dikhana hai

1. **Controls** — month selector, quality (strict/relaxed), variable selector

2. **5 KPI tiles** — Mean, Min, Max, Std Dev, Valid Pixels for selected month

3. **Satellite Imagery map** — geographic heatmap with district boundaries overlaid
   - LST → red-yellow colorscale
   - NDVI → green colorscale
   - SMAP → blue colorscale
   - GPM → cividis colorscale

4. **Validity Map** — green = valid pixels, red = no data, with coverage annotation

5. **Strict vs Relaxed comparison** — side-by-side maps for same variable

6. **Pixel Value Distribution** — histogram

7. **Temporal History** — 10-year time series with trend lines

### Kya bolna hai

> "Ye page actual NASA satellite data ko geographic map pe dikhata hai. Har pixel ~9km × 9km area hai. Data EPSG:6933 (equal-area projection) se WGS84 (lat/lon) pe convert kiya gaya hai."

**Satellite imagery map dikhao:**
> "Dekho — har color cell ek satellite pixel hai. LST ke liye: red = zyada garam, yellow = thandi. District boundaries white mein overlay hain."

**Validity map dikhao:**
> "Ye map dikhata hai ki satellite ne us month mein kitna area dekha. Green = valid reading, red = no data. Clouds ya terrain ki wajah se kuch pixels missing ho sakte hain."

**Strict vs Relaxed dikhao:**
> "Strict quality mein sirf cleanest readings rakhte hain. Relaxed mein zyada readings accept karte hain. Gap zyada ho to iska matlab borderline readings zyada hain."

### Concepts explain karne hain
- Satellite pixel kya hai (~9km × 9km)
- EPSG:6933 → WGS84 conversion (projected to geographic)
- Strict vs relaxed quality
- Coverage = kitna % area ka valid reading
- Optical sensor (MODIS) clouds se block, microwave (GPM/SMAP) clouds ke through

---

## PAGE 4 — Trend Detective

**File:** `pages/03_Trend_Detective.py`
**Time:** 3 min

### Is page ka purpose
Ye page NASA ke chaaro sawaalon ka direct answer deta hai. Autocorrelation-adjusted trend results use karta hai — naive p-values nahi. Ye sabse important page hai judges ke liye.

### Section A: All-Variable Summary Table (Q1 + Q3 + Q4)

**Kya dikhata hai:**
- Table with all 5 variables: Sensor, Trend, Sen's Slope/Year, MK τ, FDR p, Significant?, Autocorr
- 5 verdict cards (color-coded: green=significant increasing, red=decreasing, gray=no trend)

**Kya bolna hai:**
> "Ye table NASA ke 3 sawaalon ka ek jagah answer hai:"

> "WHAT is changing? LST decreasing hai, NDVI increasing hai. Baaki teen mein koi significant trend nahi."

> "HOW MUCH? LST: −0.173 K per year (10 saal mein ~1.73 K). NDVI: +0.00314 per year."

> "Is it SIGNIFICANT? LST: FDR p=0.003, NDVI: FDR p=0.0000015. Baaki teen: not significant."

> "Notice karo — autocorrelation column. LST ki lag-1 autocorrelation 0.549 hai. Naive Mann-Kendall p-value 4×10⁻⁵ thi. Correction ke baad 0.003. Abhi bhi significant, lekin humne sahi kiya. Agar kisi variable mein significance correction ke baad gayab ho jaye, to wo false positive tha."

**"Explain" button dabao:**
> "AI ko dekho — sirf actual numbers explain karta hai."

### Section B: Single Variable Deep Dive (Q3: How Much)

**Select karo:** "🌡️ Land Surface Temperature"

**Kya dikhata hai:**
- 5 KPI tiles: Direction, Sen's Slope/Year, 95% CI, FDR p, OLS R²
- Significance verdict (green/red/gray box)
- Time series with OLS + Sen's slope trend lines
- Annual mean bar chart (colored vs 2015 baseline)

**Kya bolna hai:**
> "Sen's slope = −0.173 K per year. Sen's slope robust hai — har pair ka slope nikalke median leta hai. OLS ki tarah outlier se shift nahi hota."

> "95% CI = [−0.012, −0.017] per month. Ye interval 0 ko exclude karta hai — matlab trend robustly non-zero hai."

> "OLS R² = 0.53 — linear trend data ke 53% explain karta hai. Baaki 47% seasonal cycle aur noise."

> "Orange dashed = OLS, purple dotted = Sen's slope. Teal = observed values."

### Section C: Where & When (Q2: Anomaly Heatmap)

**Kya dikhata hai:**
- Monthly anomaly heatmap (rows=variables, cols=months, green=above normal, red=below normal)
- Annual anomaly heatmap (year × variable)

**Kya bolna hai:**
> "Ye heatmap dikhata hai KAB aur KAUNSE variables anomalous the. Green = above normal, red = below normal."

> "LST row mein progressively red badh raha hai — temperature below-normal ki taraf. NDVI mein green badh raha hai — vegetation above-normal."

### Section D: Monthly Seasonality

**Kya dikhata hai:**
- Bar chart: 12 months ka climatological mean with error bars

**Kya bolna hai:**
> "Ye typical seasonal cycle hai — 10 saal ka average per calendar month. Iske bina tum har saal 'January thandi, July garam' ko trend samajh loge."

### Concepts explain karne hain
- Modified Mann-Kendall vs naive MK (autocorrelation correction)
- Sen's slope vs OLS (robustness)
- FDR correction (multiple testing)
- 95% CI interpretation
- Deseasonalised anomaly (seasonal cycle removal)
- "Absence of significance is also a finding"

---

## PAGE 5 — Anomaly Intelligence

**File:** `pages/04_Anomaly_Intelligence.py`
**Time:** 2 min

### Is page ka purpose
Ye page NASA ka "WHERE is it changing?" sawaal ka spatial answer deta hai. 13 districts ka choropleth map with precipitation anomaly analysis.

### Kya dikhana hai

1. **4 overview metrics** — districts analysed, scoreable pixels, high anomaly pixels, high anomaly share

2. **Choropleth map** — 13 districts colored by high anomaly %, with district labels, selected district highlighted with white border

3. **District deep dive** — 6 metrics for selected district (anomaly %, pixels, precipitation, robust Z scores)

4. **District ranking table** — all 13 districts sorted by anomaly %

### Kya bolna hai

> "Ab NASA ka doosra sawaal — WHERE is it changing? Ye choropleth map hai. Har district ek color se filled hai. Color ki intensity = kitna % area anomalous tha."

> "Ye August 2025 ka precipitation anomaly hai. Historical baseline August 2015-2024. Har pixel ka robust Z-score calculate kiya — threshold 3.5."

**Map dikhao:**
> "Robust Z-score kya hai? Normal Z-score mean + standard deviation use karta hai — lekin ye outliers se sensitive hai. Robust version median + MAD use karta hai — MAD = Median Absolute Deviation. Extreme events se distort nahi hota."

**Ek district select karo (e.g., Dehradun):**
> "Dehradun ka detail — kitne pixels anomalous the, mean precipitation kitna, max robust Z-score kya tha."

**Ranking table dikhao:**
> "Ye sab 13 districts ka ranking hai — high anomaly percentage ke descending order mein."

**"Explain district anomalies" button dabao:**
> "AI dekho — sirf actual district data explain karta hai. Important caveat: high precipitation anomaly ka matlab flood ya disaster nahi hai. Wo alag cheez hai."

### Concepts explain karne hain
- Choropleth map kya hai
- Robust Z-score vs normal Z-score (median+MAD vs mean+std)
- "High anomaly ≠ disaster" (important caveat)
- District attribution (pixel-center spatial assignment)

---

## PAGE 6 — Interaction Network

**File:** `pages/05_Interaction_Network.py`
**Time:** 2 min

### Is page ka purpose
Ye page variables ke beech ke relationships dikhata hai. Network graph, correlation matrix, aur relationship table. Spearman + FDR + lag-aware analysis.

### Kya dikhana hai

1. **4 overview metrics** — interaction records, FDR significant, variables, lag windows

2. **Filters** — temporal lag selector, significance filter, minimum correlation slider

3. **Network graph** — nodes = variables, edges = Spearman correlations (green=positive, red=negative, width=|ρ|)

4. **Correlation heatmap** — matrix with all pairwise correlations

5. **Relationship table** — all filtered relationships with ρ, p, q-value, significance

6. **Strongest relationship** — KPI tiles for top pair

### Kya bolna hai

> "Individual variables dekhna kaafi nahi hai. Earth system variables ek doosre se connected hain. Temperature badhe to vegetation affect hota hai. Rainfall badhe to soil moisture affect hota hai."

> "Spearman rank correlation use kiya — Pearson nahi. Spearman non-linear but monotonic relationships bhi detect karta hai. Environmental data non-linear hota hai."

> "Lag-aware analysis: lag 0 = same month, lag 1 = X predicts Y 1 month later. Hum lag 0 se 3 test karte hain."

> "FDR correction apply kiya — 70+ relationships test kiye, multiple testing correction zaroori tha."

**Network graph dikhao (Lag=0, FDR significant only):**
> "Green edges = positive correlation. Red = negative. Edge thickness = correlation strength. Dekho — LST aur NDVI connected hain. Soil moisture aur precipitation connected hain."

**"Explain this graph" button dabao:**
> "AI simple language mein batayega ki kaunse variables saath move karte hain."

### Concepts explain karne hain
- Spearman vs Pearson (non-parametric, non-linear)
- Lag-aware correlation (X predicts Y later?)
- FDR correction for 70+ tests
- "Correlation ≠ causation" (important caveat)
- Edge interpretation (positive/negative, strength)

---

## PAGE 7 — Physics & Uncertainty

**File:** `pages/06_Physics_Uncertainty.py`
**Time:** 2 min

### Is page ka purpose
Ye page data quality aur reliability dikhata hai. Satellites perfect data nahi dete — clouds block karte hain, terrain difficult hai. Ye page batata hai ki humare data ka quality kya tha aur findings kitna trustworthy hain.

### Kya dikhana hai

1. **Observation Coverage chart** — 5 variables, monthly coverage % over 10 years

2. **Latest month snapshot** — 5 metric tiles for most recent month coverage

3. **Strict vs Relaxed quality** — grouped bar chart comparing mean coverage

4. **Spatial Validity Map** — pixel-level valid/invalid grid for selected month/sensor

5. **SMAP AM vs PM comparison** — line chart with morning vs evening soil moisture

6. **Data Quality Summary table** — avg/worst/best coverage per sensor

### Kya bolna hai

> "Jo findings humne dikhaye, unki reliability depend karta hai data quality pe. NASA satellites har jagah perfect data nahi de paate. Clouds optical sensors ko block karte hain. Mountains mein terrain difficult hota hai."

**Coverage chart dikhao:**
> "Ye chart dikhata ki har month kitna % area ka valid reading tha. GPM rainfall almost 100% coverage — radar hai, clouds se affect nahi hota. LST aur NDVI mein monsoon months pe drop — MODIS optical sensor, clouds block karte hain."

**Strict vs Relaxed dikhao:**
> "Strict = sirf cleanest readings. Relaxed = more readings, some borderline. Gap zyada ho to borderline readings zyada. Humne strict use kiya."

**SMAP AM vs PM dikhao:**
> "SMAP din mein do baar guarta hai — subah aur shaam. Dono readings compare karne se pata chalta hai consistency. Correlation > 0.99 — matlab very consistent."

**Validity map dikhao:**
> "Ye pixel-level map hai. Green = valid reading, red = no data. Patchy red areas mountains ya clouds ki wajah se."

### Concepts explain karne hain
- Coverage ≠ uncertainty (important distinction)
- Optical vs microwave sensors (clouds block optical only)
- Strict vs relaxed quality (trade-off: quality vs coverage)
- AM vs PM consistency (measurement reliability check)
- "Coverage is not measurement uncertainty"

---

## PAGE 8 — AI Scientist

**File:** `pages/07_AI_Scientist.py`
**Time:** 2 min

### Is page ka purpose
Ye page humara chautha UG-ESI contribution hai — Evidence-Grounded AI Scientist. AI ko actual research data diya gaya hai. Ye sirf data interpret karta hai, invent nahi karta.

### Kya dikhana hai

1. **4 status metrics** — monthly records, districts, interaction records, FDR significant

2. **AI engine status** — model name, configured indicator

3. **Research Knowledge Base** — 3 tabs: Regional Observations, District Anomalies, Environmental Interactions

4. **Quick Questions** — 5 preset question buttons:
   - Regional Environmental Summary
   - District Anomaly Analysis
   - Environmental Interactions
   - Data Quality Assessment
   - Scientific Research Report

5. **Chat interface** — full conversational AI with context

### Kya bolna hai

> "Ye humara chautha contribution — Evidence-Grounded AI Scientist. Isko actual research data diya gaya hai — regional observations, district anomalies, interaction results. Ye sirf us data ko interpret karta hai."

> "AI ke rules strict hain:"
> 1. No invented measurements, trends, or events
> 2. Correlation ≠ causation
> 3. Uncertainty must be explicit
> 4. Distinguish observation from interpretation

**"Scientific Research Report" button dabao:**

AI answer aayega:
> "Dekho — har claim data-backed hai. AI 'Observation → Interpretation → Limitations' structure mein answer deta hai. Ye evidence-grounded reasoning hai."

**Chat mein sawaal puchho:**
> "Type karo: 'Which variables show significant trends and why does autocorrelation correction matter?'"

AI answer:
> "AI sirf actual results use kar raha hai. Naive approach mein AI ko sirf question puchte hain. Humara approach mein AI ko actual statistical results diye hain — wo unhe interpret karta hai. Ye fundamental difference hai."

### Concepts explain karne hain
- Evidence-grounded vs free-form AI (fundamental difference)
- AI rules: no invention, correlation≠causation, uncertainty explicit
- Research context: what data the AI has access to
- "AI explains findings; statistical engines establish them"

---

## 5. GLOSSARY

### Satellites & Sensors

| Term | Simple Meaning |
|---|---|
| MODIS | NASA satellite instrument — surface temperature + vegetation |
| SMAP | NASA satellite — soil moisture (morning + evening) |
| GPM | NASA satellite — precipitation/rainfall |
| LST | Land Surface Temperature — zameen ki surface ka temperature |
| NDVI | Normalized Difference Vegetation Index — kitna green vegetation (0-1) |
| Optical sensor | Light-based sensor (clouds block karte hain) |
| Microwave sensor | Clouds ke through dekh sakta hai (GPM, SMAP) |

### Statistical Methods

| Term | Simple Meaning |
|---|---|
| OLS Linear Regression | Best-fit straight line through data |
| R² | Line data ko kitna % explain karti hai (0-1) |
| Mann-Kendall | Non-parametric monotonic trend test |
| τ (tau) | Mann-Kendall trend strength (−1 to +1) |
| Sen's slope | Robust slope — median of all pairwise slopes |
| Confidence interval | Range jismein true slope 95% probability mein hai |
| Autocorrelation | Is value pichli value pe depend karti hai ya nahi |
| Modified Mann-Kendall | MK + autocorrelation correction (Hamed & Rao 1998) |
| FDR | Multiple testing correction (Benjamini-Hochberg) |
| p-value | Probability ki result random chance se aaya |
| CUSUM | Cumulative sum — structural shifts detect karta hai |
| Spearman correlation | Monotonic relationship between two variables (−1 to +1) |
| Robust Z-score | Outlier-proof anomaly score (median + MAD) |

### Data Concepts

| Term | Simple Meaning |
|---|---|
| Climatology | Long-term average per calendar month |
| Deseasonalised anomaly | Observed minus climatological normal |
| Coverage % | Kitna % area ka valid satellite reading tha |
| Strict quality | Sirf cleanest readings |
| Relaxed quality | More readings, some borderline |
| Choropleth map | Map jisme regions color se data value dikhate hain |
| Pixel | Satellite ka ek grid cell (~9km × 9km) |

### UG-ESI Methodology

| Term | Simple Meaning |
|---|---|
| UG-ESI | Uncertainty-Guided Earth System Intelligence (humari methodology) |
| Adaptive Variable Selection | Variables ko quality + signal pe rank karna (not p-value) |
| Multi-Scale Trend Intelligence | Multiple statistical methods ek saath |
| Uncertainty-Guided Interaction Graph | Relationships with confidence scores |
| Evidence-Grounded AI Scientist | AI jo sirf data explain kare, invent na kare |
| Composite score | Multiple factors combine karke ek ranking |
| Redundancy penalty | Similar variable to score kam |
| Temporal stability | Relationship time windows pe consistent hai ya nahi |
| Edge confidence | |ρ| + certainty + sample size + stability |

---

## 6. DEMO QUICK REFERENCE

| Page | Time | Key Thing To Say |
|---|---|---|
| Home | 1.5 min | "4 contributions, 126 months, 5 variables, LST↓ NDVI↑" |
| UG-ESI Control | 3 min | "Interactive workflow: select→trend→graph→AI report" |
| Earth Observation | 2 min | "Actual satellite data on geographic map with boundaries" |
| Trend Detective | 3 min | "NASA Q1-Q4: autocorrelation-adjusted MK + Sen's slope + FDR" |
| Anomaly Intel | 2 min | "13 districts, robust Z > 3.5, choropleth map" |
| Interaction Net | 2 min | "Spearman + FDR + lag-aware variable relationships" |
| Physics/Uncert | 2 min | "Data quality: strict vs relaxed, AM vs PM, coverage" |
| AI Scientist | 2 min | "Evidence-grounded, AI invent nahi karta" |

**Total: ~17.5 minutes**

---

## 7. JUDGE Q&A

**Q: Sen's slope kyu use kiya, OLS kyu nahi?**
> OLS outliers se sensitive hai — ek extreme month line shift kar deta hai. Sen's slope har pair ka slope nikalke median leta hai — outlier ka effect median pe nahi padta. Environmental data mein outliers common hain (sensor glitches, extreme weather).

**Q: Autocorrelation correction kyu zaroori hai?**
> Monthly data mein serial dependence hoti hai — is month ki value pichle month pe depend karti hai. Standard Mann-Kendall independent observations assume karta hai. LST autocorrelation 0.549 hai — bina correction ke effective sample size 126 se ~50 ho jata hai. False positives milte bina correction ke.

**Q: FDR kyu use kiya?**
> Humne 5 variables test kiye ek saath. Agar 20 tests karo alpha=0.05 pe to 1 guaranteed false positive milega. FDR multiple testing ka problem solve karta hai.

**Q: Correlation causation nahi — to graph kya batata hai?**
> Graph statistical association batata hai, causation nahi. LST aur NDVI correlated hain — lekin ye iska matlab nahi ki temperature vegetation ko cause kar raha. Ho sakta hai dono kisi third factor (season) ke effect hain. Humne explicitly ye limitation mention kiya hai.

**Q: AI kaise reliable hai?**
> AI ko actual statistical results diye hain — wo unhe interpret karta hai. Strict rules: no invented numbers, correlation≠causation, uncertainty explicit. AI kahin bhi apne se measurement ya trend nahi banata.

**Q: 3 variables mein no trend kyu?**
> Soil moisture aur precipitation mein koi significant monotonic trend nahi mila. Ye important finding hai — ye variables 10 saal mein systematically nahi badhe. Cyclic variation ho sakti hai, lekin monotonic trend nahi. Hum sirf significant results nahi dikhate, non-significant bhi dikhate hain — ye scientific honesty hai.

**Q: Ye sirf Uttarakhand ke liye hai?**
> Framework region-agnostic hai. Data change karo to same analysis kisi bhi region pe chal jayega. Uttarakhand ek test case hai — mountainous region jisme multiple climate zones, diverse vegetation, aur monsoon impact hai.

**Q: "Absence of significance" kya matlab?**
> Statistical test mein "not significant" ka matlab ye nahi ki koi change nahi ho raha. Iska matlab ye hai ki humare data mein evidence insufficient hai ki ek systematic monotonic trend exist karti hai. Ho sakta hai variation cyclic hai, ya trend bahut slow hai, ya data mein noise zyada hai. Ye nuance important hai — hum "no trend detected" bolte hain, "no change" nahi.

# EARTHPULSE-X — 7-slide presentation content

**Exactly 7 slides.** Copy the **Slide text** onto the slide; use the Hinglish **Presenter script** as speaker notes. Follow the visual instructions to keep the deck image-led and readable.

---

## Slide 1 — EARTHPULSE-X

### Slide text

# EARTHPULSE-X
## Be an Earth System Trend Detective
### Uttarakhand, India · April 2015–September 2025

**5 satellite signals** · **126 monthly observations** · **664 study-area grid cells**

NASA Space Apps Challenge

### Visuals

- Full-slide `assets/AERIAL.jpg` with a dark overlay; large project title on the left.
- Uttarakhand outline/map on the right with a small satellite icon.
- Along the bottom, five compact icons: LST, NDVI, SMAP AM, SMAP PM, GPM.
- Add `assets/Space_Apps_2026_Logo_OG.jpg` as a small corner logo.

### Presenter script

“Namaste judges. EARTHPULSE-X ek Earth System Trend Detective hai. Humne Uttarakhand ke 10 saal ke satellite observations ko use karke investigate kiya hai ki environment mein kya badal raha hai, kab aur kahan badal raha hai, aur us change ka evidence kitna reliable hai.”

---

## Slide 2 — The challenge and our data

### Slide text

# Four questions. Five satellite signals.

**WHAT is changing? · WHEN? · WHERE? · HOW strong is the evidence?**

| NASA product | Signal | Native cadence |
|---|---|---|
| MODIS Terra · MOD11A2.061 | Land-surface temperature (LST) | 8-day |
| MODIS Terra · MOD13Q1.061 | Vegetation greenness (NDVI) | 16-day |
| SMAP · SPL3SMP_E.006 | Soil moisture AM + PM | Daily product |
| GPM IMERG Final · V07 | Precipitation | Daily granules |

**Different satellite schedules → one 126-month timeline**

### Visuals

- Place a Uttarakhand map in the center and the four question words around it.
- Add four product cards across the bottom with product name, icon, and unit.
- Show a small daily/8-day/16-day calendar strip flowing into “monthly.”
- Label units: **K · NDVI index · m³/m³ · mm/month**.

### Presenter script

“NASA challenge ne hume Earth-system trends ko identify karne ko kaha. Humne Uttarakhand ko pilot region banaya aur temperature, vegetation, soil moisture aur precipitation signals choose kiye. Product schedules alag the, isliye pehle sab observations ko monthly timeline par lana zaroori tha.”

---

## Slide 3 — From NASA files to a reliable map

### Slide text

# Harmonize first. Compare second.

**Discover → Extract → QA-filter → Monthly aggregate → Reproject → Boundary-mask**

- **Study area:** Uttarakhand boundary
- **Common grid:** EPSG:6933 · approximately 9 km × 9 km
- **Grid cells inside boundary:** 664
- **Monthly files:** 126 · April 2015–September 2025

### Coverage is part of the result

| Signal | Strict | Relaxed |
|---|---:|---:|
| LST | 99.64% | 99.99% |
| NDVI | 92.72% | 99.96% |
| SMAP AM | 4.31% | 85.98% |
| SMAP PM | 4.32% | 88.61% |

### Visuals

- Left: a 6-step pipeline with archive, shield, calendar, grid, boundary, and chart icons.
- Right: actual Uttarakhand satellite-grid/validity map from the Earth Observation page.
- Bottom: compact grouped coverage bars (strict vs relaxed); highlight limited strict-SMAP coverage in amber.
- Add a clear note: **“Common analysis grid ≠ equal native sensor resolution.”**

### Presenter script

“Raw satellite values ko directly compare nahi kiya. Humne quality layers apply ki, observations ko month-wise aggregate kiya, phir EPSG:6933 equal-area grid par reproject karke Uttarakhand boundary mask lagaya. Coverage chart ek important limitation bhi dikhata hai: strict SMAP filtering mein valid area bahut kam hai, isliye quality mode ko result ke saath show karte hain.”

---

## Slide 4 — What is changing over the decade?

### Slide text

# Two regional trends pass adjusted evidence checks

### LST ↓ Decreasing
**−0.173 K/year**  ·  Modified Mann–Kendall FDR q = **0.00284**

### NDVI ↑ Increasing
**+0.00314 index/year**  ·  Modified Mann–Kendall FDR q = **0.00000150**

### No reliable monotonic trend detected
**SMAP AM · SMAP PM · GPM precipitation**

*126 monthly observations · q < 0.05 threshold*

### Visuals

- Two large time-series charts: LST and NDVI, each with observed line, Sen trend line, units, and dates.
- Beneath them, three smaller neutral cards for SMAP AM, SMAP PM, and GPM.
- Use clear up/down arrows and q-value badges; avoid one shared axis for unlike units.
- Optional right-side inset: crop of `assets/what-is-changing-chart.png` if its labels remain readable.

### Presenter script

“Regional analysis mein LST ka Sen slope minus 0.173 Kelvin per year aur NDVI ka plus 0.00314 index per year hai. Modified Mann–Kendall aur multiple-testing FDR adjustment ke baad dono threshold pass karte hain. Baaki teen signals mein reliable monotonic trend detect nahi hua. Yeh poore region ka summary hai; har district ka trend same ho, yeh zaroori nahi.”

---

## Slide 5 — Where and when are unusual signals?

### Slide text

# Anomaly = unusual for this time of year

1. Compare a month with the **same calendar month** in past years.
2. Measure distance from the historical median using MAD.
3. Flag a statistical candidate when **|robust z| ≥ 3.5**.

```text
robust z = 0.6745 × (observed − historical median) / MAD
```

**Candidate signal ≠ confirmed disaster report**

### Visuals

- Main: a project pixel/district anomaly map with readable legend and selected month.
- Small side chart: historical monthly series with the selected unusual point highlighted.
- Show the method as a 3-step visual: calendar comparison → robust score → map candidate.
- Add denominator/coverage beside the map: valid pixels or grid cells for that month.

### Presenter script

“Seasonality ko account karne ke liye June ko historical Junes se compare karte hain, January ko Januaries se. Median aur MAD robust baseline dete hain. Robust z-score 3.5 se zyada ya minus 3.5 se kam ho toh system us pixel-month ko candidate mark karta hai. Iska matlab statistical unusualness hai, confirmed flood ya official warning nahi.”

---

## Slide 6 — Do signals move together? Haldwani → Rudrapur

### Slide text

# A nearby unusual reading does not prove a repeating link

**Haldwani · LST · Dec 2019**  
−1.05σ from its usual December level

→ **Rudrapur · rainfall · Jan 2020**  
+1.58σ from its usual January level

### Historical one-month association
**ρ = −0.08 · 125 paired months · very weak**

**No clear repeating relationship for this selected signal pair.**

### Visuals

- Left: Haldwani–Rudrapur map with markers and 15 km analysis circles.
- Center: two anomaly bars for Dec 2019 and Jan 2020 with an arrow between them.
- Right: rho gauge from −1 to +1, marker near zero.
- Show valid grid-cell counts; keep the sparse-cell warning visible if a town has fewer than 3 cells.
- Add a small, simplified interaction network inset with three example links and the badge **20/70 FDR-significant tests**.

### Presenter script

“Local comparison mein Haldwani ka December temperature usual se 1.05 sigma neeche tha aur agle mahine Rudrapur rainfall 1.58 sigma upar thi. Lekin 125 historical month-pairs ka rho minus 0.08 hai—bahut weak association. Isliye do unusual readings dikhne ke bawajood hum causal impact claim nahi karte. Regional interaction graph bhi co-movement dikhata hai, cause nahi.”

---

## Slide 7 — The product, the value, and what comes next

### Slide text

# EARTHPULSE-X makes satellite evidence explorable

**OBSERVE** · Maps and data coverage  
**DETECT** · Trends and anomaly candidates  
**COMPARE** · Districts, variables, and time lags  
**EXPLAIN** · Methods, uncertainty, and plain-language AI

### Built
**126 months · 5 signals · common Uttarakhand grid · interactive investigation pages**

### Next
**Ground validation · event-based evaluation · stronger local coverage · better-tested forecasts**

*Statistics calculate the evidence. Llama explains the displayed values; it does not prove causation.*

### Visuals

- Across the top, a 4-step icon journey: Observe → Detect → Compare → Explain.
- Below it, use 3 large cropped screenshots: Earth Observation, Trend Detective, and Interaction Network/Haldwani study.
- On the right, show a “Next” roadmap with three milestones.
- End with a clear line: **“Turn satellite change into evidence people can investigate.”**

### Presenter script

“Website user ko observation se investigation tak le jaati hai: pehle map aur coverage, phir trends aur anomalies, phir districts aur signal relationships. AI guide numbers ko simple Hinglish mein explain karta hai; calculations data pipeline karti hai. Ab next step ground reports se validation, event-based testing aur local spatial coverage improve karna hai. EARTHPULSE-X ka goal satellite change ko transparent aur investigable banana hai. Thank you.”

---

## 7-slide visual checklist

- **Slide 1:** aerial background + state outline + five signal icons + project mark.
- **Slide 2:** four challenge question cards + product/satellite cards + cadence strip.
- **Slide 3:** processing pipeline + grid/validity map + strict/relaxed coverage bars.
- **Slide 4:** two time-series charts + three “no reliable trend” cards.
- **Slide 5:** anomaly map + time-series point + 3-step robust-z visual.
- **Slide 6:** two-place map + anomaly comparison + rho gauge + tiny interaction graph.
- **Slide 7:** product screenshots + workflow arrows + next-step roadmap.

### Design rules

- Use the visual suggestions as the slide’s main content; keep paragraphs in speaker notes.
- Put units, date range, denominator/coverage and legend on every chart/map.
- Use teal/green for positive, coral for negative, amber for caveats, gray for missing/not significant; add labels as well as colors.
- Never stretch map screenshots or put unlike raw units on one shared axis.
- Use real project screenshots and maps; don’t use generated imagery that could be mistaken for satellite observations.
- Keep caveats visible: **association ≠ causation**, **anomaly candidate ≠ confirmed event**, **shared grid ≠ native resolution**.

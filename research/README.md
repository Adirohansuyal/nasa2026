# Uttarakhand land-cover research

This folder contains a Streamlit dashboard for district-wise land-cover distribution and annual trends. The 2021 ESA WorldCover result remains a separate 10 m snapshot. The requested 2015–2025 series uses the nine Dynamic World V1 classes: water, tree cover, grassland, flooded vegetation, cropland, shrubland, built-up, bare/sparse vegetation, and snow/ice.

## Run the dashboard

From the repository root:

```bash
research/.venv/bin/streamlit run research/app.py
```

The **Land-cover distribution** page has a year selector for the annual Dynamic World distribution and vertical class bars labeled with hectares and the share of total district area. The **District trends** page compares all classes per district and statewide, shows annual class series, and ranks each district's largest estimated increase and decrease. Its map timeline renders the selected year's Dynamic World class mode inside the selected district; change the year and class to compare, for example, built-up pixels in Udham Singh Nagar.

The map timeline queries Earth Engine when a new district/class is selected and provides a play/pause control across 2015–2025. Each year compares the annual modal class mask with the prior year: persistent class pixels keep the class color, new pixels are green, and pixels that left the class are blue. Frames cross-fade after the incoming map tiles load. The ha figure and net annual difference use the 500 m CSV estimates. It needs the same locally authenticated Earth Engine account and network access as the annual data script. The map itself renders native Dynamic World map tiles clipped to the selected GAUL district boundary over an attributed OpenStreetMap basemap. 2015 is partial.

## Generate annual land-cover data and trends

Use the locally authenticated Earth Engine account. From the repository root:

```bash
research/.venv/bin/python research/dynamic_world_analysis.py
```

The script checks the 13 Uttarakhand district boundaries in `FAO/GAUL/2025/level2`, samples annual Dynamic World label modes, and saves:

- `outputs/uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv` — one row per district/year/class, including an Uttarakhand-wide aggregate.
- `outputs/uttarakhand_dynamic_world_class_trends_2016_2025.csv` — Sen slope, Kendall trend test, FDR-adjusted q-value, direction, and coverage by class and district/state.
- `outputs/uttarakhand_dynamic_world_trend_highlights_2016_2025.csv` — largest area increase and decrease for each district and statewide.

Annual processing is sequential to limit Earth Engine aggregation pressure. Class fractions are estimated from the annual modal label on a 500 m grid and multiplied by district area; they are regional estimates, not exact 10 m pixel counts. 2015 is partial because Dynamic World begins on 27 June 2015. Trend estimates use the ten full years 2016–2025. Statewide area and percentage are calculated from summed district areas, not by averaging district percentages.

The trend page labels the largest positive and negative slopes for all classes, but calls a trend statistically supported only when the Kendall test passes a false-discovery correction (q < 0.05). A non-significant result means the data do not provide clear evidence of a monotonic change; it does not establish no change.

## 2021 ESA WorldCover snapshot

To recreate the 2021 baseline:

```bash
research/.venv/bin/python research/landcover_analysis.py
```

It writes `outputs/uttarakhand_worldcover_2021_districtwise.csv` and `outputs/uttarakhand_worldcover_2021_wide.csv`. ESA WorldCover's `tree_cover` category is a land-cover classification, not an official forest boundary or proof of forest recovery. It is a single year and cannot be used to infer the 2015–2025 trend.

## Source and interpretation

### Data provenance

The 2015–2025 class series was queried from the Google Earth Engine image collection **`GOOGLE/DYNAMICWORLD/V1`** by `dynamic_world_analysis.py`; it was not sourced from the older NDVI-attribution CSV or from the 2021 WorldCover CSV.

**Satellite source:** Dynamic World classifies optical imagery from the **Copernicus Sentinel-2 mission**, whose satellites are operated by the European Space Agency (ESA) for the European Union's Copernicus programme. It is **not NASA satellite data**. The 2015–2025 inputs are Sentinel-2 Level-1C scenes (Sentinel-2A, 2B, and, in the later period, 2C). Sentinel-2 provides multispectral imagery; Dynamic World applies a trained deep-learning land-cover classifier to each scene.

**Classification and annual calculation:** Dynamic World is produced by Google in partnership with the World Resources Institute and National Geographic Society. For each Sentinel-2 scene, the model gives estimated probabilities for nine classes—water, trees, grass, flooded vegetation, crops, shrub/scrub, built-up, bare ground, and snow/ice—and a label for the class with the highest probability. The workflow groups the available scene labels by calendar year, takes their per-pixel mode, then estimates district class fractions from samples on a 500 m grid. This produces approximate district area estimates, not a new 10 m NASA map. The source is available from **27 June 2015** onward, so 2015 is partial.

District boundaries come from **`FAO/GAUL/2025/level2`** in Earth Engine, filtered to India and Uttarakhand; the script confirms 13 districts. The annual CSV includes those district estimates plus a statewide row aggregated from the districts. Because 2015 begins partway through the year, it is displayed as a partial observation and excluded from the 2016–2025 trend calculations.

Primary source links: [Dynamic World V1 catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) · [ESA Sentinel-2 mission](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2) · [FAO GAUL 2025 level-2 boundaries](https://developers.google.com/earth-engine/datasets/catalog/FAO_GAUL_2025_level2) · [Dynamic World paper](https://doi.org/10.1038/s41597-022-01307-4).

**Attribution:** Dynamic World is produced for the Dynamic World Project by Google in partnership with National Geographic Society and the World Resources Institute. The dataset is licensed CC BY 4.0. GAUL boundaries are provided by FAO under CC BY 4.0; refer to each linked catalog entry for the exact license terms and attribution.

Dynamic World provides source predictions at 10 m; this workflow uses the annual mode of its hard labels to keep the class definitions interpretable and aggregates on a 500 m grid to make district-scale computation practical. Annual label modes can still vary with observation timing, clouds, and seasonal coverage. The resulting hectare values are approximate district-level estimates, not exact 10 m pixel counts. NASA products such as MODIS or VIIRS are not inputs to this CSV; using them would be a separate analysis with different sensors and spatial resolution.

The GADM level-2 boundary file is downloaded on demand by the 2021 WorldCover script and is not committed. GADM makes its data available for academic and other non-commercial use; consult its terms before other uses or redistribution.

// Attribute long-term positive NDVI trends to Dynamic World cover classes
// across Uttarakhand. Run in the Earth Engine Code Editor and start the CSV
// export from the Tasks tab.
// Period: 2015–2025. Sentinel-2 begins in June 2015, so pre-monsoon starts 2016.

var roi = ee.Geometry.Rectangle([77.45, 28.55, 81.1, 31.5], null, false);
var districts = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL0_NAME', 'India'))
  .filter(ee.Filter.eq('GAUL1_NAME', 'Uttarakhand'))
  .filterBounds(roi);

var seasons = [
  {name: 'pre_monsoon', startMonth: 4, endMonth: 6, firstYear: 2016},
  {name: 'monsoon', startMonth: 7, endMonth: 10, firstYear: 2015},
  {name: 'post_monsoon', startMonth: 10, endMonth: 12, firstYear: 2015}
];
var classes = [
  {name: 'tree_cover', label: 1},
  {name: 'grass', label: 2},
  {name: 'shrub_scrub', label: 5}
];
var probabilityBands = [
  'water', 'trees', 'grass', 'flooded_vegetation', 'crops',
  'shrub_and_scrub', 'built', 'bare', 'snow_and_ice'
];
var probabilityTypes = {};
probabilityBands.forEach(function(band) { probabilityTypes[band] = 'float'; });
var confidenceThreshold = 0.60;
var analysisScale = 100;
var analysisCrs = 'EPSG:6933';
var cloudScore = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');

print('District count (expected 13):', districts.size());
print('District names:', districts.aggregate_array('GAUL2_NAME').sort());
Map.centerObject(districts, 7);
Map.addLayer(districts.style({color: 'ffffff', fillColor: '00000000', width: 1}), {}, 'District boundaries');

function resampleToGrid(image, reducer, targetScale, sourceProjection) {
  return image
    // Collection composites can inherit a placeholder WGS84/1-degree grid.
    // Restore the source image's real projection before reduceResolution.
    .setDefaultProjection(sourceProjection)
    .reduceResolution({
      reducer: reducer,
      maxPixels: 256,
      bestEffort: true
    })
    // Set a valid Projection object for downstream requests without forcing
    // reprojection during map rendering.
    .setDefaultProjection(ee.Projection(analysisCrs).atScale(targetScale))
    .clip(roi);
}

function clearNdvi(image) {
  return image.updateMask(image.select('cs_cdf').gte(0.60))
    .normalizedDifference(['B8', 'B4']).rename('ndvi')
    .cast({ndvi: 'float'})
    .copyProperties(image, ['system:time_start']);
}

function seasonalNdvi(year, season) {
  var start = ee.Date.fromYMD(year, season.startMonth, 1);
  var end = ee.Date.fromYMD(year, season.endMonth, 1);
  var emptyNdvi = ee.Image.constant(0).rename('ndvi').cast({ndvi: 'float'})
    .updateMask(ee.Image.constant(0)).clip(roi);
  var sourceScenes = ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
    .filterBounds(roi).filterDate(start, end)
    .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 80))
    .linkCollection(cloudScore, ['cs_cdf']);
  var sourceProjection = ee.Image(sourceScenes.first()).select('B8').projection();
  var scenes = sourceScenes.map(clearNdvi);
  var medianNdvi = scenes.merge(ee.ImageCollection.fromImages([emptyNdvi]))
    .median().rename('ndvi');
  return resampleToGrid(medianNdvi, ee.Reducer.mean(), analysisScale, sourceProjection);
}

function annualNdviCollection(season) {
  var yearList = ee.List.sequence(season.firstYear, 2025);
  return ee.ImageCollection.fromImages(yearList.map(function(year) {
    year = ee.Number(year);
    var ndvi = seasonalNdvi(year, season);
    var yearBand = ee.Image.constant(year).rename('year').cast({year: 'float'})
      .setDefaultProjection(ndvi.projection());
    return ndvi.addBands(yearBand);
  }));
}

function periodCover(season) {
  var start = ee.Date.fromYMD(season.firstYear, season.startMonth, 1);
  var end = ee.Date.fromYMD(2026, 1, 1);

  var baseCol = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
    .filterBounds(roi)
    .filterDate(start, end)
    .filter(ee.Filter.calendarRange(season.startMonth, season.endMonth - 1, 'month'));
  var sourceProjection = ee.Image(baseCol.first()).select('label').projection();

  var rawProbabilities = baseCol.select(probabilityBands)
    .map(function(img) { return img.cast(probabilityTypes); })
    .median();
  var analysisProbabilities = resampleToGrid(
    rawProbabilities, ee.Reducer.mean(), analysisScale, sourceProjection
  );
  var label = analysisProbabilities.toArray().arrayArgmax()
    .arrayGet([0]).rename('label').toByte();
  var confidence = analysisProbabilities.reduce(ee.Reducer.max())
    .rename('confidence').toFloat();

  return {label: label, confidence: confidence};
}

var seasonalProducts = {};
var seasonalCovers = {};
seasons.forEach(function(season) {
  var annual = annualNdviCollection(season);
  seasonalProducts[season.name] = {
    meanNdvi: annual.select('ndvi').mean().rename('ndvi').clip(roi),
    slope: annual.select(['year', 'ndvi']).reduce(ee.Reducer.linearFit())
      .select('scale').rename('ndvi_slope').clip(roi)
  };
  seasonalCovers[season.name] = periodCover(season);
});

var seasonRows = seasons.map(function(season) {
  var cover = seasonalCovers[season.name];
  var confident = cover.confidence.gte(confidenceThreshold);
  var ndvi = seasonalProducts[season.name].meanNdvi;
  var slope = seasonalProducts[season.name].slope;
  var pixelArea = ee.Image.pixelArea();

  var metricImages = classes.map(function(coverClass) {
    var prefix = coverClass.name;
    var classMask = cover.label.eq(coverClass.label).and(confident);
    var validNdviClass = classMask.and(ndvi.mask());
    var greeningMask = classMask.and(slope.gt(0));
    var ndviArea = ndvi.multiply(pixelArea).updateMask(validNdviClass)
      .unmask(0).rename(prefix + '_ndvi_area_sum');
    var validNdviArea = pixelArea.updateMask(validNdviClass)
      .unmask(0).rename(prefix + '_valid_ndvi_area_m2');
    var classArea = pixelArea.updateMask(classMask)
      .unmask(0).rename(prefix + '_class_area_m2');
    var greeningArea = pixelArea.updateMask(greeningMask)
      .unmask(0).rename(prefix + '_greening_area_m2');
    return ndviArea.addBands(validNdviArea).addBands(classArea).addBands(greeningArea);
  });

  var districtSummary = ee.Image.cat(metricImages).reduceRegions({
    collection: districts,
    reducer: ee.Reducer.sum(),
    crs: analysisCrs,
    scale: analysisScale,
    tileScale: 16,
    maxPixelsPerRegion: 100000000
  });

  var classRows = classes.map(function(coverClass) {
    return districtSummary.map(function(district) {
      var prefix = coverClass.name;
      var validNdviArea = ee.Number(district.get(prefix + '_valid_ndvi_area_m2'));
      var classArea = ee.Number(district.get(prefix + '_class_area_m2'));
      var greeningArea = ee.Number(district.get(prefix + '_greening_area_m2'));
      var ndviArea = ee.Number(district.get(prefix + '_ndvi_area_sum'));
      var districtArea = district.geometry().area(1);
      return ee.Feature(district.geometry(), {
        GAUL2_NAME: district.get('GAUL2_NAME'),
        season: season.name,
        cover_class: prefix,
        analysis_period: '2015–2025',
        ndvi_trend_period: season.firstYear + '–2025',
        mean_ndvi: ndviArea.divide(validNdviArea.max(1)),
        class_area_ha: classArea.divide(10000),
        positive_ndvi_trend_area_ha: greeningArea.divide(10000),
        positive_trend_share_of_class_pct: greeningArea.divide(classArea.max(1)).multiply(100),
        positive_trend_share_of_district_pct: greeningArea.divide(districtArea).multiply(100),
        land_cover_source: 'Dynamic World V1; seasonal median class probabilities & top median probability >= 0.60',
        district_summary_scale_m: analysisScale
      });
    });
  });
  return ee.FeatureCollection(classRows).flatten();
});

var rows = ee.FeatureCollection(seasonRows).flatten();
print('Analysis ready: 2015–2025 seasonal trend summaries; start the CSV export from Tasks.');

// Fast map preview using native Dynamic World label mode without reduceResolution overhead.
var quickMonsoonLabel = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
  .filterBounds(roi)
  .filterDate('2024-07-01', '2025-10-01')
  .filter(ee.Filter.calendarRange(7, 9, 'month'))
  .select('label')
  .mode()
  .clip(roi);

Map.addLayer(quickMonsoonLabel, {
  min: 0, max: 8,
  palette: ['419bdf', '397d49', '88b053', '7a87c6', 'e49635', 'dfc35a', 'c4281b', 'a59b8f', 'b39fe1']
}, 'Dynamic World monsoon preview (2024–2025)');
Map.addLayer(seasonalCovers[seasons[1].name].confidence, {
  min: 0, max: 1, palette: ['8c2d04', 'fdbb84', '2ca25f']
}, 'Class confidence · monsoon composite', false);
Map.addLayer(seasonalProducts[seasons[1].name].slope, {
  min: -0.02, max: 0.02, palette: ['b2182b', 'f7f7f7', '1a9850']
}, 'Monsoon NDVI trend per year · 2015–2025', false);

Export.table.toDrive({
  collection: rows,
  description: 'Uttarakhand_tree_grass_shrub_NDVI_greening_2015_2025_revised',
  fileNamePrefix: 'uttarakhand_tree_grass_shrub_ndvi_greening_2015_2025_revised',
  fileFormat: 'CSV'
});

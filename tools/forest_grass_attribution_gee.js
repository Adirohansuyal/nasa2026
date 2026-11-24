// Identify which Dynamic World cover classes occur in long-term NDVI-greening
// pixels in Uttarakhand. Run in https://code.earthengine.google.com/ and start
// the CSV export from the Tasks tab.
//
// This is a screening analysis: Dynamic World's "trees" class is not a legal
// forest map, and shrub/grass classes can be confused in steep terrain.

var roi = ee.Geometry.Rectangle([77.45, 28.55, 81.1, 31.5], null, false);
var districts = ee.FeatureCollection('FAO/GAUL/2025/level2')
  .filter(ee.Filter.eq('GAUL0_NAME', 'India'))
  .filter(ee.Filter.eq('GAUL1_NAME', 'Uttarakhand'))
  .filterBounds(roi);

var years = ee.List.sequence(2016, 2024);
var yearsClient = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
var seasons = [
  {name: 'pre_monsoon', startMonth: 4, endMonth: 6},  // April–May
  {name: 'monsoon', startMonth: 7, endMonth: 10},     // July–September
  {name: 'post_monsoon', startMonth: 10, endMonth: 12} // October–November
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
var confidenceThreshold = 0.60;

print('District count (expected 13):', districts.size());
print('District names:', districts.aggregate_array('GAUL2_NAME').sort());
Map.centerObject(roi, 7);
Map.addLayer(districts.style({color: 'ffffff', fillColor: '00000000', width: 1}), {}, 'District boundaries');

function clearNdvi(image) {
  var scl = image.select('SCL');
  var clear = scl.neq(1).and(scl.neq(3)).and(scl.neq(8))
    .and(scl.neq(9)).and(scl.neq(10)).and(scl.neq(11));
  return image.updateMask(clear)
    .normalizedDifference(['B8', 'B4']).rename('ndvi')
    .copyProperties(image, ['system:time_start']);
}

function seasonalNdvi(year, season) {
  var start = ee.Date.fromYMD(year, season.startMonth, 1);
  var end = ee.Date.fromYMD(year, season.endMonth, 1);
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(roi).filterDate(start, end)
    .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 80))
    .map(clearNdvi).median().rename('ndvi').clip(roi);
}

function seasonTrend(season) {
  var annualImages = ee.ImageCollection.fromImages(years.map(function(y) {
    y = ee.Number(y);
    return seasonalNdvi(y, season)
      .addBands(ee.Image.constant(y).rename('year').toFloat());
  }));
  // Linear NDVI change per year. Positive slope marks greening pixels.
  return annualImages.select(['year', 'ndvi']).reduce(ee.Reducer.linearFit())
    .select('scale').rename('ndvi_slope').clip(roi);
}

function seasonalCover(year, season) {
  var start = ee.Date.fromYMD(year, season.startMonth, 1);
  var end = ee.Date.fromYMD(year, season.endMonth, 1);
  var probabilities = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
    .filterBounds(roi).filterDate(start, end)
    .select(probabilityBands).median().clip(roi);
  var label = probabilities.toArray().arrayArgmax().arrayGet([0]).rename('label');
  var confidence = probabilities.reduce(ee.Reducer.max()).rename('confidence');
  return {label: label, confidence: confidence};
}

var rows = ee.FeatureCollection(seasons.map(function(season) {
  var slope = seasonTrend(season);
  var yearlyClassRows = yearsClient.map(function(year) {
    var cover = seasonalCover(year, season);
    var confident = cover.confidence.gte(confidenceThreshold);
    var ndvi = seasonalNdvi(year, season);

    var classRows = classes.map(function(coverClass) {
      var classMask = cover.label.eq(coverClass.label).and(confident);
      var greeningMask = classMask.and(slope.gt(0));
      var meanNdvi = ndvi.updateMask(classMask).rename('ndvi');
      var areaBands = ee.Image.pixelArea().updateMask(classMask).rename('class_area_m2')
        .addBands(ee.Image.pixelArea().updateMask(greeningMask).rename('greening_area_m2'));
      var meanRows = meanNdvi.reduceRegions({
        collection: districts, reducer: ee.Reducer.mean(), scale: 10, tileScale: 4
      });
      var areaRows = areaBands.reduceRegions({
        collection: districts, reducer: ee.Reducer.sum(), scale: 10, tileScale: 4
      });
      var joined = ee.Join.saveFirst('area_feature').apply(
        meanRows,
        areaRows,
        ee.Filter.equals({leftField: 'GAUL2_NAME', rightField: 'GAUL2_NAME'})
      );

      return ee.FeatureCollection(joined).map(function(feature) {
        var areaFeature = ee.Feature(feature.get('area_feature'));
        var classAreaValue = areaFeature.get('class_area_m2');
        var greeningAreaValue = areaFeature.get('greening_area_m2');
        var classArea = ee.Number(ee.Algorithms.If(classAreaValue, classAreaValue, 0));
        var greeningArea = ee.Number(ee.Algorithms.If(greeningAreaValue, greeningAreaValue, 0));
        var districtArea = feature.geometry().area(1);
        return feature.set({
          year: year,
          season: season.name,
          cover_class: coverClass.name,
          mean_ndvi: feature.get('ndvi'),
          class_area_ha: classArea.divide(10000),
          positive_ndvi_trend_area_ha: greeningArea.divide(10000),
          positive_trend_share_of_class_pct: greeningArea.divide(classArea.max(1)).multiply(100),
          positive_trend_share_of_district_pct: greeningArea.divide(districtArea).multiply(100),
          ndvi_slope_method: 'OLS linear fit of annual seasonal Sentinel-2 NDVI, 2016-2024',
          land_cover_source: 'Dynamic World V1; top-class probability >= 0.60'
        }).select([
          'GAUL2_NAME', 'year', 'season', 'cover_class', 'mean_ndvi',
          'class_area_ha', 'positive_ndvi_trend_area_ha',
          'positive_trend_share_of_class_pct', 'positive_trend_share_of_district_pct',
          'ndvi_slope_method', 'land_cover_source'
        ]);
      });
    });
    return ee.FeatureCollection(classRows).flatten();
  });
  return ee.FeatureCollection(yearlyClassRows).flatten();
})).flatten();

print('Sample district × season × cover rows:', rows.limit(12));
var latestCover = seasonalCover(2024, seasons[1]);
Map.addLayer(latestCover.label, {
  min: 0, max: 8,
  palette: ['419bdf', '397d49', '88b053', '7a87c6', 'e49635', 'dfc35a', 'c4281b', 'a59b8f', 'b39fe1']
}, 'Dynamic World classes · 2024 monsoon');
Map.addLayer(latestCover.confidence, {
  min: 0, max: 1, palette: ['8c2d04', 'fdbb84', '2ca25f']
}, 'Class confidence · 2024 monsoon', false);
Map.addLayer(seasonTrend(seasons[1]), {
  min: -0.02, max: 0.02, palette: ['b2182b', 'f7f7f7', '1a9850']
}, 'Monsoon NDVI trend per year · 2016–2024', false);

Export.table.toDrive({
  collection: rows,
  description: 'Uttarakhand_tree_grass_shrub_NDVI_greening_2016_2024',
  fileNamePrefix: 'uttarakhand_tree_grass_shrub_ndvi_greening_2016_2024',
  fileFormat: 'CSV'
});

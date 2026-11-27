"""Shared NASA MERRA-2 variable metadata and data-quality notes."""

GRID = {"nlat": 361, "nlon": 576, "lat0": -90, "lon0": -180, "dlat": 0.5, "dlon": 0.625}

# id, collection, display unit, source unit, multiplier, offset, pack scale,
# decimals, land-only, EN/TR name, EN/TR description
VARS = [
    ("T2M", "M2TMNXSLV", "°C", "K", 1, -273.15, 0.01, 1, False,
     ("Air temperature", "Hava sıcaklığı"),
     ("Air temperature 2 meters above the ground.", "Yerden 2 metre yükseklikteki hava sıcaklığı.")),
    ("QV2M", "M2TMNXSLV", "g/kg", "kg/kg", 1000, 0, 0.001, 2, False,
     ("Humidity", "Nem"),
     ("How much water vapour the air holds (grams of water per kg of air).",
      "Havanın taşıdığı su buharı miktarı (1 kg havadaki gram su).")),
    ("SPEED", "M2TMNXFLX", "m/s", "m/s", 1, 0, 0.001, 2, False,
     ("Wind speed", "Rüzgâr hızı"),
     ("Average wind speed near the surface.", "Yüzeye yakın ortalama rüzgâr hızı.")),
    ("PRECTOT", "M2TMNXFLX", "mm/day", "kg m-2 s-1", 86400, 0, 0.01, 2, False,
     ("Precipitation", "Yağış"),
     ("Rain and snow that falls, as millimetres of water per day.",
      "Yağmur ve kar olarak düşen su, günde milimetre olarak.")),
    ("EVAP", "M2TMNXFLX", "mm/day", "kg m-2 s-1", 86400, 0, 0.001, 2, False,
     ("Evaporation", "Buharlaşma"),
     ("Water that goes from the surface into the air, mm per day.",
      "Yüzeyden havaya geçen su, günde milimetre.")),
    ("GWETROOT", "M2TMNXLND", "%", "1", 100, 0, 0.01, 1, True,
     ("Soil moisture", "Toprak nemi"),
     ("How wet the soil is where plant roots are, from the driest this soil gets to fully soaked. "
      "Even deserts stay around 30%, so compare places by their change, not their level.",
      "Bitki köklerinin olduğu toprağın ıslaklığı: o toprağın en kuru halinden tamamen doygun haline kadar. "
      "Çöller bile %30 civarında kalır; yerleri seviyesiyle değil değişimiyle karşılaştır.")),
    ("RUNOFF", "M2TMNXLND", "mm/day", "kg m-2 s-1", 86400, 0, 0.02, 2, True,
     ("Surface runoff", "Yüzey akışı"),
     ("Water that flows over the ground instead of soaking in, mm per day.",
      "Toprağa sızmadan yüzeyden akıp giden su, günde milimetre.")),
    ("SNOMAS", "M2TMNXLND", "mm", "kg m-2", 1, 0, 0.5, 0, True,
     ("Snow amount", "Kar miktarı"),
     ("Snow on the ground, as the millimetres of water it would make if melted.",
      "Yerdeki kar; eriseydi kaç milimetre su olacağı olarak.")),
    ("TOTEXTTAU", "M2TMNXAER", "AOD", "1", 1, 0, 0.0005, 3, False,
     ("Aerosols (haze)", "Aerosol (pus)"),
     ("How much dust, smoke and haze block sunlight (aerosol optical depth, no unit).",
      "Toz, duman ve pusun güneş ışığını ne kadar engellediği (aerosol optik derinliği, birimsiz).")),
]

CAVEAT = {
    "PRECTOT": ("Reanalysis precipitation can jump when satellite observations change.",
                "Reanaliz yağış verisi, uydu gözlemleri değiştiğinde sıçrama yapabilir."),
    "TOTEXTTAU": ("Aerosol data can jump in years when new satellite observations were added.",
                  "Aerosol verisi yeni uydu gözlemlerinin eklendiği yıllarda sıçrama yapabilir."),
    "SNOMAS": ("In mountains snow is shown lower than it really is: each grid square (about 50 km) averages "
               "peaks and valleys together. Use it for the direction of change, not the amount.",
               "Dağlık bölgelerde kar gerçekte olduğundan az görünür: her ızgara karesi (yaklaşık 50 km) dağları ve "
               "ovaları birlikte ortalar. Miktar için değil, değişimin yönü için kullan."),
    "RUNOFF": ("Experimental: in some places the model's runoff is far larger than the rain that fell, "
               "more often in recent years. Trends are never marked as strong evidence.",
               "Deneysel: bazı yerlerde modelin akış değeri düşen yağıştan çok daha büyük ve bu son yıllarda "
               "daha sık. Trendler hiçbir zaman güçlü kanıt olarak işaretlenmez."),
}

EXPERIMENTAL = {"RUNOFF"}
SOURCE_FIELD: dict[str, str] = {}

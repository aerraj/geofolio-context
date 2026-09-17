# Primary sources

Documentation checked September 17, 2026. Provider APIs and access policies may change.

- [Coinbase Exchange WebSocket overview](https://docs.cdp.coinbase.com/exchange/websocket-feed/overview): public unauthenticated market endpoint, subscription format and delivery caveats.
- [Coinbase WebSocket channels](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels): ticker and heartbeat message shapes. GeoFolio samples last trades; it does not reconstruct a complete order book or verify trade-tape sequence completeness.
- [USGS GeoJSON summary](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php): coordinates, event times, magnitude and provenance URLs. The economic shock field is GeoFolio's assumption, not USGS data.
- [statsmodels rolling regression](https://www.statsmodels.org/stable/examples/notebooks/generated/rolling_ls.html): reference for rolling-window regression and intercept handling. Implementation uses its own C++ centered sums and NumPy reference tests; statsmodels is not a dependency.
- [pybind11 build systems](https://pybind11.readthedocs.io/en/stable/compiling.html): setuptools extension build integration.
- [SEC investor bulletin: performance claims](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-47): limitations of investment performance claims. No past or simulated results establish future performance.

- [Coinbase historical candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles): valid intervals, maximum 300 candles per request, missing-tick gaps and closed-price semantics.
- [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392): annual indicator API. GeoFolio requests NY.GDP.MKTP.CD and NY.GDP.MKTP.KD.ZG for configured countries.
- [World Bank data terms](https://data.worldbank.org/summary-terms-of-use): review indicator-specific metadata and attribution requirements. Attribution: The World Bank: World Development Indicators. Data are displayed as supplied, with latest non-null year selected and formatting applied; no endorsement is implied. Free API access is not a blanket waiver of data-provider terms.

- Basemap: [Natural Earth 1:110m land GeoJSON](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson), bundled locally and rendered in equirectangular projection; [public-domain terms](https://www.naturalearthdata.com/about/terms-of-use/). No political boundaries are rendered.

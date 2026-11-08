# Data sources

Each source is verified before integration (existence, resolution, history, frequency,
licence, limits). Status as of 2026-11-09.

| Source | Disease / use | Status | Doc |
|---|---|---|---|
| WHO FluNet | Influenza (MVP) | **Verified** — public API tested, full download profiled | [flunet.md](flunet.md), [profile](flunet_profile.md) |
| OpenDengue | Dengue (2nd) | Partly verified — repo active, release V1.3.1; **data licence not stated in repo** | — |
| WHO COVID-19 | COVID-19 (3rd) | Partly verified — daily until 25 Aug 2023, weekly after | — |
| Open-Meteo | Weather features | Partly verified — CC BY 4.0 data, free non-commercial tier (<10k calls/day); **historical-API plan requirement unconfirmed** | — |
| Natural Earth | Country boundaries | Not yet checked (public domain) | — |
| World Bank WDI | Population, health-system indicators | Not yet checked | — |

## Open questions

1. OpenDengue data licence — check the Figshare record (DOI 10.6084/m9.figshare.24259573).
2. Open-Meteo historical API — test whether it works on the free tier.
3. FluNet licence wording for public deployment.
4. Kosovo (`XKX`) and other non-ISO codes — mapping to the boundary dataset.

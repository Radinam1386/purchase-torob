# Complete purchase and Mock contact implementation plan

Goal: connect consultation, a simultaneous product/map view, real offer selection, deterministic Mock calls and recoverable history.

The supplied user specification is the implementation contract. Existing Next routes, Leaflet, SQLite catalog predicates and inquiry simulator are reused. Real dataset records, simulated answers and buyer reports remain separate. No network or telephone provider is invoked by Mock.

- [x] Extend the persistent consultation profile with category preferences, unknowns, constraints and contradiction handling. Verify existing multi-turn regressions and new profile cases.
- [x] Add real offer counts, price range/date and recorded spec highlights to catalog cards. Verify aggregate values against controlled offers and actual data.
- [x] Show the same filtered map beside products on desktop and through mobile tabs. Preserve URL state and true geography; keep independent `/map`. Verify map/list selection and offer-specific contact links.
- [x] Reuse the simulator and inquiry storage behind a deterministic Mock provider/coordinator. Implement six explicit scenarios and cookie-scoped selection/history APIs. Verify no real-offer mutation or network calls, invalid selection rejection and session isolation.
- [x] Implement `/contact?offer_id=...`, resumable run URLs and `/contact/history`. Show selected data, explicit start, stages/transcript/analysis, rerun and separate buyer report form with observation time/source.
- [x] Execute Backend checks, TypeScript/build and real browser flow on mobile/desktop from consultation through each Mock scenario, history/refresh, manual reporting and errors.
- [x] Record changed files, routes, provider/scenario/storage details, actual test results and unavoidable dataset limits. Leave a runnable local build.

File ownership: consultation in `src/core/agent.py`; catalog and Mock APIs in separate sections of `src/api.py`; Mock logic beside the existing simulator; product/map integration in existing product routes plus one shared map component; contact UI in two routed pages with `web/lib/contact.ts`. No new package is required.


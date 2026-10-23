# Scoped catalog search timeout

The live products API returned HTTP 500 (`Internal Server Error`) for searches with a location and budget. Liara runtime logs showed Next.js upstream `ECONNRESET`; the simple unscoped headphone search still returned HTTP 200. The real failing request used `q=هدفون موسیقی`, category `هدفون`, latitude 35.7219, longitude 51.4097, radius 4 km and maximum price 5,000,000 tomans.

The reused `eligible_offers` CTE could be materialized before product predicates were applied. This processed unrelated offers and defeated the selective `offers_product_idx` lookup. The local newer SQLite planner inlined this query, concealing the production performance problem. An explicit `AS NOT MATERIALIZED` permits predicate pushdown on the deployed SQLite family without changing filtering or data. See [SQLite materialization hints](https://www.sqlite.org/lang_with.html#materialization_hints).

The regression fixture adds 2,000 unrelated offers and reproduces the older materialization choice on newer development SQLite. Before the fix it performed 8,016 distance calculations and failed the operation budget. After the fix it performs 14; the forced-materialization negative control still performs 8,016 and returns an identical response. This avoids a timing test tied to machine speed.

Validation before deployment: all 62 backend tests passed. No dependency, schema, pricing, infrastructure plan or live data migration was needed. Deployment uses the existing persistent disk; startup does not replace an existing catalog or its histories.

Release `6adbaf5dbffb36d784151ae2` passed live verification after traffic finished switching to the new container. Build state `READY` alone preceded that switch; the first HTTP attempt still reached the retiring release and timed out. Runtime release identities and a read-only console check confirmed the new code and SQLite 3.40.1 before acceptance was repeated.

The production query plans use `offers_product_idx`; count, rows and facets took 0.085, 0.069 and 0.098 seconds respectively inside the container. Public API checks returned 735 headphone products in 642 ms, page two in 392 ms and ascending price order in 384 ms. The map returned the same 735 products from 160 shops. S24 search returned five products in 6.081 seconds. A remote zero-radius center returned zero headphone products. Desktop, refresh and mobile browser checks passed, exit code zero; the mobile screenshot was visually reviewed.

Live results are recorded in `output/liara/search-repair-check.json`, browser evidence alongside it and `remote-query-plan.txt`. No broad concurrent-load test was performed; S24 search remains slower than the headphone query.

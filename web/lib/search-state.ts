export const LAST_RESULTS_KEY = "torob-last-results-url";
export const COMPARE_KEY = "torob-product-compare.v1";

export interface SearchState {
  query: string;
  label: string;
  brand: string;
  category: string;
  minPrice: number | null;
  maxPrice: number | null;
  sort: "relevance" | "price_asc" | "price_desc";
  page: number;
  geography: Record<string, string>;
}

function price(value: string | null): number | null {
  if (!value?.trim()) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

export function readSearchState(params: URLSearchParams): SearchState {
  const page = Number(params.get("page") || 1);
  const sort = params.get("sort");
  return {
    query: params.get("q") || "", label: params.get("label") || "",
    brand: params.get("brand") || "", category: params.get("category") || "",
    minPrice: price(params.get("min_price")), maxPrice: price(params.get("max_price")),
    sort: sort === "price_asc" || sort === "price_desc" ? sort : "relevance",
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    geography: Object.fromEntries(["lat", "lng", "radius_km", "city", "location", "location_label", "installment", "express", "open_now"]
      .filter(key => params.has(key)).map(key => [key, params.get(key)!])),
  };
}

export function searchParams(state: SearchState): URLSearchParams {
  const params = new URLSearchParams(state.geography);
  if (state.query) params.set("q", state.query);
  if (state.label) params.set("label", state.label);
  if (state.brand) params.set("brand", state.brand);
  if (state.category) params.set("category", state.category);
  if (state.minPrice !== null) params.set("min_price", String(state.minPrice));
  if (state.maxPrice !== null) params.set("max_price", String(state.maxPrice));
  if (state.sort !== "relevance") params.set("sort", state.sort);
  if (state.page > 1) params.set("page", String(state.page));
  return params;
}

export function resultsUrl(state: SearchState): string {
  const query = searchParams(state).toString();
  return `/products${query ? `?${query}` : ""}`;
}

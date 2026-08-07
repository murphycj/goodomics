import type {
  AnalysisValue,
  InsightDraft,
  InsightView,
  ResultScope,
} from "./insightSchemas";
import { valueReference } from "./fieldReferences";

/** Create the default result scope for the selected analysis grain. */
export function defaultScope(
  grain: InsightDraft["analysis"]["grain"],
): ResultScope {
  return {
    selection:
      grain === "run" ? "all_eligible" : "latest_successful_per_sample",
    analysis_type_ids: [],
    method_ids: [],
    method_versions: [],
    run_ids: [],
    statuses: [],
    run_contract_ids: [],
  };
}

/** Generate a unique, identifier-safe alias for a value field. */
export function safeValueAlias(
  field: string,
  values: AnalysisValue[],
  grain: string,
) {
  const used = new Set(values.map(valueReference));
  const normalized = field
    .replace(/[^A-Za-z0-9_]+/g, "_")
    .replace(/^([^A-Za-z_])/, "_$1");
  const base = normalized || "value";
  let id = base;
  let suffix = 2;
  while (used.has(id) || id === `${grain}_id`) id = `${base}_${suffix++}`;
  return id;
}

/** Create a view with sensible bindings and settings for its visualization kind. */
export function createViewForKind(
  kind: InsightView["kind"],
  values: AnalysisValue[],
): InsightView {
  const ids = values.map(valueReference);
  const first = ids[0] ?? "value";
  const second = ids[1] ?? first;

  if (kind === "table") {
    return {
      kind,
      hidden_values: [],
      sorting: [],
      null_format: "—",
      numeric_format: {},
    };
  }

  if (kind === "scatter") {
    return {
      kind,
      hidden_values: [],
      x: first,
      y: second,
      colors: {},
      tooltips: [],
    };
  }

  if (kind === "metric")
    return { kind, hidden_values: [], value: first, thresholds: [] };

  if (kind === "histogram") {
    return { kind, hidden_values: [], bins: 20, colors: {} };
  }

  if (kind === "boxplot") return { kind, hidden_values: [], colors: {} };

  if (kind === "heatmap") {
    return {
      kind,
      hidden_values: [],
      x: first,
      y: second,
      value: ids[2] ?? first,
      colors: [],
      tooltips: [],
    };
  }

  return {
    kind,
    hidden_values: kind === "pie" || kind === "donut" ? ids.slice(1) : [],
    colors: {},
    tooltips: [],
  };
}

/**
 * Keep persisted view settings while removing references to deleted values.
 * It is called when doing things like changing view type, adding or removing values,
 * and changing the analysis grain
 * */
export function reconcileView(
  view: InsightView,
  values: AnalysisValue[],
  grain: InsightDraft["analysis"]["grain"],
): InsightView {
  const ids = values.map(valueReference);
  const allowed = new Set([...ids, `${grain}_id`]);
  const first = ids[0] ?? "value";
  const second = ids[1] ?? first;

  const hiddenValues = (required: Set<string> = new Set()) =>
    view.hidden_values.filter((id) => ids.includes(id) && !required.has(id));

  const colors = (current: Record<string, string>) =>
    Object.fromEntries(
      Object.entries(current).filter(([id]) => ids.includes(id)),
    );

  if (view.kind === "table") {
    return {
      ...view,
      hidden_values: hiddenValues(),
      sorting: view.sorting.filter((sort) => allowed.has(sort.by)),
      numeric_format: Object.fromEntries(
        Object.entries(view.numeric_format).filter(([id]) => allowed.has(id)),
      ),
    };
  }

  if (view.kind === "scatter") {
    const x = ids.includes(view.x) ? view.x : first;
    const rawY = ids.includes(view.y) ? view.y : second;
    const y =
      ids.length > 1 && rawY === x
        ? (ids.find((id) => id !== x) ?? second)
        : rawY;
    return {
      ...view,
      x,
      y,
      hidden_values: hiddenValues(new Set([x, y])),
      colors: colors(view.colors),
      tooltips: view.tooltips.filter((id) => allowed.has(id)),
    };
  }

  if (view.kind === "metric") {
    const value = ids.includes(view.value) ? view.value : first;
    return { ...view, value, hidden_values: hiddenValues(new Set([value])) };
  }

  if (view.kind === "histogram") {
    return {
      ...view,
      hidden_values: hiddenValues(),
      colors: colors(view.colors),
    };
  }

  if (view.kind === "boxplot") {
    return {
      ...view,
      category:
        view.category && allowed.has(view.category) ? view.category : undefined,
      hidden_values: hiddenValues(
        new Set(
          view.category && allowed.has(view.category) ? [view.category] : [],
        ),
      ),
      colors: colors(view.colors),
    };
  }

  if (view.kind === "heatmap") {
    const x = ids.includes(view.x) ? view.x : first;
    const rawY = ids.includes(view.y) ? view.y : second;
    const y =
      ids.length > 1 && rawY === x
        ? (ids.find((id) => id !== x) ?? second)
        : rawY;
    const rawValue = ids.includes(view.value) ? view.value : (ids[2] ?? first);
    const value =
      ids.length > 2 && (rawValue === x || rawValue === y)
        ? (ids.find((id) => id !== x && id !== y) ?? rawValue)
        : rawValue;
    return {
      ...view,
      x,
      y,
      value,
      hidden_values: hiddenValues(new Set([x, y, value])),
      tooltips: view.tooltips.filter((id) => allowed.has(id)),
    };
  }

  const category =
    view.category && allowed.has(view.category) ? view.category : undefined;
  const nextHidden = normalizeCategoryVisibility(
    view.kind,
    ids,
    category,
    hiddenValues(new Set(category ? [category] : [])),
  );

  return {
    ...view,
    category,
    hidden_values: nextHidden,
    colors: colors(view.colors),
    tooltips: view.tooltips.filter((id) => allowed.has(id)),
  };
}

/** Ensure pie and donut views expose exactly one non-category value. */
function normalizeCategoryVisibility(
  kind: "bar" | "stacked_bar" | "line" | "area" | "pie" | "donut",
  ids: string[],
  category: string | undefined,
  hiddenValues: string[],
) {
  if (kind !== "pie" && kind !== "donut") return hiddenValues;

  const candidates = ids.filter((id) => id !== category);
  const hidden = new Set(hiddenValues);
  const visible = candidates.filter((id) => !hidden.has(id));

  if (!visible.length && candidates[0]) hidden.delete(candidates[0]);

  const keptVisible = candidates.find((id) => !hidden.has(id));

  for (const id of candidates) {
    if (id !== keptVisible) hidden.add(id);
  }

  return ids.filter((id) => hidden.has(id));
}

/** Reconcile a view after adding a value while preserving pie and donut visibility rules. */
export function appendValueToView(
  view: InsightView,
  valueId: string,
  values: AnalysisValue[],
  grain: InsightDraft["analysis"]["grain"],
): InsightView {
  const reconciled = reconcileView(view, values, grain);

  if (reconciled.kind === "pie" || reconciled.kind === "donut") {
    const visible = values.filter((value) => {
      const reference = valueReference(value);
      return (
        !reconciled.hidden_values.includes(reference) &&
        reference !== reconciled.category
      );
    });

    if (visible.length > 1) {
      return {
        ...reconciled,
        hidden_values: [...reconciled.hidden_values, valueId],
      };
    }
  }

  return reconciled;
}

/** Replace one public value reference throughout an existing view. */
export function replaceViewReference(
  view: InsightView,
  previous: string,
  next: string,
): InsightView {
  const replace = (value: string) => (value === previous ? next : value);
  const hiddenValues = view.hidden_values.map(replace);

  if (view.kind === "table") {
    return {
      ...view,
      hidden_values: hiddenValues,
      sorting: view.sorting.map((sort) => ({ ...sort, by: replace(sort.by) })),
      numeric_format: Object.fromEntries(
        Object.entries(view.numeric_format).map(([reference, format]) => [
          replace(reference),
          format,
        ]),
      ),
    };
  }

  if (view.kind === "scatter") {
    return {
      ...view,
      hidden_values: hiddenValues,
      x: replace(view.x),
      y: replace(view.y),
      colors: replaceRecordKeys(view.colors, replace),
      tooltips: view.tooltips.map(replace),
    };
  }

  if (view.kind === "metric") {
    return { ...view, hidden_values: hiddenValues, value: replace(view.value) };
  }

  if (view.kind === "histogram") {
    return {
      ...view,
      hidden_values: hiddenValues,
      colors: replaceRecordKeys(view.colors, replace),
    };
  }

  if (view.kind === "heatmap") {
    return {
      ...view,
      hidden_values: hiddenValues,
      x: replace(view.x),
      y: replace(view.y),
      value: replace(view.value),
      tooltips: view.tooltips.map(replace),
    };
  }

  if (view.kind === "boxplot") {
    return {
      ...view,
      hidden_values: hiddenValues,
      category: view.category ? replace(view.category) : undefined,
      colors: replaceRecordKeys(view.colors, replace),
    };
  }

  return {
    ...view,
    hidden_values: hiddenValues,
    category: view.category ? replace(view.category) : undefined,
    colors: replaceRecordKeys(view.colors, replace),
    tooltips: view.tooltips.map(replace),
  };
}

/** Replace keys in a string record using the supplied reference mapper. */
function replaceRecordKeys(
  values: Record<string, string>,
  replace: (value: string) => string,
) {
  return Object.fromEntries(
    Object.entries(values).map(([reference, value]) => [
      replace(reference),
      value,
    ]),
  );
}

/** Convert an underscore-delimited identifier into a title-cased label. */
export function titleCase(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

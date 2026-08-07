import {
  Box,
  ChartArea,
  ChartBar,
  ChartBarStacked,
  ChartLine,
  ChartNoAxesColumn,
  ChartPie,
  ChartScatter,
  CircleGauge,
  Hash,
  LayoutGrid,
  Table2,
  type LucideIcon,
} from "lucide-react";
import type { InsightView } from "./insightSchemas";

export type InsightViewKind = InsightView["kind"];

type InsightViewDefinition = {
  label: string;
  icon: LucideIcon;
  editor: {
    title: string;
    addLabel: string;
    valueNounPlural: string;
  };
  defaultJoin: "outer" | "inner" | undefined;
  capabilities: {
    axes: boolean;
    categoryBinding: boolean;
    recordColors: boolean;
    tooltips: boolean;
    marks: boolean;
  };
};

/** Ordered, exhaustive frontend metadata for every supported insight view. */
export const INSIGHT_VIEW_CATALOG = {
  table: {
    label: "Table",
    icon: Table2,
    editor: {
      title: "Columns",
      addLabel: "Add columns",
      valueNounPlural: "columns",
    },
    defaultJoin: "outer",
    capabilities: {
      axes: false,
      categoryBinding: false,
      recordColors: false,
      tooltips: false,
      marks: false,
    },
  },
  bar: {
    label: "Bar chart",
    icon: ChartBar,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: true,
      marks: true,
    },
  },
  stacked_bar: {
    label: "Stacked bar",
    icon: ChartBarStacked,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: true,
      marks: true,
    },
  },
  line: {
    label: "Line chart",
    icon: ChartLine,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: true,
      marks: true,
    },
  },
  area: {
    label: "Area chart",
    icon: ChartArea,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: true,
      marks: true,
    },
  },
  scatter: {
    label: "Scatter plot",
    icon: ChartScatter,
    editor: {
      title: "Data",
      addLabel: "Choose fields",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: false,
      recordColors: true,
      tooltips: true,
      marks: true,
    },
  },
  metric: {
    label: "Metric",
    icon: Hash,
    editor: {
      title: "Value",
      addLabel: "Choose value",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: false,
      categoryBinding: false,
      recordColors: false,
      tooltips: false,
      marks: false,
    },
  },
  histogram: {
    label: "Histogram",
    icon: ChartNoAxesColumn,
    editor: {
      title: "Distribution",
      addLabel: "Add fields",
      valueNounPlural: "fields",
    },
    defaultJoin: undefined,
    capabilities: {
      axes: true,
      categoryBinding: false,
      recordColors: true,
      tooltips: false,
      marks: true,
    },
  },
  boxplot: {
    label: "Box plot",
    icon: Box,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: false,
      marks: false,
    },
  },
  pie: {
    label: "Pie chart",
    icon: ChartPie,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: true,
      marks: false,
    },
  },
  donut: {
    label: "Donut chart",
    icon: CircleGauge,
    editor: {
      title: "Data",
      addLabel: "Add series",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: true,
      categoryBinding: true,
      recordColors: true,
      tooltips: true,
      marks: false,
    },
  },
  heatmap: {
    label: "Heatmap",
    icon: LayoutGrid,
    editor: {
      title: "Data",
      addLabel: "Choose fields",
      valueNounPlural: "fields",
    },
    defaultJoin: "inner",
    capabilities: {
      axes: false,
      categoryBinding: false,
      recordColors: false,
      tooltips: true,
      marks: false,
    },
  },
} as const satisfies Record<InsightViewKind, InsightViewDefinition>;

const insightViewKinds = Object.keys(
  INSIGHT_VIEW_CATALOG,
) as InsightViewKind[];

export const INSIGHT_VIEW_OPTIONS = insightViewKinds.map((kind) => ({
  kind,
  ...INSIGHT_VIEW_CATALOG[kind],
}));

export type InsightViewCapability = keyof InsightViewDefinition["capabilities"];
type InsightViewCatalog = typeof INSIGHT_VIEW_CATALOG;

export type InsightViewKindWith<Capability extends InsightViewCapability> = {
  [Kind in InsightViewKind]: InsightViewCatalog[Kind]["capabilities"][Capability] extends true
      ? Kind
      : never;
}[InsightViewKind];

export function getInsightViewDefinition(kind: InsightViewKind) {
  return INSIGHT_VIEW_CATALOG[kind];
}

export function isInsightViewKind(value: string): value is InsightViewKind {
  return Object.prototype.hasOwnProperty.call(INSIGHT_VIEW_CATALOG, value);
}

export function insightViewLabel(kind: string) {
  return isInsightViewKind(kind) ? INSIGHT_VIEW_CATALOG[kind].label : kind;
}

export function insightViewSupportsMarks(kind: string) {
  return isInsightViewKind(kind)
    ? INSIGHT_VIEW_CATALOG[kind].capabilities.marks
    : true;
}

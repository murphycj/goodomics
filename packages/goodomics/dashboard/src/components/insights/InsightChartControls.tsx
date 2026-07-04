import {
  AreaChart,
  BarChart2,
  BarChart3,
  Box,
  Check,
  ChevronDown,
  Hash,
  LineChart,
  PieChart,
  ScatterChart,
  Settings2,
  Table2,
} from "lucide-react";
import type { DisplayOptions } from "../../lib/insightDisplayOptions";
import { DISPLAY_OPTION_ITEMS } from "../../lib/insightDisplayOptions";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "../ui";

type ChartOption = {
  value: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
};

const CHART_OPTIONS: { group: string; items: ChartOption[] }[] = [
  {
    group: "Time Series",
    items: [
      {
        value: "line",
        label: "Line chart",
        description: "Trends over time as a continuous line.",
        icon: LineChart,
      },
      {
        value: "area",
        label: "Area chart",
        description: "Trends over time as a shaded area.",
        icon: AreaChart,
      },
      {
        value: "bar",
        label: "Bar chart",
        description: "Values as vertical bars.",
        icon: BarChart3,
      },
      {
        value: "stacked_bar",
        label: "Stacked bar chart",
        description: "Series stacked into vertical bars.",
        icon: BarChart2,
      },
    ],
  },
  {
    group: "Total Value",
    items: [
      {
        value: "metric",
        label: "Metric",
        description: "A headline value.",
        icon: Hash,
      },
      {
        value: "pie",
        label: "Pie chart",
        description: "Proportions of a whole.",
        icon: PieChart,
      },
      {
        value: "table",
        label: "Table",
        description: "Rows and columns.",
        icon: Table2,
      },
    ],
  },
  {
    group: "Distributions",
    items: [
      {
        value: "histogram",
        label: "Histogram",
        description: "Distribution of one or more numeric fields.",
        icon: BarChart2,
      },
      {
        value: "boxplot",
        label: "Box plot",
        description: "Quartiles and outliers.",
        icon: Box,
      },
      {
        value: "scatter",
        label: "Scatter plot",
        description: "Two aligned measures plotted together.",
        icon: ScatterChart,
      },
      {
        value: "heatmap",
        label: "Heatmap",
        description: "Intensity across two dimensions.",
        icon: GridIcon,
      },
    ],
  },
];

export function InsightChartControls({
  displayOptions,
  onDisplayOptionsChange,
  visualization,
  onVisualizationChange,
}: {
  displayOptions: DisplayOptions;
  onDisplayOptionsChange: React.Dispatch<React.SetStateAction<DisplayOptions>>;
  visualization: string;
  onVisualizationChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <OptionsMenu
        options={displayOptions}
        onChange={onDisplayOptionsChange}
      />
      <ChartTypeSelect
        value={visualization}
        onChange={onVisualizationChange}
      />
    </div>
  );
}

function OptionsMenu({
  options,
  onChange,
}: {
  options: DisplayOptions;
  onChange: React.Dispatch<React.SetStateAction<DisplayOptions>>;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost">
          <Settings2 className="h-4 w-4" /> Options{" "}
          <ChevronDown className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>Display</DropdownMenuLabel>
        {DISPLAY_OPTION_ITEMS.map((item) => (
          <DropdownMenuItem
            key={item.key}
            onSelect={(event) => {
              event.preventDefault();
              onChange((current) => ({
                ...current,
                [item.key]: !current[item.key],
              }));
            }}
          >
            <span className="flex h-4 w-4 items-center justify-center rounded border border-[#c7d0dd]">
              {options[item.key] ? <Check className="h-3 w-3" /> : null}
            </span>
            {item.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ChartTypeSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const selected = chartOption(value);
  const Icon = selected.icon;
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-[190px]">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0" />
          <span className="truncate">{selected.label}</span>
        </div>
      </SelectTrigger>
      <SelectContent className="max-h-[560px] w-[380px]">
        {CHART_OPTIONS.map((group) => (
          <div key={group.group}>
            <div className="px-3 py-2 text-xs font-bold uppercase tracking-wide text-[#8b95a5]">
              {group.group}
            </div>
            {group.items.map((item) => {
              const ItemIcon = item.icon;
              return (
                <SelectItem key={item.value} value={item.value}>
                  <span className="flex items-start gap-3">
                    <ItemIcon className="mt-0.5 h-4 w-4" />
                    <span>
                      <span className="block font-semibold">{item.label}</span>
                      <span className="block text-xs text-[#657082]">
                        {item.description}
                      </span>
                    </span>
                  </span>
                </SelectItem>
              );
            })}
          </div>
        ))}
      </SelectContent>
    </Select>
  );
}

function chartOption(value: string) {
  return (
    CHART_OPTIONS.flatMap((group) => group.items).find(
      (item) => item.value === value,
    ) ?? CHART_OPTIONS[0].items[0]
  );
}

function GridIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <rect height="7" width="7" x="3" y="3" />
      <rect height="7" width="7" x="14" y="3" />
      <rect height="7" width="7" x="3" y="14" />
      <rect height="7" width="7" x="14" y="14" />
    </svg>
  );
}

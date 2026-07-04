import { HexColorInput, HexColorPicker } from "react-colorful";
import { Copy, MoreHorizontal, Plus } from "lucide-react";
import type { DataProfile, DataProfileField } from "../../api";
import { CHART_COLORS } from "../../lib/chartColors";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";
import { isRecord } from "../reports/reportUtils";

export type BuilderSeries = {
  id: string;
  profileId: string;
  fieldId: string;
  aggregation: string;
  name: string;
  color: string;
};

export function InsightSeriesEditor({
  profiles,
  series,
  setSeries,
}: {
  profiles: DataProfile[];
  series: BuilderSeries[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Series</Label>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            setSeries((current) => [
              ...current,
              blankSeries(current.length, current[0]?.profileId ?? "", ""),
            ])
          }
        >
          <Plus className="h-4 w-4" /> Series
        </Button>
      </div>
      {series.map((item, index) => {
        const profile = profiles.find(
          (candidate) => candidate.data_profile_id === item.profileId,
        );
        const fields = profile?.fields ?? [];
        const field = fields.find(
          (candidate) => candidate.field_id === item.fieldId,
        );
        return (
          <SeriesCard
            field={field}
            fields={fields}
            index={index}
            item={item}
            key={item.id}
            profiles={profiles}
            setSeries={setSeries}
          />
        );
      })}
    </div>
  );
}

export function blankSeries(
  index: number,
  profileId: string,
  fieldId: string,
): BuilderSeries {
  return {
    id: `series-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`,
    profileId,
    fieldId,
    aggregation: "avg",
    name: "",
    color: CHART_COLORS[index % CHART_COLORS.length],
  };
}

export function profileSeries(
  profileId: string,
  profiles: DataProfile[],
  current: BuilderSeries,
): BuilderSeries {
  const profile = profiles.find(
    (candidate) => candidate.data_profile_id === profileId,
  );
  const field =
    profile?.fields.length === 1
      ? profile.fields[0]
      : profile?.fields.find((candidate) => candidate.value_type === "numeric");
  return {
    ...current,
    profileId,
    fieldId: field?.field_id ?? "",
    name: field?.display_name ?? "",
  };
}

export function fieldForSeries(
  profiles: DataProfile[],
  series: BuilderSeries,
) {
  return profiles
    .find((profile) => profile.data_profile_id === series.profileId)
    ?.fields.find((field) => field.field_id === series.fieldId);
}

export function seriesDisplayName(
  profiles: DataProfile[],
  series: BuilderSeries,
) {
  return (
    series.name ||
    fieldForSeries(profiles, series)?.display_name ||
    series.fieldId ||
    "This field"
  );
}

function SeriesCard({
  field,
  fields,
  index,
  item,
  profiles,
  setSeries,
}: {
  field: DataProfileField | undefined;
  fields: DataProfileField[];
  index: number;
  item: BuilderSeries;
  profiles: DataProfile[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <div className="rounded-md border border-[#d6dee8] bg-white p-3 shadow-sm">
      <div className="mb-3 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
        <ColorPickerTrigger
          color={item.color}
          index={index}
          label={seriesDisplayName(profiles, item)}
          onChange={(color) => updateSeries(setSeries, item.id, { color })}
        />
        <Input
          aria-label="Series name"
          className="h-9 min-w-0 border-transparent bg-transparent px-2 font-semibold shadow-none hover:border-[#cfd8e3] focus:border-[#cfd8e3]"
          placeholder={field?.display_name || `Series ${index + 1}`}
          value={item.name}
          onChange={(event) =>
            updateSeries(setSeries, item.id, { name: event.target.value })
          }
        />
        <SeriesActions
          field={field}
          index={index}
          item={item}
          setSeries={setSeries}
        />
      </div>
      <div className="space-y-2">
        <ProfileSelect
          item={item}
          profiles={profiles}
          setSeries={setSeries}
        />
        <FieldSelect
          fields={fields}
          item={item}
          setSeries={setSeries}
        />
        <AggregationSelect
          item={item}
          setSeries={setSeries}
        />
        <FieldSummary field={field} />
      </div>
    </div>
  );
}

function ColorPickerTrigger({
  color,
  index,
  label,
  onChange,
}: {
  color: string;
  index: number;
  label: string;
  onChange: (color: string) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label={`Choose color for ${label}`}
          className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-black/10 text-xs font-semibold text-white shadow-sm outline-none transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-[#21a66a]"
          style={{ backgroundColor: color }}
          type="button"
        >
          {String.fromCharCode(65 + index)}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[244px]">
        <div className="space-y-3 p-2">
          <HexColorPicker color={color} onChange={onChange} />
          <div className="space-y-1.5">
            <Label>Hex</Label>
            <HexColorInput
              className="flex min-h-[38px] w-full rounded-lg border border-[#cfd8e3] bg-white px-3 py-1 font-mono text-sm uppercase outline-none transition-colors focus:ring-2 focus:ring-[#21a66a]"
              color={color}
              prefixed
              onChange={onChange}
            />
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SeriesActions({
  field,
  index,
  item,
  setSeries,
}: {
  field: DataProfileField | undefined;
  index: number;
  item: BuilderSeries;
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button aria-label="Series actions" size="icon" variant="ghost">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[180px]">
        <DropdownMenuItem
          onClick={() =>
            setSeries((current) => duplicateSeries(current, item, field, index))
          }
        >
          <Copy className="h-4 w-4" /> Duplicate series
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={index === 0}
          onClick={() =>
            setSeries((current) =>
              current.filter((candidate) => candidate.id !== item.id),
            )
          }
        >
          Delete series
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function duplicateSeries(
  current: BuilderSeries[],
  item: BuilderSeries,
  field: DataProfileField | undefined,
  index: number,
) {
  const source = current.find((candidate) => candidate.id === item.id);
  if (!source) return current;
  const sourceIndex = current.findIndex((candidate) => candidate.id === item.id);
  const copyName = source.name || field?.display_name || `Series ${index + 1}`;
  const duplicate = {
    ...source,
    id: `series-${Date.now()}-${current.length}-${Math.random()
      .toString(16)
      .slice(2)}`,
    name: `${copyName} copy`,
    color: CHART_COLORS[current.length % CHART_COLORS.length],
  };
  return [
    ...current.slice(0, sourceIndex + 1),
    duplicate,
    ...current.slice(sourceIndex + 1),
  ];
}

function ProfileSelect({
  item,
  profiles,
  setSeries,
}: {
  item: BuilderSeries;
  profiles: DataProfile[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <Select
      value={item.profileId}
      onValueChange={(value) =>
        setSeries((current) =>
          current.map((candidate) =>
            candidate.id === item.id
              ? profileSeries(value, profiles, candidate)
              : candidate,
          ),
        )
      }
    >
      <SelectTrigger>
        <SelectValue placeholder="Data profile" />
      </SelectTrigger>
      <SelectContent>
        {profiles.map((profile) => (
          <SelectItem
            key={profile.data_profile_id}
            value={profile.data_profile_id}
          >
            {profile.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function FieldSelect({
  fields,
  item,
  setSeries,
}: {
  fields: DataProfileField[];
  item: BuilderSeries;
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <Select
      value={item.fieldId}
      onValueChange={(value) =>
        setSeries((current) =>
          current.map((candidate) =>
            candidate.id === item.id
              ? {
                  ...candidate,
                  fieldId: value,
                  name:
                    candidate.name ||
                    fields.find((field) => field.field_id === value)
                      ?.display_name ||
                    candidate.name,
                }
              : candidate,
          ),
        )
      }
    >
      <SelectTrigger>
        <SelectValue placeholder="Field / measure" />
      </SelectTrigger>
      <SelectContent>
        {fields.map((field) => (
          <SelectItem key={field.field_id} value={field.field_id}>
            {field.display_name || field.field_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function AggregationSelect({
  item,
  setSeries,
}: {
  item: BuilderSeries;
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <Select
      value={item.aggregation}
      onValueChange={(aggregation) =>
        updateSeries(setSeries, item.id, { aggregation })
      }
    >
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {["count", "sum", "avg", "min", "max"].map((aggregation) => (
          <SelectItem key={aggregation} value={aggregation}>
            {aggregation}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function updateSeries(
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>,
  id: string,
  patch: Partial<BuilderSeries>,
) {
  setSeries((current) =>
    current.map((candidate) =>
      candidate.id === id ? { ...candidate, ...patch } : candidate,
    ),
  );
}

function FieldSummary({ field }: { field: DataProfileField | undefined }) {
  if (!field) return null;
  const parts = [
    field.value_type,
    field.unit,
    summaryRange(field.summary),
    topValues(field.summary),
  ].filter(Boolean);
  return (
    <div className="mt-2 space-y-1 text-xs text-[#657082]">
      <div>{parts.join(" · ")}</div>
      {field.description ? <div>{field.description}</div> : null}
    </div>
  );
}

function summaryRange(summary: Record<string, unknown>) {
  const min = summary.min;
  const max = summary.max;
  if (typeof min === "number" && typeof max === "number") {
    return `${min.toLocaleString()} to ${max.toLocaleString()}`;
  }
  return null;
}

function topValues(summary: Record<string, unknown>) {
  const values = summary.top_values;
  if (!Array.isArray(values) || values.length === 0) return null;
  return values
    .slice(0, 3)
    .map((item) =>
      isRecord(item) && "value" in item ? String(item.value) : String(item),
    )
    .join(", ");
}

/** Generated-SDK integration and frontend draft adapters. */

import "./client";
import { z } from "zod";
import {
  addMember as sdkAddMember,
  addProjectSampleGroupMembers as sdkAddProjectSampleGroupMembers,
  addUser as sdkAddUser,
  changePassword as sdkChangePassword,
  chatWithAi as sdkChatWithAi,
  createInsight as sdkCreateInsight,
  createProject as sdkCreateProject,
  createProjectSampleGroup as sdkCreateProjectSampleGroup,
  createReport as sdkCreateReport,
  deleteInsight as sdkDeleteInsight,
  deleteMember as sdkDeleteMember,
  deleteProjectSampleGroup as sdkDeleteProjectSampleGroup,
  deleteReport as sdkDeleteReport,
  executeAdhocInsight,
  executeSavedInsight,
  executeSavedReport,
  getContractResultOptions as sdkGetContractResultOptions,
  getDatabaseSummary as sdkGetDatabaseSummary,
  getDataContract as sdkGetDataContract,
  getInsight as sdkGetInsight,
  getInsightCapabilities as sdkGetInsightCapabilities,
  getProject as sdkGetProject,
  getProjectRun as sdkGetProjectRun,
  getProjectSample as sdkGetProjectSample,
  getProjectSampleGroup as sdkGetProjectSampleGroup,
  getSavedReport,
  listDatabaseTables as sdkListDatabaseTables,
  listDataContracts as sdkListDataContracts,
  listInsights as sdkListInsights,
  listMembers as sdkListMembers,
  listProjectRunAnalyticsMetrics,
  listProjectRunAnalyticsPayloads,
  listProjectRunFiles as sdkListProjectRunFiles,
  listProjectRuns as sdkListProjectRuns,
  listProjectSampleGroupMembers as sdkListProjectSampleGroupMembers,
  listProjectSampleGroups as sdkListProjectSampleGroups,
  listProjectSampleRunAnalyticsMetrics,
  listProjectSampleRuns as sdkListProjectSampleRuns,
  listProjectSamples as sdkListProjectSamples,
  listProjects as sdkListProjects,
  listReports as sdkListReports,
  listRoles as sdkListRoles,
  listRuns as sdkListRuns,
  listSampleGroups as sdkListSampleGroups,
  listUserMemberships as sdkListUserMemberships,
  listUsers as sdkListUsers,
  patchInsight as sdkPatchInsight,
  patchMember as sdkPatchMember,
  patchProject as sdkPatchProject,
  patchProjectSampleGroup as sdkPatchProjectSampleGroup,
  patchReport as sdkPatchReport,
  patchRole as sdkPatchRole,
  patchUser as sdkPatchUser,
  previewDatabaseTable as sdkPreviewDatabaseTable,
  removeProjectSampleGroupMembers as sdkRemoveProjectSampleGroupMembers,
  searchSamples as sdkSearchSamples,
  validateInsightConfig as sdkValidateInsightConfig,
  validateReportConfig as sdkValidateReportConfig,
} from "./generated/sdk.gen";
import type {
  AdminMembershipRead,
  AnalyticsMetricRead,
  AnalyticsResultPayloadRead,
  ChatMessage,
  ChatResult,
  ContractResultOptionsRead,
  DatabaseSummaryRead,
  DatabaseTablePageRead,
  DatabaseTableRead,
  DataContractFieldRead,
  DataContractRead,
  FileRead,
  InsightCapabilitiesRead,
  InsightValidationRead,
  MembershipRead,
  ProjectPatch,
  ProjectRead,
  RoleRead,
  Run,
  RunPageRead,
  Sample,
  SampleGroupMemberPageRead,
  SampleGroupMemberRead,
  SampleGroupPageRead,
  SampleGroupPatch,
  SampleGroupRead,
  SampleListItemRead,
  SamplePageRead,
  SampleRunRead,
  SavedInsightPatch,
  SavedInsightRead,
  SavedInsightSummary,
  SavedReportRead,
  SavedReportSummary,
  SearchResultRead,
  ToolEvidence,
  UserPatchRequest,
  UserRead,
} from "./generated/types.gen";
import {
  zChatResult,
  zDataContractFieldRead,
  zDataContractRead,
  zDatabaseTablePageRead,
  zDatabaseTableRead,
  zFileRead,
  zProjectRead,
  zRun,
  zRunPageRead,
  zSampleGroupPageRead,
  zSampleGroupRead,
  zSampleListItemRead,
  zSamplePageRead,
} from "./generated/zod.gen";
import {
  insightDraftToCreate,
  insightDraftToPatch,
  reportDraftToCreate,
  reportDraftToPatch,
  savedInsightToDraft,
  savedReportToDraft,
  type InsightDraft,
  type ReportDefinition,
} from "../lib/insightSchemas";
export { fileContentUrl, listNamedRows, openFileContent } from "./transport";

export type GoodomicsRun = Omit<z.output<typeof zRun>, "created_at" | "samples"> & {
  created_at: string;
  samples: Sample[];
};
export type RunsPage = Omit<RunPageRead, "items"> & { items: GoodomicsRun[] };
export type GoodomicsProject = z.output<typeof zProjectRead>;
export type GoodomicsSample = Sample;
export type SampleListItem = z.output<typeof zSampleListItemRead>;
export type SamplesPage = z.output<typeof zSamplePageRead>;
export type SampleRun = SampleRunRead;
export type SearchResult = SearchResultRead;
export type StoredFile = z.output<typeof zFileRead>;
export type AnalyticsMetric = AnalyticsMetricRead;
export type AnalyticsPayload = AnalyticsResultPayloadRead;
export type DatabaseSummary = DatabaseSummaryRead;
export type DatabaseTable = Omit<z.output<typeof zDatabaseTableRead>, "columns"> & {
  columns: string[];
};
export type DatabaseTablePage = z.output<typeof zDatabaseTablePageRead>;
export type DataContractField = Omit<
  z.output<typeof zDataContractFieldRead>,
  "metadata_json" | "physical_tables" | "query_ref" | "summary"
> & {
  metadata_json: Record<string, unknown>;
  physical_tables: Record<string, unknown>;
  query_ref: Record<string, unknown>;
  summary: Record<string, unknown>;
};
export type DataContract = Omit<
  z.output<typeof zDataContractRead>,
  "fields"
> & { fields: DataContractField[] };
export type InsightSummary = SavedInsightSummary;
export type ReportSummary = SavedReportSummary;
export type InsightCapabilities = InsightCapabilitiesRead;
export type InsightValidation = InsightValidationRead;
export type SampleGroup = z.output<typeof zSampleGroupRead>;
export type SampleGroupPage = z.output<typeof zSampleGroupPageRead>;
export type SampleGroupMember = SampleGroupMemberRead;
export type SampleGroupMemberPage = SampleGroupMemberPageRead;
export type AiMessage = ChatMessage;
export type AiToolEvidence = ToolEvidence;
export type AiChatResponse = Omit<z.output<typeof zChatResult>, "tool_calls"> & {
  conversation_id: string | null;
  tool_calls: ToolEvidence[];
};
export type GoodomicsUser = UserRead;
export type ProjectRole = RoleRead;
export type ProjectMembership = MembershipRead;
export type AdminMembership = AdminMembershipRead;
export type InsightResult = Record<string, unknown>;
export type ReportResult = Record<string, unknown>;
export type SavedInsight = Omit<
  SavedInsightRead,
  "analysis" | "version" | "view"
> & InsightDraft;
export type SavedReport = Omit<
  SavedReportRead,
  keyof ReportDefinition
> & ReportDefinition;

const throwing = { throwOnError: true } as const;

export function listRuns({ limit, offset, search }: PageQuery) {
  return sdkListRuns({ query: { limit, offset, search }, ...throwing }).then(
    materializeRunPage,
  );
}

export async function listProjectRuns({ limit, offset, projectId, search }: ProjectPageQuery) {
  return materializeRunPage(await sdkListProjectRuns({
    path: { project_id: projectId },
    query: { limit, offset, search },
    ...throwing,
  }));
}

export async function listProjectSamples({ limit, offset, projectId, search }: ProjectPageQuery) {
  return zSamplePageRead.parse(await sdkListProjectSamples({
    path: { project_id: projectId },
    query: { limit, offset, search },
    ...throwing,
  }));
}

export const listProjects = async () =>
  z.array(zProjectRead).parse(await sdkListProjects(throwing));
export const getProject = async (projectId: string) =>
  zProjectRead.parse(await sdkGetProject({ path: { project_id: projectId }, ...throwing }));
export const getProjectSample = (projectId: string, sampleId: string) =>
  sdkGetProjectSample({
    path: { project_id: projectId, sample_id: sampleId },
    ...throwing,
  });
export const listProjectSampleRuns = (projectId: string, sampleId: string) =>
  sdkListProjectSampleRuns({
    path: { project_id: projectId, sample_id: sampleId },
    ...throwing,
  });
export const listProjectSampleRunMetrics = (
  projectId: string,
  sampleId: string,
  runId: string,
) =>
  listProjectSampleRunAnalyticsMetrics({
    path: { project_id: projectId, sample_id: sampleId, run_id: runId },
    ...throwing,
  });
export const createProject = (body: { name: string; slug?: string; description?: string }) =>
  sdkCreateProject({ body, ...throwing });
export const patchProject = (projectId: string, body: ProjectPatch) =>
  sdkPatchProject({ path: { project_id: projectId }, body, ...throwing });
export const searchSamples = ({ projectId, query }: { projectId?: string; query: string }) =>
  sdkSearchSamples({ query: { project_id: projectId, q: query }, ...throwing });
export const askAi = async ({ conversationId, messages, projectId }: {
  conversationId?: string | null;
  messages: AiMessage[];
  projectId?: string;
}) => materializeChatResult(await sdkChatWithAi({
  body: { conversation_id: conversationId, messages, project_id: projectId },
  ...throwing,
}));
export const getProjectRun = async (projectId: string, runId: string) =>
  materializeRun(await sdkGetProjectRun({ path: { project_id: projectId, run_id: runId }, ...throwing }));
export const listProjectRunFiles = async (projectId: string, runId: string) =>
  z.array(zFileRead).parse(await sdkListProjectRunFiles({ path: { project_id: projectId, run_id: runId }, ...throwing }));
export const listProjectRunMetrics = (projectId: string, runId: string) =>
  listProjectRunAnalyticsMetrics({ path: { project_id: projectId, run_id: runId }, ...throwing });
export const listProjectRunPayloads = (projectId: string, runId: string) =>
  listProjectRunAnalyticsPayloads({ path: { project_id: projectId, run_id: runId }, ...throwing });
export const getDatabaseSummary = () => sdkGetDatabaseSummary(throwing);
export const getProjectDatabaseSummary = (projectId: string) =>
  sdkGetDatabaseSummary({ query: { project_id: projectId }, ...throwing });
export const listProjectDatabaseTables = async (projectId: string) =>
  materializeTables(await sdkListDatabaseTables({ query: { project_id: projectId }, ...throwing }));
export const listProjectDataContracts = async (projectId: string) =>
  materializeContracts(await sdkListDataContracts({ query: { project_id: projectId }, ...throwing }));
export const getContractResultOptions = (projectId: string, dataContractId: string) =>
  sdkGetContractResultOptions({
    path: { data_contract_id: dataContractId },
    query: { project_id: projectId },
    ...throwing,
  });
export const getInsightCapabilities = () => sdkGetInsightCapabilities(throwing);
export const validateInsightConfig = (body: InsightDraft & { project_id?: string }) =>
  sdkValidateInsightConfig({ body, ...throwing });
export const listSampleGroups = async (projectId: string, kind?: string) =>
  z.array(zSampleGroupRead).parse(
    await sdkListSampleGroups({ query: { project_id: projectId, kind }, ...throwing }),
  );

export async function listProjectSampleGroups({ kind, limit, offset, projectId, search }: ProjectPageQuery & { kind?: string }) {
  return zSampleGroupPageRead.parse(await sdkListProjectSampleGroups({
    path: { project_id: projectId },
    query: { kind, limit, offset, search },
    ...throwing,
  }));
}

export const createProjectSampleGroup = (
  projectId: string,
  body: { description?: string | null; kind?: string; name: string; sample_ids?: string[] },
) => sdkCreateProjectSampleGroup({ path: { project_id: projectId }, body, ...throwing })
  .then(materializeSampleGroup);
export const getProjectSampleGroup = (projectId: string, sampleGroupRef: string) =>
  sdkGetProjectSampleGroup({
    path: { project_id: projectId, sample_group_id: sampleGroupRef },
    ...throwing,
  }).then(materializeSampleGroup);
export const patchProjectSampleGroup = (
  projectId: string,
  sampleGroupId: string,
  body: SampleGroupPatch,
) => sdkPatchProjectSampleGroup({
  path: { project_id: projectId, sample_group_id: sampleGroupId }, body, ...throwing,
}).then(materializeSampleGroup);
export const deleteProjectSampleGroup = (projectId: string, sampleGroupId: string) =>
  sdkDeleteProjectSampleGroup({
    path: { project_id: projectId, sample_group_id: sampleGroupId }, ...throwing,
  });
export function listProjectSampleGroupMembers({ limit, offset, projectId, sampleGroupId, search }: ProjectPageQuery & { sampleGroupId: string }) {
  return sdkListProjectSampleGroupMembers({
    path: { project_id: projectId, sample_group_id: sampleGroupId },
    query: { limit, offset, search },
    ...throwing,
  });
}
export const addProjectSampleGroupMembers = (projectId: string, sampleGroupId: string, sampleIds: string[]) =>
  sdkAddProjectSampleGroupMembers({
    path: { project_id: projectId, sample_group_id: sampleGroupId },
    body: { sample_ids: sampleIds }, ...throwing,
  }).then(materializeSampleGroup);
export const removeProjectSampleGroupMembers = (projectId: string, sampleGroupId: string, runSampleIds: string[]) =>
  sdkRemoveProjectSampleGroupMembers({
    path: { project_id: projectId, sample_group_id: sampleGroupId },
    body: { run_sample_ids: runSampleIds }, ...throwing,
  }).then(materializeSampleGroup);
export const getProjectDataContract = (projectId: string, dataContractId: string) =>
  sdkGetDataContract({ path: { data_contract_id: dataContractId }, query: { project_id: projectId }, ...throwing })
    .then(materializeContract);
export function previewProjectDatabaseTable({ projectId, store, table, limit, offset, sortBy, sortDirection }: {
  projectId: string; store: DatabaseTable["store"]; table: string; limit: number; offset: number;
  sortBy?: string | null; sortDirection?: "asc" | "desc" | null;
}) {
  return sdkPreviewDatabaseTable({
    path: { store, table_name: table },
    query: { project_id: projectId, limit, offset, sort_by: sortBy ?? undefined, sort_direction: sortDirection ?? undefined },
    ...throwing,
  }).then((value) => zDatabaseTablePageRead.parse(value));
}

export const listInsights = (projectId: string) =>
  sdkListInsights({ query: { project_id: projectId }, ...throwing });
export async function getInsight(insightId: string): Promise<SavedInsight> {
  const saved = await sdkGetInsight({ path: { insight_ref: insightId }, ...throwing });
  return { ...saved, ...savedInsightToDraft(saved) };
}
export const createInsight = (payload: InsightDraft & { insight_id?: string; project_id: string; name: string; description?: string | null }) =>
  sdkCreateInsight({ body: insightDraftToCreate(payload, payload), ...throwing });
export const patchInsight = (insightId: string, payload: SavedInsightPatch & InsightDraft) =>
  sdkPatchInsight({ path: { insight_ref: insightId }, body: insightDraftToPatch(payload, payload), ...throwing });
export const deleteInsight = (insightId: string) =>
  sdkDeleteInsight({ path: { insight_ref: insightId }, ...throwing });
export async function executeInsight({ insightId, projectId, config, name, description, limit, random, exportResult, refresh }: {
  insightId?: string; projectId: string; config?: InsightDraft; name?: string; description?: string | null;
  limit?: number; random?: boolean; exportResult?: boolean; refresh?: boolean;
}) {
  const body = { ...(config ?? {}), project_id: projectId, name, description, limit, random, export: exportResult, refresh: Boolean(refresh) };
  const response = insightId
    ? await executeSavedInsight({ path: { insight_ref: insightId }, body, ...throwing })
    : await executeAdhocInsight({ body, ...throwing });
  return response.result;
}

export const listReports = (projectId: string) =>
  sdkListReports({ query: { project_id: projectId }, ...throwing });
export async function getReport(reportId: string): Promise<SavedReport> {
  const saved = await getSavedReport({ path: { report_ref: reportId }, ...throwing });
  return { ...saved, ...savedReportToDraft(saved) } as SavedReport;
}
export const createReport = (payload: ReportDefinition & { project_id: string }) =>
  sdkCreateReport({ body: reportDraftToCreate(payload, payload.project_id), ...throwing });
export const validateReportConfig = (body: ReportDefinition & { project_id: string }) =>
  sdkValidateReportConfig({ body, ...throwing });
export const patchReport = (reportId: string, payload: Partial<ReportDefinition>) =>
  sdkPatchReport({ path: { report_ref: reportId }, body: reportDraftToPatch(payload), ...throwing });
export const deleteReport = (reportId: string) =>
  sdkDeleteReport({ path: { report_ref: reportId }, ...throwing });
export async function executeReport({ reportId, projectId, limit, random, refresh }: {
  reportId: string; projectId: string; limit?: number; random?: boolean; refresh?: boolean;
}) {
  const response = await executeSavedReport({
    path: { report_ref: reportId },
    body: { project_id: projectId, limit, random, refresh: Boolean(refresh) },
    ...throwing,
  });
  return response.result;
}

export const listUsers = () => sdkListUsers(throwing);
export const listProjectRoles = (projectId: string) =>
  sdkListRoles({ path: { project_id: projectId }, ...throwing });
export const listProjectMembers = (projectId: string) =>
  sdkListMembers({ path: { project_id: projectId }, ...throwing });
export const listUserMemberships = (userId: string) =>
  sdkListUserMemberships({ path: { user_id: userId }, ...throwing });
export const addProjectMember = (projectId: string, userId: string, roleId: string) =>
  sdkAddMember({ path: { project_id: projectId }, body: { user_id: userId, role_id: roleId }, ...throwing });
export const updateProjectMember = (projectId: string, membershipId: string, roleId: string) =>
  sdkPatchMember({ path: { project_id: projectId, membership_id: membershipId }, body: { role_id: roleId }, ...throwing });
export const deleteProjectMember = (projectId: string, membershipId: string) =>
  sdkDeleteMember({ path: { project_id: projectId, membership_id: membershipId }, ...throwing });
export const updateProjectRole = (projectId: string, roleId: string, permissions: string[]) =>
  sdkPatchRole({ path: { project_id: projectId, role_id: roleId }, body: { permissions }, ...throwing });
export const changePassword = (currentPassword: string, newPassword: string) =>
  sdkChangePassword({ body: { current_password: currentPassword, new_password: newPassword }, ...throwing });
export const createInstallationUser = (payload: { email: string; password: string; display_name?: string }) =>
  sdkAddUser({ body: { ...payload, must_change_password: true }, ...throwing });
export const setInstallationUserActive = (userId: string, isActive: boolean) =>
  sdkPatchUser({ path: { user_id: userId }, body: { is_active: isActive }, ...throwing });
export const patchInstallationUser = (userId: string, body: UserPatchRequest) =>
  sdkPatchUser({ path: { user_id: userId }, body, ...throwing });

type PageQuery = { limit: number; offset: number; search?: string };
type ProjectPageQuery = PageQuery & { projectId: string };

export type { ContractResultOptionsRead };

function materializeRun(value: Run): GoodomicsRun {
  const run = zRun.parse(value);
  if (!run.created_at) throw new Error("Run response omitted created_at");
  return { ...run, created_at: run.created_at, samples: run.samples ?? [] };
}

function materializeRunPage(value: RunPageRead): RunsPage {
  const page = zRunPageRead.parse(value);
  return { ...page, items: page.items.map(materializeRun) };
}

function materializeTables(values: DatabaseTableRead[]): DatabaseTable[] {
  return values.map((value) => {
    const table = zDatabaseTableRead.parse(value);
    return { ...table, columns: table.columns ?? [] };
  });
}

function materializeContractField(value: DataContractFieldRead): DataContractField {
  const field = zDataContractFieldRead.parse(value);
  return {
    ...field,
    metadata_json: field.metadata_json ?? {},
    physical_tables: field.physical_tables ?? {},
    query_ref: field.query_ref ?? {},
    summary: field.summary ?? {},
  } as DataContractField;
}

function materializeContract(value: DataContractRead): DataContract {
  const contract = zDataContractRead.parse(value);
  return {
    ...contract,
    fields: (contract.fields ?? []).map(materializeContractField),
  } as DataContract;
}

function materializeContracts(values: DataContractRead[]): DataContract[] {
  return values.map(materializeContract);
}

function materializeChatResult(value: ChatResult): AiChatResponse {
  const result = zChatResult.parse(value);
  return {
    ...result,
    conversation_id: result.conversation_id ?? null,
    tool_calls: result.tool_calls ?? [],
  };
}

function materializeSampleGroup(value: SampleGroupRead): SampleGroup {
  return zSampleGroupRead.parse(value);
}

import { z } from "zod";

export const passwordPolicySchema = z.object({
  min_length: z.number().int().positive(),
  max_length: z.number().int().positive().nullable(),
  require_uppercase: z.boolean(),
  require_lowercase: z.boolean(),
  require_number: z.boolean(),
  require_symbol: z.boolean(),
});

export type PasswordPolicy = z.infer<typeof passwordPolicySchema>;

export const DEFAULT_PASSWORD_POLICY: PasswordPolicy = {
  min_length: 6,
  max_length: null,
  require_uppercase: false,
  require_lowercase: false,
  require_number: false,
  require_symbol: false,
};

/** Human-readable summary shared by setup and account-management forms. */
export function describePasswordPolicy(policy: PasswordPolicy) {
  const length = policy.max_length
    ? `Use ${policy.min_length}–${policy.max_length} characters.`
    : `Use at least ${policy.min_length} characters.`;
  const composition = [
    policy.require_uppercase && "an uppercase letter",
    policy.require_lowercase && "a lowercase letter",
    policy.require_number && "a number",
    policy.require_symbol && "a symbol",
  ].filter((value): value is string => Boolean(value));
  if (composition.length === 0) return length;
  const last = composition.at(-1)!;
  const leading = composition.slice(0, -1);
  const list = leading.length ? `${leading.join(", ")} and ${last}` : last;
  return `${length} Include ${list}.`;
}

/** Cheap client-side eligibility check; the server remains authoritative. */
export function passwordMeetsPolicy(password: string, policy: PasswordPolicy) {
  if (password.length < policy.min_length) return false;
  if (policy.max_length !== null && password.length > policy.max_length) return false;
  if (policy.require_uppercase && !/\p{Lu}/u.test(password)) return false;
  if (policy.require_lowercase && !/\p{Ll}/u.test(password)) return false;
  if (policy.require_number && !/\p{N}/u.test(password)) return false;
  if (policy.require_symbol && !/[^\p{L}\p{N}\s]/u.test(password)) return false;
  return true;
}

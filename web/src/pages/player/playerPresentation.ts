/** Build a React Router path for a contest history row. */
export function contestHref(contestId: string): string {
  return `/contest/${encodeURIComponent(contestId)}`
}

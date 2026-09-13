const MIN_INDEX_QUERY_LENGTH = 2

export function shouldLoadSearchIndexes(open: boolean, query: string): boolean {
  return open && query.trim().length >= MIN_INDEX_QUERY_LENGTH
}

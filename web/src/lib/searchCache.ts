/**
 * LRU cache for search results to optimize repeated queries.
 * 
 * This cache stores search results with a configurable capacity, evicting
 * least-recently-used entries when the capacity is exceeded.
 */

export class SearchLRUCache<T> {
  private capacity: number
  private cache: Map<string, T>

  constructor(capacity = 100) {
    this.capacity = capacity
    this.cache = new Map()
  }

  /**
   * Get a value from the cache. Returns undefined if not found.
   * Moves the accessed entry to the end (most recently used).
   */
  get(key: string): T | undefined {
    const value = this.cache.get(key)
    if (value !== undefined) {
      // Refresh the entry by deleting and re-adding (moves to end)
      this.cache.delete(key)
      this.cache.set(key, value)
    }
    return value
  }

  /**
   * Set a value in the cache.
   * If at capacity, removes the least-recently-used entry first.
   */
  set(key: string, value: T): void {
    // If key exists, delete it first to refresh position
    if (this.cache.has(key)) {
      this.cache.delete(key)
    } else if (this.cache.size >= this.capacity) {
      // Remove the first (oldest) entry
      const firstKey = this.cache.keys().next().value
      if (firstKey !== undefined) {
        this.cache.delete(firstKey)
      }
    }
    this.cache.set(key, value)
  }

  /**
   * Clear all entries from the cache.
   */
  clear(): void {
    this.cache.clear()
  }

  /**
   * Get the current size of the cache.
   */
  size(): number {
    return this.cache.size
  }
}

/**
 * Global singleton cache for player search results.
 * Keyed by query string, stores PlayerSearchEntry arrays.
 */
export const searchCache = new SearchLRUCache<unknown>(100)

/*
 * Minimal MD5 implementation (RFC 1321), UTF-8 aware.
 *
 * Why hand-rolled: the player shard is `md5(key)` first 2 hex chars, computed by
 * the Python exporter as `hashlib.md5(key.encode("utf-8")).hexdigest()[:2]`.
 * The browser SubtleCrypto digest API does not offer MD5, so we need a small,
 * dependency-free implementation that produces a byte-identical hex digest for
 * the same UTF-8 input. Used only for shard routing, never for security.
 */

function toUtf8Bytes(str: string): number[] {
  const bytes: number[] = []
  for (let i = 0; i < str.length; i++) {
    let code = str.charCodeAt(i)
    if (code < 0x80) {
      bytes.push(code)
    } else if (code < 0x800) {
      bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f))
    } else if (code >= 0xd800 && code <= 0xdbff) {
      // High surrogate: combine with the following low surrogate.
      const hi = code
      const lo = str.charCodeAt(++i)
      code = 0x10000 + ((hi - 0xd800) << 10) + (lo - 0xdc00)
      bytes.push(
        0xf0 | (code >> 18),
        0x80 | ((code >> 12) & 0x3f),
        0x80 | ((code >> 6) & 0x3f),
        0x80 | (code & 0x3f),
      )
    } else {
      bytes.push(
        0xe0 | (code >> 12),
        0x80 | ((code >> 6) & 0x3f),
        0x80 | (code & 0x3f),
      )
    }
  }
  return bytes
}

function add32(a: number, b: number): number {
  return (a + b) & 0xffffffff
}

function rol(value: number, shift: number): number {
  return (value << shift) | (value >>> (32 - shift))
}

function cmn(
  q: number,
  a: number,
  b: number,
  x: number,
  s: number,
  t: number,
): number {
  return add32(rol(add32(add32(a, q), add32(x, t)), s), b)
}

function ff(a: number, b: number, c: number, d: number, x: number, s: number, t: number) {
  return cmn((b & c) | (~b & d), a, b, x, s, t)
}
function gg(a: number, b: number, c: number, d: number, x: number, s: number, t: number) {
  return cmn((b & d) | (c & ~d), a, b, x, s, t)
}
function hh(a: number, b: number, c: number, d: number, x: number, s: number, t: number) {
  return cmn(b ^ c ^ d, a, b, x, s, t)
}
function ii(a: number, b: number, c: number, d: number, x: number, s: number, t: number) {
  return cmn(c ^ (b | ~d), a, b, x, s, t)
}

function toHex(num: number): string {
  let hex = ''
  for (let i = 0; i < 4; i++) {
    hex += ((num >> (i * 8)) & 0xff).toString(16).padStart(2, '0')
  }
  return hex
}

export function md5Hex(input: string): string {
  const bytes = toUtf8Bytes(input)
  const bitLen = bytes.length * 8

  // Padding: 0x80, then zeros up to 56 mod 64, then 64-bit length (LE).
  // The 64-bit length is split into low/high 32-bit words. We must NOT use a
  // shift count >= 32 on a single value: JS shift counts are taken mod 32, so
  // `bitLen >>> 32` would alias back to `bitLen >>> 0` and re-emit the low bits.
  bytes.push(0x80)
  while (bytes.length % 64 !== 56) bytes.push(0)
  const lowWord = bitLen >>> 0
  // Math.floor keeps this exact for the message sizes we deal with.
  const highWord = Math.floor(bitLen / 0x100000000) >>> 0
  for (let i = 0; i < 4; i++) {
    bytes.push((lowWord >>> (i * 8)) & 0xff)
  }
  for (let i = 0; i < 4; i++) {
    bytes.push((highWord >>> (i * 8)) & 0xff)
  }

  let a = 0x67452301
  let b = 0xefcdab89
  let c = 0x98badcfe
  let d = 0x10325476

  for (let chunk = 0; chunk < bytes.length; chunk += 64) {
    const x = new Array<number>(16)
    for (let i = 0; i < 16; i++) {
      const o = chunk + i * 4
      x[i] =
        bytes[o] |
        (bytes[o + 1] << 8) |
        (bytes[o + 2] << 16) |
        (bytes[o + 3] << 24)
    }

    const aa = a
    const bb = b
    const cc = c
    const dd = d

    a = ff(a, b, c, d, x[0], 7, 0xd76aa478)
    d = ff(d, a, b, c, x[1], 12, 0xe8c7b756)
    c = ff(c, d, a, b, x[2], 17, 0x242070db)
    b = ff(b, c, d, a, x[3], 22, 0xc1bdceee)
    a = ff(a, b, c, d, x[4], 7, 0xf57c0faf)
    d = ff(d, a, b, c, x[5], 12, 0x4787c62a)
    c = ff(c, d, a, b, x[6], 17, 0xa8304613)
    b = ff(b, c, d, a, x[7], 22, 0xfd469501)
    a = ff(a, b, c, d, x[8], 7, 0x698098d8)
    d = ff(d, a, b, c, x[9], 12, 0x8b44f7af)
    c = ff(c, d, a, b, x[10], 17, 0xffff5bb1)
    b = ff(b, c, d, a, x[11], 22, 0x895cd7be)
    a = ff(a, b, c, d, x[12], 7, 0x6b901122)
    d = ff(d, a, b, c, x[13], 12, 0xfd987193)
    c = ff(c, d, a, b, x[14], 17, 0xa679438e)
    b = ff(b, c, d, a, x[15], 22, 0x49b40821)

    a = gg(a, b, c, d, x[1], 5, 0xf61e2562)
    d = gg(d, a, b, c, x[6], 9, 0xc040b340)
    c = gg(c, d, a, b, x[11], 14, 0x265e5a51)
    b = gg(b, c, d, a, x[0], 20, 0xe9b6c7aa)
    a = gg(a, b, c, d, x[5], 5, 0xd62f105d)
    d = gg(d, a, b, c, x[10], 9, 0x02441453)
    c = gg(c, d, a, b, x[15], 14, 0xd8a1e681)
    b = gg(b, c, d, a, x[4], 20, 0xe7d3fbc8)
    a = gg(a, b, c, d, x[9], 5, 0x21e1cde6)
    d = gg(d, a, b, c, x[14], 9, 0xc33707d6)
    c = gg(c, d, a, b, x[3], 14, 0xf4d50d87)
    b = gg(b, c, d, a, x[8], 20, 0x455a14ed)
    a = gg(a, b, c, d, x[13], 5, 0xa9e3e905)
    d = gg(d, a, b, c, x[2], 9, 0xfcefa3f8)
    c = gg(c, d, a, b, x[7], 14, 0x676f02d9)
    b = gg(b, c, d, a, x[12], 20, 0x8d2a4c8a)

    a = hh(a, b, c, d, x[5], 4, 0xfffa3942)
    d = hh(d, a, b, c, x[8], 11, 0x8771f681)
    c = hh(c, d, a, b, x[11], 16, 0x6d9d6122)
    b = hh(b, c, d, a, x[14], 23, 0xfde5380c)
    a = hh(a, b, c, d, x[1], 4, 0xa4beea44)
    d = hh(d, a, b, c, x[4], 11, 0x4bdecfa9)
    c = hh(c, d, a, b, x[7], 16, 0xf6bb4b60)
    b = hh(b, c, d, a, x[10], 23, 0xbebfbc70)
    a = hh(a, b, c, d, x[13], 4, 0x289b7ec6)
    d = hh(d, a, b, c, x[0], 11, 0xeaa127fa)
    c = hh(c, d, a, b, x[3], 16, 0xd4ef3085)
    b = hh(b, c, d, a, x[6], 23, 0x04881d05)
    a = hh(a, b, c, d, x[9], 4, 0xd9d4d039)
    d = hh(d, a, b, c, x[12], 11, 0xe6db99e5)
    c = hh(c, d, a, b, x[15], 16, 0x1fa27cf8)
    b = hh(b, c, d, a, x[2], 23, 0xc4ac5665)

    a = ii(a, b, c, d, x[0], 6, 0xf4292244)
    d = ii(d, a, b, c, x[7], 10, 0x432aff97)
    c = ii(c, d, a, b, x[14], 15, 0xab9423a7)
    b = ii(b, c, d, a, x[5], 21, 0xfc93a039)
    a = ii(a, b, c, d, x[12], 6, 0x655b59c3)
    d = ii(d, a, b, c, x[3], 10, 0x8f0ccc92)
    c = ii(c, d, a, b, x[10], 15, 0xffeff47d)
    b = ii(b, c, d, a, x[1], 21, 0x85845dd1)
    a = ii(a, b, c, d, x[8], 6, 0x6fa87e4f)
    d = ii(d, a, b, c, x[15], 10, 0xfe2ce6e0)
    c = ii(c, d, a, b, x[6], 15, 0xa3014314)
    b = ii(b, c, d, a, x[13], 21, 0x4e0811a1)
    a = ii(a, b, c, d, x[4], 6, 0xf7537e82)
    d = ii(d, a, b, c, x[11], 10, 0xbd3af235)
    c = ii(c, d, a, b, x[2], 15, 0x2ad7d2bb)
    b = ii(b, c, d, a, x[9], 21, 0xeb86d391)

    a = add32(a, aa)
    b = add32(b, bb)
    c = add32(c, cc)
    d = add32(d, dd)
  }

  return toHex(a) + toHex(b) + toHex(c) + toHex(d)
}

/** Shard a player key the same way the Python exporter does. */
export function shardForKey(key: string): string {
  return md5Hex(key).slice(0, 2)
}

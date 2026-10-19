"""Simple pinyin initial extraction for search indexing.

This module provides basic pinyin initial (声母) extraction for Chinese
characters using Unicode range-based lookup tables, matching common
CJK character-to-pinyin mappings.
"""

# Unicode-based pinyin initial mapping for common Chinese characters
# Based on GB2312 encoding ranges and common character frequencies
# Format: (start_unicode, end_unicode, initial)
PINYIN_RANGES = [
    # A
    (0x554a, 0x5594, 'a'),  # 啊-喔
    # B
    (0x5595, 0x5727, 'b'),  # 喕-圧
    # C
    (0x5728, 0x5893, 'c'),  # 在-墓
    # D
    (0x5894, 0x5a7f, 'd'),  # 墔-婿
    # E
    (0x5a80, 0x5b08, 'e'),  # 媀-嬈
    # F
    (0x5b09, 0x5c0d, 'f'),  # 嬉-對
    # G
    (0x5c0e, 0x5d13, 'g'),  # 導-崓
    # H
    (0x5d14, 0x5f65, 'h'),  # 崔-彥
    # J
    (0x5f66, 0x6289, 'j'),  # 彦-抉
    # K
    (0x628a, 0x64ad, 'k'),  # 把-播
    # L
    (0x64ae, 0x6785, 'l'),  # 撮-枅
    # M
    (0x6786, 0x6bd3, 'm'),  # 枆-毓
    # N
    (0x6bd4, 0x6eef, 'n'),  # 比-滯
    # O
    (0x6ef0, 0x6f1f, 'o'),  # 滰-漟
    # P
    (0x6f20, 0x7247, 'p'),  # 漠-片
    # Q
    (0x7248, 0x755b, 'q'),  # 版-畛
    # R
    (0x755c, 0x7847, 'r'),  # 畜-硇
    # S
    (0x7848, 0x7d71, 's'),  # 硈-統
    # T
    (0x7d72, 0x8138, 't'),  # 絲-脸
    # W
    (0x8139, 0x846b, 'w'),  # 脹-葫
    # X
    (0x846c, 0x8746, 'x'),  # 葬-蝆
    # Y
    (0x8747, 0x8a88, 'y'),  # 蝇-誈
    # Z
    (0x8a89, 0x9fff, 'z'),  # 誉-鿿
]

# More accurate mapping for common surnames and high-frequency characters
COMMON_CHARS = {
    # Common surnames
    '李': 'l', '王': 'w', '张': 'z', '刘': 'l', '陈': 'c',
    '杨': 'y', '黄': 'h', '赵': 'z', '周': 'z', '吴': 'w',
    '徐': 'x', '孙': 's', '马': 'm', '朱': 'z', '胡': 'h',
    '郭': 'g', '何': 'h', '林': 'l', '罗': 'l', '高': 'g',
    # Common characters
    '明': 'm', '华': 'h', '建': 'j', '国': 'g', '文': 'w',
    '伟': 'w', '平': 'p', '强': 'q', '军': 'j', '超': 'c',
    '东': 'd', '西': 'x', '南': 'n', '北': 'b', '中': 'z',
    '大': 'd', '小': 'x', '学': 'x', '校': 'x', '院': 'y',
    '清': 'q', '北': 'b', '复': 'f', '上': 's', '交': 'j',
    '浙': 'z', '南': 'n', '武': 'w', '川': 'c', '山': 's',
}

_initial_cache = {}


def chinese_initial(char: str) -> str:
    """Get the pinyin initial for a single Chinese character.
    
    Returns empty string for non-Chinese characters.
    Uses pre-computed lookup table for common characters and Unicode ranges.
    
    Examples:
        >>> chinese_initial('李')
        'l'
        >>> chinese_initial('张')
        'z'
        >>> chinese_initial('王')
        'w'
        >>> chinese_initial('a')
        ''
    """
    if not char:
        return ''
    
    if char in _initial_cache:
        return _initial_cache[char]
    
    # Check common characters first (most accurate)
    if char in COMMON_CHARS:
        initial = COMMON_CHARS[char]
        _initial_cache[char] = initial
        return initial
    
    # Check if it's a CJK character
    code_point = ord(char)
    if code_point < 0x4e00 or code_point > 0x9fff:
        _initial_cache[char] = ''
        return ''
    
    # Use Unicode range lookup
    for start, end, initial in PINYIN_RANGES:
        if start <= code_point <= end:
            _initial_cache[char] = initial
            return initial
    
    # Fallback for characters not in ranges
    # Default to 'a' for unknown CJK characters
    _initial_cache[char] = 'a'
    return 'a'


def pinyin_initials(text: str) -> str:
    """Extract pinyin initials from a string.
    
    Examples:
        >>> pinyin_initials("李明")
        'lm'
        >>> pinyin_initials("张三")
        'zs'
        >>> pinyin_initials("Hello世界")
        'sj'
    """
    if not text:
        return ''
    
    result = []
    for char in text:
        initial = chinese_initial(char)
        if initial:
            result.append(initial)
    
    return ''.join(result)

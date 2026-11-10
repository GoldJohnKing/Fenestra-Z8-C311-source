"""Prevent plugin text from relying on Han absent from the stock menu subset."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
from z8_chinese_text import audit_sources, decode_c_string, load_safe_han, unsupported_han

SOURCES = [
    'examples/prores/module.c',
    'examples/h265/module.c', 'examples/log_colour/module.c',
    'examples/video_setting/module.inc', 'examples/framing/module.c',
    'modules/photo_tools/module.c',
]


class Z8ChineseTextTests(unittest.TestCase):
    def test_stock_subset_and_reported_missing_character(self):
        safe = load_safe_han()
        self.assertEqual(len(safe), 797)
        self.assertEqual(unsupported_han('就绪', safe), [0x7eea])
        self.assertEqual(unsupported_han('准备完成', safe), [])
        self.assertEqual(unsupported_han('功能未准备完成', safe), [])
        self.assertEqual(unsupported_han('\U00020bb7', safe), [0x20bb7])

    def test_actual_frontend_literal_vocabulary_and_field_bounds(self):
        rows = audit_sources([ROOT / p for p in SOURCES])
        self.assertGreater(len(rows), 50)
        self.assertEqual([r for r in rows if r['unsupported_han']], [])
        self.assertLessEqual(max(r['utf8_bytes_with_nul'] for r in rows), 48)
        self.assertLessEqual(max(r['utf16_units_with_nul'] for r in rows), 48)

    def test_c_execution_byte_decoding_handles_utf8_and_universal_escapes(self):
        self.assertEqual(decode_c_string(r'"\xe5\xb0\xb1\xe7\xbb\xaa"'), '就绪')
        self.assertEqual(decode_c_string(r'"\u51c6\u5907\u5b8c\u6210"'), '准备完成')
        self.assertEqual(decode_c_string(r'"A\"B\nC"'), 'A"B\nC')


if __name__ == '__main__':
    unittest.main()

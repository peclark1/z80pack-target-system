import unittest

from gui.front_panel import console_name, parse_hex_byte, switch_states, value_from_states


class FrontPanelTests(unittest.TestCase):
    def test_hex_byte_parser(self):
        self.assertEqual(parse_hex_byte("00"), 0x00)
        self.assertEqual(parse_hex_byte("a5"), 0xA5)
        self.assertEqual(parse_hex_byte("FF"), 0xFF)
        with self.assertRaises(ValueError):
            parse_hex_byte("100")
        with self.assertRaises(ValueError):
            parse_hex_byte("ZZ")

    def test_switch_round_trip(self):
        for value in (0x00, 0x01, 0x02, 0x55, 0xA5, 0xFF):
            self.assertEqual(value_from_states(switch_states(value)), value)

    def test_console_decode_uses_low_two_bits(self):
        self.assertEqual(console_name(0x00), "Console I/O")
        self.assertEqual(console_name(0x01), "Serial I/O A")
        self.assertEqual(console_name(0x02), "MIO SIO")
        self.assertIn("fallback", console_name(0x03).lower())
        self.assertEqual(console_name(0x82), "MIO SIO")


if __name__ == "__main__":
    unittest.main()

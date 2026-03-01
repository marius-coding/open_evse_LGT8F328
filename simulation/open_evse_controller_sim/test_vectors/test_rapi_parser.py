import unittest

from open_evse_controller_sim.rapi_parser import (
    RapiStreamParser,
    append_xor_checksum,
    build_response,
    parse_frame,
)


class TestRapiParser(unittest.TestCase):
    def test_parse_xor_checksum_with_sequence(self) -> None:
        frame = "$GV :7A^59\r"
        parsed = parse_frame(frame)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.token, "GV")
        self.assertEqual(parsed.args, ())
        self.assertEqual(parsed.sequence_id, 0x7A)
        self.assertEqual(parsed.checksum_type, "xor")

    def test_parse_invalid_checksum(self) -> None:
        self.assertIsNone(parse_frame("$GV^00\r"))

    def test_parse_additive_checksum(self) -> None:
        self.assertIsNotNone(parse_frame("$FD*AE\r"))

    def test_parse_without_checksum(self) -> None:
        parsed = parse_frame("$GS\r")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.token, "GS")
        self.assertEqual(parsed.checksum_type, "none")

    def test_stream_parser_framing(self) -> None:
        parser = RapiStreamParser()
        out = parser.feed("noise$GV^35\r$FD*AE\rjunk")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].token, "GV")
        self.assertEqual(out[1].token, "FD")

    def test_response_builder(self) -> None:
        resp = build_response(True, "5.2.1-LGT", 0x11)
        self.assertEqual(resp, "$OK 5.2.1-LGT :11^5E\r")

    def test_append_xor_checksum(self) -> None:
        self.assertEqual(append_xor_checksum("$AB 01 FW"), "$AB 01 FW^37\r")


if __name__ == "__main__":
    unittest.main()

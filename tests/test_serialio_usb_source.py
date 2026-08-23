import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMIO = ROOT / "emulator" / "srcsim" / "simio.c"
DEVICE = ROOT / "emulator" / "srcsim" / "target-serialio-usb.c"
PREPARE = ROOT / "scripts" / "prepare-targetsim.sh"
MAKEFILE = ROOT / "Makefile"


class SerialIoUsbSourceTests(unittest.TestCase):
    def test_host_link_ports_are_mapped(self):
        text = SIMIO.read_text(encoding="utf-8")
        self.assertIn("[0xaa] = target_serialio_usb_status_in", text)
        self.assertIn("[0xac] = target_serialio_usb_data_in", text)
        self.assertIn("[0xac] = target_serialio_usb_data_out", text)

    def test_active_low_handshake_bits_match_serial_io_board(self):
        text = DEVICE.read_text(encoding="utf-8")
        self.assertIn("#define RX_READY_MASK 0x80", text)
        self.assertIn("#define TX_READY_MASK 0x40", text)
        self.assertIn("status &= (BYTE) ~TX_READY_MASK", text)
        self.assertIn("status &= (BYTE) ~RX_READY_MASK", text)

    def test_device_uses_stable_pty_endpoint(self):
        text = DEVICE.read_text(encoding="utf-8")
        self.assertIn("posix_openpt", text)
        self.assertIn("/tmp/targets100sim-usb-%lu", text)
        self.assertIn("TARGET_SERIALIO_USB_TTY", text)

    def test_device_is_part_of_generated_target(self):
        prepare = PREPARE.read_text(encoding="utf-8")
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("target-serialio-usb.c", prepare)
        self.assertIn("target-serialio-usb.c", makefile)
        self.assertIn("target-serialio-usb.h", makefile)


if __name__ == "__main__":
    unittest.main()

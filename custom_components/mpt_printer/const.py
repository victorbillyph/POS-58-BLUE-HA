"""Constants for the MPT-II Bluetooth Printer integration."""

DOMAIN = "mpt_printer"

MANUFACTURER = "Generic"
DEFAULT_NAME = "MPT-II Printer"

CONF_CONNECTION = "connection"
CONF_ADDRESS = "address"
CONF_SERIAL_PATH = "serial_path"
CONF_WIDTH = "width"

CONF_DEFAULT_ALIGN = "default_align"
CONF_DEFAULT_SIZE = "default_size"
CONF_DEFAULT_BOLD = "default_bold"
CONF_DEFAULT_FEED = "default_feed"
CONF_DEFAULT_CUT = "default_cut"

CONN_BLE = "ble"
CONN_SERIAL = "serial"
CONNECTIONS = {
    CONN_BLE: "Bluetooth (BLE)",
    CONN_SERIAL: "Serial device (/dev/rfcomm0)",
}

ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"
ALIGNS = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT]

SIZE_NORMAL = "normal"
SIZE_TALL = "tall"
SIZE_WIDE = "wide"
SIZE_DOUBLE = "double"
SIZES = [SIZE_NORMAL, SIZE_TALL, SIZE_WIDE, SIZE_DOUBLE]

DEFAULT_WIDTH = 32
DEFAULT_ALIGN = ALIGN_LEFT
DEFAULT_SIZE = SIZE_NORMAL
DEFAULT_BOLD = False
DEFAULT_FEED = 3
DEFAULT_CUT = False

BLE_CONNECT_TIMEOUT = 15.0
BLE_CHUNK_SIZE = 20
BLE_INTER_CHUNK_DELAY = 0.02

# Well-known ESC/POS-over-BLE characteristics on cheap thermal printers
KNOWN_WRITE_CHARS = [
    "0000ff02-0000-1000-8000-00805f9b34fb",
    "0000ff01-0000-1000-8000-00805f9b34fb",
    "49535343-8841-43f4-a8d4-ecbe34729bb3",
    "e7810a71-73ae-499d-8c15-faa9aef0c3f2",
]
KNOWN_SERVICE_UUIDS = [
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "49535343-fe7d-4ae5-8fa9-9fafd205e455",
    "e7810a71-73ae-499d-8c15-faa9aef0c3f2",
]

NAME_KEYWORDS = ("mpt", "print", "pos", "thermal", "receipt")

import os

import wasm_kegs


class Loader(wasm_kegs.PluginLoader):
    plugin_type = "kaithem.chandler.lighting-generator"


os.environ["WASMTIME_BACKTRACE_DETAILS"] = "1"


def test_plugin():
    ps = wasm_kegs.packages.PackageStore(
        [os.path.join(os.path.dirname(__file__), "../../../..")]
    )
    with ps:
        p = Loader("lighting-generator-fx:gradient-generator", {})

        # Ten green lights
        for i in range(10):
            pl = wasm_kegs.Payload(b"")
            pl.write_i64(i)  # ch num
            pl.write_i64(i)  # fixture
            pl.write_i64(2)  # g
            pl.write_bytes(b"")  # Extra data
            p.call_plugin("set_channel_metadata", pl.data)

            pl = wasm_kegs.Payload(b"")
            pl.write_i64(i)  # ch num
            pl.write_f32(-1000_001)  # g
            p.call_plugin("set_input_value", pl.data)

        pl = wasm_kegs.Payload(b"")
        pl.write_i64(10)  # ch num
        pl.write_i64(-1)  # fixture
        pl.write_i64(-1)  # g
        pl.write_bytes(b"")  # Extra data
        p.call_plugin("set_channel_metadata", pl.data)

        pl = wasm_kegs.Payload(b"")
        pl.write_i64(0)  # ch num
        pl.write_f32(100)  # g
        p.call_plugin("set_input_value", pl.data)

        pl = wasm_kegs.Payload(b"")
        pl.write_i64(9)  # ch num
        pl.write_f32(200)  # g
        p.call_plugin("set_input_value", pl.data)

        pl = wasm_kegs.Payload(b"")
        pl.write_i64(0)  # start
        pl.write_i64(10)  # len
        pl.write_i64(0)  # time

        x = p.call_plugin("process", pl.data)

        pl = wasm_kegs.Payload(x)
        ctr = 0

        start = 100
        end = 200
        while pl.data:
            expected = start + ((end - start) / 10) * ctr
            x = pl.read_f32()
            print(f"Expected: {expected} Got: {x}")

            # assert x == expected
            ctr += 1


if __name__ == "__main__":
    test_plugin()

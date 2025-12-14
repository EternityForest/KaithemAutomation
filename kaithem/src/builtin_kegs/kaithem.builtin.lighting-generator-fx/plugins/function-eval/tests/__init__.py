import os

import wasm_kegs


class Loader(wasm_kegs.PluginLoader):
    plugin_type = "kaithem.chandler.lighting-generator"


os.environ["WASMTIME_BACKTRACE_DETAILS"] = "1"


def test_plugin():
    ps = wasm_kegs.packages.PackageStore(
        [
            os.path.normpath(
                os.path.join(os.path.dirname(__file__), "../../../..")
            )
        ]
    )
    with ps:
        p = Loader("kaithem.builtin.lighting-generator-fx:function-eval", {})

        p.call_plugin("set_config", b'{"green": "60*2"}')
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
            p.call_plugin("set_input_values", pl.data)

        pl = wasm_kegs.Payload(b"")
        pl.write_i64(10)  # ch num
        pl.write_i64(-1)  # fixture
        pl.write_i64(-1)  # g
        pl.write_bytes(b"")  # Extra data
        p.call_plugin("set_channel_metadata", pl.data)

        pl = wasm_kegs.Payload(b"")
        pl.write_i64(0)  # start
        pl.write_i64(10)  # len
        pl.write_i64(0)  # time

        x = p.call_plugin("process", pl.data)

        pl = wasm_kegs.Payload(x)
        ctr = 0

        while pl.data:
            expected = 60 * 2
            x = pl.read_f32()
            # print(f"Expected: {expected} Got: {x} {ctr}")

            assert abs(x - expected) < 0.0001
            ctr += 1


if __name__ == "__main__":
    test_plugin()

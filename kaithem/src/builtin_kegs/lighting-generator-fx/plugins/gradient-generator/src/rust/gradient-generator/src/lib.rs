use extism_pdk::*;

use wasm_kegs_sdk::KegsPayload;


use wasm_kegs_sdk::keg_get_static_resource;

#[host_fn("extism:host/user")]
extern "ExtismHost" {
    fn keg_test_get_name() -> String;
}


#[plugin_fn]
pub unsafe fn readback(name: String) -> FnResult<String> {
    Ok(
        String::from_utf8(
            keg_get_static_resource(name)?
    )?)
    }


#[plugin_fn]
pub unsafe fn greet(name: String) -> FnResult<String> {
    Ok(format!("Hello, {}, from {}!", name, keg_test_get_name()?))
}


#[plugin_fn]
pub unsafe fn add_test(input: Vec<u8>) -> FnResult<Vec<u8>> {
    let mut keg_payload: KegsPayload = KegsPayload::from_bytes(input);
    let a = keg_payload.read_i64();
    let b = keg_payload.read_i64();
    
    let output = a + b;

    let mut keg_payload_out = KegsPayload::new();
    keg_payload_out.write_i64(output);
    Ok(keg_payload_out.into_bytes())
}


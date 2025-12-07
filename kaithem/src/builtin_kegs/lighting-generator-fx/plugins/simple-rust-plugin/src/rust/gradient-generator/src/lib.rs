use extism_pdk::*;

use wasm_kegs_sdk::KegsPayload;



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


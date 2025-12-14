use exp_rs::types::AstExpr;
use extism_pdk::json::value;
use extism_pdk::*;
use fchashmap::FcHashMap;
use picojson::{Event, PullParser, SliceParser};

use exp_rs::context::EvalContext;
use exp_rs::engine::parse_expression;
use exp_rs::eval::eval_ast;
use std::rc::Rc;

use wasm_kegs_sdk::KegsPayload;

static mut EXPR_BY_CHANNEL: Option<FcHashMap<i64, AstExpr, 64>> = None;
static mut CONTEXT: Option<Rc<EvalContext>> = None;

#[derive(Copy, Clone, PartialEq)]
struct ChannelMetadata {
    typecode: i64,
    fixture_id: i64,
}

static mut METADATA: [ChannelMetadata; 65536] = [ChannelMetadata {
    typecode: -1,
    fixture_id: -1,
}; 65536];

static mut INPUT_DATA: [f32; 65536] = [0.0; 65536];

#[plugin_fn]
pub unsafe fn set_channel_metadata(input: Vec<u8>) -> FnResult<()> {
    let mut keg_payload: KegsPayload = KegsPayload::from_bytes(input);

    let mut channel = keg_payload.read_i64();

    while keg_payload.available() >= 24 {
        let fixture_id = keg_payload.read_i64();
        let typecode = keg_payload.read_i64();

        let _ext_json = keg_payload.read_bytes();

        METADATA[channel as usize] = ChannelMetadata {
            typecode: typecode,
            fixture_id: fixture_id,
        };

        channel += 1;
    }

    return Ok(());
}

#[plugin_fn]
pub unsafe fn set_input_values(input: Vec<u8>) -> FnResult<()> {
    let mut keg_payload: KegsPayload = KegsPayload::from_bytes(input);
    let mut channel = keg_payload.read_i64();

    while keg_payload.available() >= 4 {
        let value = keg_payload.read_f32();
        INPUT_DATA[channel as usize] = value;
        channel += 1;
    }

    return Ok(());
}

fn color_to_code(s: &str) -> i64 {
    return match s {
        "red" => 1,
        "green" => 2,
        "blue" => 3,
        "white" => 4,
        "neutral_white" => 5,
        "warm_white" => 6,
        "cool_white" => 7,
        "amber" => 8,
        "lime" => 9,
        "uv" => 10,
        "x" => 11,
        "y" => 12,
        _ => -1,
    };
}

#[plugin_fn]
pub unsafe fn set_config(json: Vec<u8>) -> FnResult<()> {
    EXPR_BY_CHANNEL = Some(FcHashMap::<i64, AstExpr, 64>::new());
    CONTEXT = Some(Rc::new(EvalContext::new()));

    let mut scratch: [u8; 256] = [0; 256];
    let mut parser =
        SliceParser::with_buffer(str::from_utf8(&json).unwrap(), &mut scratch);

    let mut channel: i64 = -1;

    while let Some(event) = parser.next() {
        match event.unwrap() {
            Event::Key(key) => {
                channel = color_to_code(&key);
            }
            Event::String(value) => {
                let expr = parse_expression(&value);
                if expr.is_err() {
                    println!(
                        "Failed to parse expression for channel {}",
                        channel
                    );
                } else {
                    EXPR_BY_CHANNEL
                        .as_mut()
                        .unwrap()
                        .insert(channel, expr.unwrap())
                        .unwrap();
                }
            }

            Event::EndDocument => break,
            _ => {}
        }
    }

    return Ok(());
}

#[plugin_fn]
pub unsafe fn reset_state() -> FnResult<()> {
    return Ok(());
}

#[plugin_fn]
pub unsafe fn process(input: Vec<u8>) -> FnResult<Vec<u8>> {
    let mut keg_payload: KegsPayload = KegsPayload::from_bytes(input);
    let start: u64 = keg_payload.read_i64().try_into().unwrap();
    let len: usize = keg_payload.read_i64().try_into().unwrap();

    let _time_us = keg_payload.read_i64();

    let mut ptr = start;
    let end_ptr: u64 = start + len as u64;

    let time_pos: f64 = _time_us as f64 / 1000000.0;

    let mut keg_payload_out: KegsPayload = KegsPayload::new();


    Rc::get_mut(CONTEXT.as_mut().unwrap())
        .unwrap()
        .set_parameter("time", time_pos);

    let mut ctx: Rc<EvalContext> = CONTEXT.as_ref().unwrap().clone();

    let by_channel = EXPR_BY_CHANNEL.as_ref().unwrap();

    while ptr < end_ptr {
        let ptr_fix_id = METADATA[ptr as usize].fixture_id;
        let ptr_typecode = METADATA[ptr as usize].typecode;

        if INPUT_DATA[ptr as usize] == -1000_001.0 {
            let expr: Option<&AstExpr> = by_channel.get(&ptr_typecode);

            if expr.is_none() {
                keg_payload_out.write_f32(0.0);
            } else {
                let value = eval_ast(expr.unwrap(), Some(ctx.clone()));

                if (value.is_err()) {
                    keg_payload_out.write_f32(0.0);
                } else {
                    keg_payload_out.write_f32(value.unwrap() as f32);
                }
            }
        }

        ptr += 1;
    }

    Ok(keg_payload_out.into_bytes())
}

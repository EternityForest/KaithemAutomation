use extism_pdk::*;

use wasm_kegs_sdk::KegsPayload;

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
    let channel = keg_payload.read_i64();
    let typecode = keg_payload.read_i64();
    let fixture_id = keg_payload.read_i64();

    let _ext_json = keg_payload.read_bytes();

    METADATA[channel as usize] = ChannelMetadata {
        typecode: typecode,
        fixture_id: fixture_id,
    };

    return Ok(());
}

#[plugin_fn]
pub unsafe fn set_channel_input(input: Vec<u8>) -> FnResult<()> {
    let mut keg_payload: KegsPayload = KegsPayload::from_bytes(input);
    let channel = keg_payload.read_i64();
    let value = keg_payload.read_f32();

    INPUT_DATA[channel as usize] = value;

    return Ok(());
}

#[derive(Copy, Clone, PartialEq)]
struct FixtureData {
    fixture_id: i64,
    values: [f32; 16]

}

impl FixtureData {
    fn new(fixture_id: i64) -> Self {
        FixtureData {
            fixture_id: fixture_id,
            values: [0.0; 16],
        }
    }

    fn interpolate(&mut self, other: FixtureData, amount: f32) -> FixtureData {
        let mut new_values: [f32; 16] = [0.0; 16];
        for i in 0..16 {
            new_values[i] = self.values[i] + (other.values[i] - self.values[i]) * amount;
        }
        return FixtureData {
            fixture_id: self.fixture_id,
            values: new_values,
        };
    }
}

unsafe fn compile_fixture_data(ptr: u64) -> FixtureData {
    let mut fixture = FixtureData::new(0);

    let mut pointer = ptr;

    fixture.fixture_id = METADATA[pointer as usize].fixture_id;

    while (pointer < 65536) {
        let typecode = METADATA[pointer as usize].typecode;
        let fixture_id = METADATA[pointer as usize].fixture_id;
        let value = INPUT_DATA[pointer as usize];

        if (fixture.fixture_id != fixture_id) {
            break;
        }
        if (fixture.fixture_id == -1) {
            break;
        }
        if (typecode > 0 && typecode < 16) {
            fixture.values[typecode as usize] = value;
        }
        fixture.values[pointer as usize] = value;
        pointer += 1;
    }

    return fixture;
}

unsafe fn find_next_fixture_after(ptr: u64) -> u64 {
    let mut pointer = ptr;
    let fixture_id = METADATA[pointer as usize].fixture_id;

    while (pointer < 65536) {
        // Look for the first fixture that has something other than
        // auto values
        if (INPUT_DATA[pointer as usize] != -1000_001.0) {
            if (METADATA[pointer as usize].fixture_id != fixture_id) {
                return pointer;
            }
        }
        pointer += 1;
    }
    return pointer;
}

#[plugin_fn]
pub unsafe fn process(input: Vec<u8>) -> FnResult<Vec<u8>> {
    let mut keg_payload: KegsPayload = KegsPayload::from_bytes(input);
    let mut start: u64 = keg_payload.read_i64().try_into().unwrap();
    let len: usize = keg_payload.read_i64().try_into().unwrap();

    let time_us = keg_payload.read_i64();

    let mut next_fix_data = FixtureData::new(0);
    let mut fade_from_data = FixtureData::new(0);

    let mut fade_from_ptr = start;
    let mut next_fix_ptr = start;

    let mut current_fix = FixtureData::new(0);

    let mut ptr = start;

    let mut currently_on_fixture = -1;

    let mut keg_payload_out = KegsPayload::preallocated(len * 4);

    next_fix_data = compile_fixture_data(find_next_fixture_after(ptr));

    let end_ptr: u64 = start + len as u64;

    while (ptr < end_ptr) {
        let ptr_fix_id = METADATA[ptr as usize].fixture_id;
        let ptr_typecode = METADATA[ptr as usize].typecode;

        if (ptr_fix_id == next_fix_data.fixture_id) {
            fade_from_data = next_fix_data;
            fade_from_ptr = ptr;
            next_fix_ptr = find_next_fixture_after(ptr);
            next_fix_data = compile_fixture_data(next_fix_ptr);
        }

        if (currently_on_fixture != ptr_fix_id) {
            let gradient_len: i64 =
                next_fix_ptr as i64 - fade_from_ptr as i64;
            
            let mut amount = 0.0;
            if (gradient_len > 0) {
                amount = (ptr as f32 - fade_from_ptr as f32) / gradient_len as f32;
            }
            current_fix = fade_from_data.interpolate(next_fix_data, amount);
            currently_on_fixture = ptr_fix_id;
        }

        if (ptr_typecode > 0 && ptr_typecode < 16) {
            keg_payload_out.write_f32(current_fix.values[ptr_typecode as usize]);
        } else {
            keg_payload_out.write_f32(INPUT_DATA[ptr as usize]);
        }
        ptr += 1;
    }

    Ok(keg_payload_out.into_bytes())
}

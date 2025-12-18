use extism_pdk::*;

// Define the enum
pub enum LogLevel {
    Trace = 0,
    Debug = 10,
    Info = 20,
    Warn = 30,
    Error = 40,
    Critical = 50
}


/// The KegsPayload is used to encode the arguments for
/// Kegs plugins that do not just use simple primitive types.
pub struct KegsPayload {
    buf: Vec<u8>,
    pos: usize,
}

impl KegsPayload {
    pub fn new() -> Self { Self { buf: Vec::new(), pos: 0 } }

    pub fn preallocated(size: usize) -> Self { Self { buf: Vec::with_capacity(size), pos: 0 } }

    pub fn from_bytes(b: Vec<u8>) -> Self { Self { buf: b, pos: 0 } }

    pub fn into_bytes(self) -> Vec<u8> { self.buf }

    // --- Write primitives ---
    pub fn write_i64(&mut self, v: i64) {
        self.buf.extend_from_slice(&v.to_le_bytes());
    }

    pub fn write_f32(&mut self, v: f32) {
        self.buf.extend_from_slice(&v.to_le_bytes());
    }

    pub fn write_bytes(&mut self, b: &[u8]) {
        self.write_i64(b.len() as i64);
        self.buf.extend_from_slice(b);
    }

    // --- Read primitives ---
    pub fn read_i64(&mut self) -> i64 {
        let mut arr = [0u8; 8];
        arr.copy_from_slice(&self.buf[self.pos..self.pos+8]);
        self.pos += 8;
        return i64::from_le_bytes(arr)
    }

    pub fn read_f32(&mut self) -> f32 {
        let mut arr = [0u8; 4];
        arr.copy_from_slice(&self.buf[self.pos..self.pos+4]);
        self.pos += 4;
        return f32::from_le_bytes(arr)
    }

    pub fn read_bytes(&mut self) -> Vec<u8> {
        let len = self.read_i64() as usize;
        if len == 0 { return Vec::new(); }
        let out = self.buf[self.pos..self.pos+len].to_vec();
        self.pos += len;
        return out;
    }

    pub fn read_string(&mut self) -> String {
        return String::from_utf8(self.read_bytes()).unwrap();
    }

    pub fn available(&self) -> usize {
        return self.buf.len() - self.pos
    }


}


/// Get a path within the /static folder
/// Of a plugin.
#[host_fn("extism:host/user")]
extern "ExtismHost" {
    pub fn keg_get_static_resource(path: String) -> Vec<u8>;
}



#[host_fn("extism:host/user")]
extern "ExtismHost" {
    fn keg_print(text: String) -> ();
}

/// Print text to be handled by the host
pub fn print(text: String) {
    unsafe {
        let _ = keg_print(text);
    }
}


#[host_fn("extism:host/user")]
extern "ExtismHost" {
    fn keg_log(pl: Vec<u8>) -> ();
}


/// Log data to be handled by the host
pub fn log(level: LogLevel, text: String) {
    let mut buf = KegsPayload::new();
    buf.write_i64(level as i64);
    buf.write_bytes(text.as_bytes());
    unsafe {
        let _ = keg_log(buf.into_bytes());
    }
}
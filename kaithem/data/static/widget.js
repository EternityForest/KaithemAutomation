/*
The MIT License (MIT)

Copyright (c) 2015 Yusuke Kawasaki
*/
!function (t) { if ("object" == typeof exports && "undefined" != typeof module) module.exports = t(); else if ("function" == typeof define && define.amd) define([], t); else { var r; r = "undefined" != typeof window ? window : "undefined" != typeof global ? global : "undefined" != typeof self ? self : this, r.msgpack = t() } }(function () {
	return function t(r, e, n) { function i(f, u) { if (!e[f]) { if (!r[f]) { var a = "function" == typeof require && require; if (!u && a) return a(f, !0); if (o) return o(f, !0); var s = new Error("Cannot find module '" + f + "'"); throw s.code = "MODULE_NOT_FOUND", s } var c = e[f] = { exports: {} }; r[f][0].call(c.exports, function (t) { var e = r[f][1][t]; return i(e ? e : t) }, c, c.exports, t, r, e, n) } return e[f].exports } for (var o = "function" == typeof require && require, f = 0; f < n.length; f++)i(n[f]); return i }({
		1: [function (t, r, e) { e.encode = t("./encode").encode, e.decode = t("./decode").decode, e.Encoder = t("./encoder").Encoder, e.Decoder = t("./decoder").Decoder, e.createCodec = t("./ext").createCodec, e.codec = t("./codec").codec }, { "./codec": 10, "./decode": 12, "./decoder": 13, "./encode": 15, "./encoder": 16, "./ext": 20 }], 2: [function (t, r, e) { (function (Buffer) { function t(t) { return t && t.isBuffer && t } r.exports = t("undefined" != typeof Buffer && Buffer) || t(this.Buffer) || t("undefined" != typeof window && window.Buffer) || this.Buffer }).call(this, t("buffer").Buffer) }, { buffer: 29 }], 3: [function (t, r, e) { function n(t, r) { for (var e = this, n = r || (r |= 0), i = t.length, o = 0, f = 0; f < i;)o = t.charCodeAt(f++), o < 128 ? e[n++] = o : o < 2048 ? (e[n++] = 192 | o >>> 6, e[n++] = 128 | 63 & o) : o < 55296 || o > 57343 ? (e[n++] = 224 | o >>> 12, e[n++] = 128 | o >>> 6 & 63, e[n++] = 128 | 63 & o) : (o = (o - 55296 << 10 | t.charCodeAt(f++) - 56320) + 65536, e[n++] = 240 | o >>> 18, e[n++] = 128 | o >>> 12 & 63, e[n++] = 128 | o >>> 6 & 63, e[n++] = 128 | 63 & o); return n - r } function i(t, r, e) { var n = this, i = 0 | r; e || (e = n.length); for (var o = "", f = 0; i < e;)f = n[i++], f < 128 ? o += String.fromCharCode(f) : (192 === (224 & f) ? f = (31 & f) << 6 | 63 & n[i++] : 224 === (240 & f) ? f = (15 & f) << 12 | (63 & n[i++]) << 6 | 63 & n[i++] : 240 === (248 & f) && (f = (7 & f) << 18 | (63 & n[i++]) << 12 | (63 & n[i++]) << 6 | 63 & n[i++]), f >= 65536 ? (f -= 65536, o += String.fromCharCode((f >>> 10) + 55296, (1023 & f) + 56320)) : o += String.fromCharCode(f)); return o } function o(t, r, e, n) { var i; e || (e = 0), n || 0 === n || (n = this.length), r || (r = 0); var o = n - e; if (t === this && e < r && r < n) for (i = o - 1; i >= 0; i--)t[i + r] = this[i + e]; else for (i = 0; i < o; i++)t[i + r] = this[i + e]; return o } e.copy = o, e.toString = i, e.write = n }, {}], 4: [function (t, r, e) { function n(t) { return new Array(t) } function i(t) { if (!o.isBuffer(t) && o.isView(t)) t = o.Uint8Array.from(t); else if (o.isArrayBuffer(t)) t = new Uint8Array(t); else { if ("string" == typeof t) return o.from.call(e, t); if ("number" == typeof t) throw new TypeError('"value" argument must not be a number') } return Array.prototype.slice.call(t) } var o = t("./bufferish"), e = r.exports = n(0); e.alloc = n, e.concat = o.concat, e.from = i }, { "./bufferish": 8 }], 5: [function (t, r, e) { function n(t) { return new Buffer(t) } function i(t) { if (!o.isBuffer(t) && o.isView(t)) t = o.Uint8Array.from(t); else if (o.isArrayBuffer(t)) t = new Uint8Array(t); else { if ("string" == typeof t) return o.from.call(e, t); if ("number" == typeof t) throw new TypeError('"value" argument must not be a number') } return Buffer.from && 1 !== Buffer.from.length ? Buffer.from(t) : new Buffer(t) } var o = t("./bufferish"), Buffer = o.global, e = r.exports = o.hasBuffer ? n(0) : []; e.alloc = o.hasBuffer && Buffer.alloc || n, e.concat = o.concat, e.from = i }, { "./bufferish": 8 }], 6: [function (t, r, e) { function n(t, r, e, n) { var o = a.isBuffer(this), f = a.isBuffer(t); if (o && f) return this.copy(t, r, e, n); if (c || o || f || !a.isView(this) || !a.isView(t)) return u.copy.call(this, t, r, e, n); var s = e || null != n ? i.call(this, e, n) : this; return t.set(s, r), s.length } function i(t, r) { var e = this.slice || !c && this.subarray; if (e) return e.call(this, t, r); var i = a.alloc.call(this, r - t); return n.call(this, i, 0, t, r), i } function o(t, r, e) { var n = !s && a.isBuffer(this) ? this.toString : u.toString; return n.apply(this, arguments) } function f(t) { function r() { var r = this[t] || u[t]; return r.apply(this, arguments) } return r } var u = t("./buffer-lite"); e.copy = n, e.slice = i, e.toString = o, e.write = f("write"); var a = t("./bufferish"), Buffer = a.global, s = a.hasBuffer && "TYPED_ARRAY_SUPPORT" in Buffer, c = s && !Buffer.TYPED_ARRAY_SUPPORT }, { "./buffer-lite": 3, "./bufferish": 8 }], 7: [function (t, r, e) { function n(t) { return new Uint8Array(t) } function i(t) { if (o.isView(t)) { var r = t.byteOffset, n = t.byteLength; t = t.buffer, t.byteLength !== n && (t.slice ? t = t.slice(r, r + n) : (t = new Uint8Array(t), t.byteLength !== n && (t = Array.prototype.slice.call(t, r, r + n)))) } else { if ("string" == typeof t) return o.from.call(e, t); if ("number" == typeof t) throw new TypeError('"value" argument must not be a number') } return new Uint8Array(t) } var o = t("./bufferish"), e = r.exports = o.hasArrayBuffer ? n(0) : []; e.alloc = n, e.concat = o.concat, e.from = i }, { "./bufferish": 8 }], 8: [function (t, r, e) { function n(t) { return "string" == typeof t ? u.call(this, t) : a(this).from(t) } function i(t) { return a(this).alloc(t) } function o(t, r) { function n(t) { r += t.length } function o(t) { a += w.copy.call(t, u, a) } r || (r = 0, Array.prototype.forEach.call(t, n)); var f = this !== e && this || t[0], u = i.call(f, r), a = 0; return Array.prototype.forEach.call(t, o), u } function f(t) { return t instanceof ArrayBuffer || E(t) } function u(t) { var r = 3 * t.length, e = i.call(this, r), n = w.write.call(e, t); return r !== n && (e = w.slice.call(e, 0, n)), e } function a(t) { return d(t) ? g : y(t) ? b : p(t) ? v : h ? g : l ? b : v } function s() { return !1 } function c(t, r) { return t = "[object " + t + "]", function (e) { return null != e && {}.toString.call(r ? e[r] : e) === t } } var Buffer = e.global = t("./buffer-global"), h = e.hasBuffer = Buffer && !!Buffer.isBuffer, l = e.hasArrayBuffer = "undefined" != typeof ArrayBuffer, p = e.isArray = t("isarray"); e.isArrayBuffer = l ? f : s; var d = e.isBuffer = h ? Buffer.isBuffer : s, y = e.isView = l ? ArrayBuffer.isView || c("ArrayBuffer", "buffer") : s; e.alloc = i, e.concat = o, e.from = n; var v = e.Array = t("./bufferish-array"), g = e.Buffer = t("./bufferish-buffer"), b = e.Uint8Array = t("./bufferish-uint8array"), w = e.prototype = t("./bufferish-proto"), E = c("ArrayBuffer") }, { "./buffer-global": 2, "./bufferish-array": 4, "./bufferish-buffer": 5, "./bufferish-proto": 6, "./bufferish-uint8array": 7, isarray: 34 }], 9: [function (t, r, e) { function n(t) { return this instanceof n ? (this.options = t, void this.init()) : new n(t) } function i(t) { for (var r in t) n.prototype[r] = o(n.prototype[r], t[r]) } function o(t, r) { function e() { return t.apply(this, arguments), r.apply(this, arguments) } return t && r ? e : t || r } function f(t) { function r(t, r) { return r(t) } return t = t.slice(), function (e) { return t.reduce(r, e) } } function u(t) { return s(t) ? f(t) : t } function a(t) { return new n(t) } var s = t("isarray"); e.createCodec = a, e.install = i, e.filter = u; var c = t("./bufferish"); n.prototype.init = function () { var t = this.options; return t && t.uint8array && (this.bufferish = c.Uint8Array), this }, e.preset = a({ preset: !0 }) }, { "./bufferish": 8, isarray: 34 }], 10: [function (t, r, e) { t("./read-core"), t("./write-core"), e.codec = { preset: t("./codec-base").preset } }, { "./codec-base": 9, "./read-core": 22, "./write-core": 25 }], 11: [function (t, r, e) { function n(t) { if (!(this instanceof n)) return new n(t); if (t && (this.options = t, t.codec)) { var r = this.codec = t.codec; r.bufferish && (this.bufferish = r.bufferish) } } e.DecodeBuffer = n; var i = t("./read-core").preset, o = t("./flex-buffer").FlexDecoder; o.mixin(n.prototype), n.prototype.codec = i, n.prototype.fetch = function () { return this.codec.decode(this) } }, { "./flex-buffer": 21, "./read-core": 22 }], 12: [function (t, r, e) { function n(t, r) { var e = new i(r); return e.write(t), e.read() } e.decode = n; var i = t("./decode-buffer").DecodeBuffer }, { "./decode-buffer": 11 }], 13: [function (t, r, e) { function n(t) { return this instanceof n ? void o.call(this, t) : new n(t) } e.Decoder = n; var i = t("event-lite"), o = t("./decode-buffer").DecodeBuffer; n.prototype = new o, i.mixin(n.prototype), n.prototype.decode = function (t) { arguments.length && this.write(t), this.flush() }, n.prototype.push = function (t) { this.emit("data", t) }, n.prototype.end = function (t) { this.decode(t), this.emit("end") } }, { "./decode-buffer": 11, "event-lite": 31 }], 14: [function (t, r, e) { function n(t) { if (!(this instanceof n)) return new n(t); if (t && (this.options = t, t.codec)) { var r = this.codec = t.codec; r.bufferish && (this.bufferish = r.bufferish) } } e.EncodeBuffer = n; var i = t("./write-core").preset, o = t("./flex-buffer").FlexEncoder; o.mixin(n.prototype), n.prototype.codec = i, n.prototype.write = function (t) { this.codec.encode(this, t) } }, { "./flex-buffer": 21, "./write-core": 25 }], 15: [function (t, r, e) { function n(t, r) { var e = new i(r); return e.write(t), e.read() } e.encode = n; var i = t("./encode-buffer").EncodeBuffer }, { "./encode-buffer": 14 }], 16: [function (t, r, e) { function n(t) { return this instanceof n ? void o.call(this, t) : new n(t) } e.Encoder = n; var i = t("event-lite"), o = t("./encode-buffer").EncodeBuffer; n.prototype = new o, i.mixin(n.prototype), n.prototype.encode = function (t) { this.write(t), this.emit("data", this.read()) }, n.prototype.end = function (t) { arguments.length && this.encode(t), this.flush(), this.emit("end") } }, { "./encode-buffer": 14, "event-lite": 31 }], 17: [function (t, r, e) { function n(t, r) { return this instanceof n ? (this.buffer = i.from(t), void (this.type = r)) : new n(t, r) } e.ExtBuffer = n; var i = t("./bufferish") }, { "./bufferish": 8 }], 18: [function (t, r, e) { function n(t) { t.addExtPacker(14, Error, [u, i]), t.addExtPacker(1, EvalError, [u, i]), t.addExtPacker(2, RangeError, [u, i]), t.addExtPacker(3, ReferenceError, [u, i]), t.addExtPacker(4, SyntaxError, [u, i]), t.addExtPacker(5, TypeError, [u, i]), t.addExtPacker(6, URIError, [u, i]), t.addExtPacker(10, RegExp, [f, i]), t.addExtPacker(11, Boolean, [o, i]), t.addExtPacker(12, String, [o, i]), t.addExtPacker(13, Date, [Number, i]), t.addExtPacker(15, Number, [o, i]), "undefined" != typeof Uint8Array && (t.addExtPacker(17, Int8Array, c), t.addExtPacker(18, Uint8Array, c), t.addExtPacker(19, Int16Array, c), t.addExtPacker(20, Uint16Array, c), t.addExtPacker(21, Int32Array, c), t.addExtPacker(22, Uint32Array, c), t.addExtPacker(23, Float32Array, c), "undefined" != typeof Float64Array && t.addExtPacker(24, Float64Array, c), "undefined" != typeof Uint8ClampedArray && t.addExtPacker(25, Uint8ClampedArray, c), t.addExtPacker(26, ArrayBuffer, c), t.addExtPacker(29, DataView, c)), s.hasBuffer && t.addExtPacker(27, Buffer, s.from) } function i(r) { return a || (a = t("./encode").encode), a(r) } function o(t) { return t.valueOf() } function f(t) { t = RegExp.prototype.toString.call(t).split("/"), t.shift(); var r = [t.pop()]; return r.unshift(t.join("/")), r } function u(t) { var r = {}; for (var e in h) r[e] = t[e]; return r } e.setExtPackers = n; var a, s = t("./bufferish"), Buffer = s.global, c = s.Uint8Array.from, h = { name: 1, message: 1, stack: 1, columnNumber: 1, fileName: 1, lineNumber: 1 } }, { "./bufferish": 8, "./encode": 15 }], 19: [function (t, r, e) { function n(t) { t.addExtUnpacker(14, [i, f(Error)]), t.addExtUnpacker(1, [i, f(EvalError)]), t.addExtUnpacker(2, [i, f(RangeError)]), t.addExtUnpacker(3, [i, f(ReferenceError)]), t.addExtUnpacker(4, [i, f(SyntaxError)]), t.addExtUnpacker(5, [i, f(TypeError)]), t.addExtUnpacker(6, [i, f(URIError)]), t.addExtUnpacker(10, [i, o]), t.addExtUnpacker(11, [i, u(Boolean)]), t.addExtUnpacker(12, [i, u(String)]), t.addExtUnpacker(13, [i, u(Date)]), t.addExtUnpacker(15, [i, u(Number)]), "undefined" != typeof Uint8Array && (t.addExtUnpacker(17, u(Int8Array)), t.addExtUnpacker(18, u(Uint8Array)), t.addExtUnpacker(19, [a, u(Int16Array)]), t.addExtUnpacker(20, [a, u(Uint16Array)]), t.addExtUnpacker(21, [a, u(Int32Array)]), t.addExtUnpacker(22, [a, u(Uint32Array)]), t.addExtUnpacker(23, [a, u(Float32Array)]), "undefined" != typeof Float64Array && t.addExtUnpacker(24, [a, u(Float64Array)]), "undefined" != typeof Uint8ClampedArray && t.addExtUnpacker(25, u(Uint8ClampedArray)), t.addExtUnpacker(26, a), t.addExtUnpacker(29, [a, u(DataView)])), c.hasBuffer && t.addExtUnpacker(27, u(Buffer)) } function i(r) { return s || (s = t("./decode").decode), s(r) } function o(t) { return RegExp.apply(null, t) } function f(t) { return function (r) { var e = new t; for (var n in h) e[n] = r[n]; return e } } function u(t) { return function (r) { return new t(r) } } function a(t) { return new Uint8Array(t).buffer } e.setExtUnpackers = n; var s, c = t("./bufferish"), Buffer = c.global, h = { name: 1, message: 1, stack: 1, columnNumber: 1, fileName: 1, lineNumber: 1 } }, { "./bufferish": 8, "./decode": 12 }], 20: [function (t, r, e) { t("./read-core"), t("./write-core"), e.createCodec = t("./codec-base").createCodec }, { "./codec-base": 9, "./read-core": 22, "./write-core": 25 }], 21: [function (t, r, e) { function n() { if (!(this instanceof n)) return new n } function i() { if (!(this instanceof i)) return new i } function o() { function t(t) { var r = this.offset ? p.prototype.slice.call(this.buffer, this.offset) : this.buffer; this.buffer = r ? t ? this.bufferish.concat([r, t]) : r : t, this.offset = 0 } function r() { for (; this.offset < this.buffer.length;) { var t, r = this.offset; try { t = this.fetch() } catch (t) { if (t && t.message != v) throw t; this.offset = r; break } this.push(t) } } function e(t) { var r = this.offset, e = r + t; if (e > this.buffer.length) throw new Error(v); return this.offset = e, r } return { bufferish: p, write: t, fetch: a, flush: r, push: c, pull: h, read: s, reserve: e, offset: 0 } } function f() { function t() { var t = this.start; if (t < this.offset) { var r = this.start = this.offset; return p.prototype.slice.call(this.buffer, t, r) } } function r() { for (; this.start < this.offset;) { var t = this.fetch(); t && this.push(t) } } function e() { var t = this.buffers || (this.buffers = []), r = t.length > 1 ? this.bufferish.concat(t) : t[0]; return t.length = 0, r } function n(t) { var r = 0 | t; if (this.buffer) { var e = this.buffer.length, n = 0 | this.offset, i = n + r; if (i < e) return this.offset = i, n; this.flush(), t = Math.max(t, Math.min(2 * e, this.maxBufferSize)) } return t = Math.max(t, this.minBufferSize), this.buffer = this.bufferish.alloc(t), this.start = 0, this.offset = r, 0 } function i(t) { var r = t.length; if (r > this.minBufferSize) this.flush(), this.push(t); else { var e = this.reserve(r); p.prototype.copy.call(t, this.buffer, e) } } return { bufferish: p, write: u, fetch: t, flush: r, push: c, pull: e, read: s, reserve: n, send: i, maxBufferSize: y, minBufferSize: d, offset: 0, start: 0 } } function u() { throw new Error("method not implemented: write()") } function a() { throw new Error("method not implemented: fetch()") } function s() { var t = this.buffers && this.buffers.length; return t ? (this.flush(), this.pull()) : this.fetch() } function c(t) { var r = this.buffers || (this.buffers = []); r.push(t) } function h() { var t = this.buffers || (this.buffers = []); return t.shift() } function l(t) { function r(r) { for (var e in t) r[e] = t[e]; return r } return r } e.FlexDecoder = n, e.FlexEncoder = i; var p = t("./bufferish"), d = 2048, y = 65536, v = "BUFFER_SHORTAGE"; n.mixin = l(o()), n.mixin(n.prototype), i.mixin = l(f()), i.mixin(i.prototype) }, { "./bufferish": 8 }], 22: [function (t, r, e) { function n(t) { function r(t) { var r = s(t), n = e[r]; if (!n) throw new Error("Invalid type: " + (r ? "0x" + r.toString(16) : r)); return n(t) } var e = c.getReadToken(t); return r } function i() { var t = this.options; return this.decode = n(t), t && t.preset && a.setExtUnpackers(this), this } function o(t, r) { var e = this.extUnpackers || (this.extUnpackers = []); e[t] = h.filter(r) } function f(t) { function r(r) { return new u(r, t) } var e = this.extUnpackers || (this.extUnpackers = []); return e[t] || r } var u = t("./ext-buffer").ExtBuffer, a = t("./ext-unpacker"), s = t("./read-format").readUint8, c = t("./read-token"), h = t("./codec-base"); h.install({ addExtUnpacker: o, getExtUnpacker: f, init: i }), e.preset = i.call(h.preset) }, { "./codec-base": 9, "./ext-buffer": 17, "./ext-unpacker": 19, "./read-format": 23, "./read-token": 24 }], 23: [function (t, r, e) { function n(t) { var r = k.hasArrayBuffer && t && t.binarraybuffer, e = t && t.int64, n = T && t && t.usemap, B = { map: n ? o : i, array: f, str: u, bin: r ? s : a, ext: c, uint8: h, uint16: p, uint32: y, uint64: g(8, e ? E : b), int8: l, int16: d, int32: v, int64: g(8, e ? A : w), float32: g(4, m), float64: g(8, x) }; return B } function i(t, r) { var e, n = {}, i = new Array(r), o = new Array(r), f = t.codec.decode; for (e = 0; e < r; e++)i[e] = f(t), o[e] = f(t); for (e = 0; e < r; e++)n[i[e]] = o[e]; return n } function o(t, r) { var e, n = new Map, i = new Array(r), o = new Array(r), f = t.codec.decode; for (e = 0; e < r; e++)i[e] = f(t), o[e] = f(t); for (e = 0; e < r; e++)n.set(i[e], o[e]); return n } function f(t, r) { for (var e = new Array(r), n = t.codec.decode, i = 0; i < r; i++)e[i] = n(t); return e } function u(t, r) { var e = t.reserve(r), n = e + r; return _.toString.call(t.buffer, "utf-8", e, n) } function a(t, r) { var e = t.reserve(r), n = e + r, i = _.slice.call(t.buffer, e, n); return k.from(i) } function s(t, r) { var e = t.reserve(r), n = e + r, i = _.slice.call(t.buffer, e, n); return k.Uint8Array.from(i).buffer } function c(t, r) { var e = t.reserve(r + 1), n = t.buffer[e++], i = e + r, o = t.codec.getExtUnpacker(n); if (!o) throw new Error("Invalid ext type: " + (n ? "0x" + n.toString(16) : n)); var f = _.slice.call(t.buffer, e, i); return o(f) } function h(t) { var r = t.reserve(1); return t.buffer[r] } function l(t) { var r = t.reserve(1), e = t.buffer[r]; return 128 & e ? e - 256 : e } function p(t) { var r = t.reserve(2), e = t.buffer; return e[r++] << 8 | e[r] } function d(t) { var r = t.reserve(2), e = t.buffer, n = e[r++] << 8 | e[r]; return 32768 & n ? n - 65536 : n } function y(t) { var r = t.reserve(4), e = t.buffer; return 16777216 * e[r++] + (e[r++] << 16) + (e[r++] << 8) + e[r] } function v(t) { var r = t.reserve(4), e = t.buffer; return e[r++] << 24 | e[r++] << 16 | e[r++] << 8 | e[r] } function g(t, r) { return function (e) { var n = e.reserve(t); return r.call(e.buffer, n, S) } } function b(t) { return new P(this, t).toNumber() } function w(t) { return new R(this, t).toNumber() } function E(t) { return new P(this, t) } function A(t) { return new R(this, t) } function m(t) { return B.read(this, t, !1, 23, 4) } function x(t) { return B.read(this, t, !1, 52, 8) } var B = t("ieee754"), U = t("int64-buffer"), P = U.Uint64BE, R = U.Int64BE; e.getReadFormat = n, e.readUint8 = h; var k = t("./bufferish"), _ = t("./bufferish-proto"), T = "undefined" != typeof Map, S = !0 }, { "./bufferish": 8, "./bufferish-proto": 6, ieee754: 32, "int64-buffer": 33 }], 24: [function (t, r, e) { function n(t) { var r = s.getReadFormat(t); return t && t.useraw ? o(r) : i(r) } function i(t) { var r, e = new Array(256); for (r = 0; r <= 127; r++)e[r] = f(r); for (r = 128; r <= 143; r++)e[r] = a(r - 128, t.map); for (r = 144; r <= 159; r++)e[r] = a(r - 144, t.array); for (r = 160; r <= 191; r++)e[r] = a(r - 160, t.str); for (e[192] = f(null), e[193] = null, e[194] = f(!1), e[195] = f(!0), e[196] = u(t.uint8, t.bin), e[197] = u(t.uint16, t.bin), e[198] = u(t.uint32, t.bin), e[199] = u(t.uint8, t.ext), e[200] = u(t.uint16, t.ext), e[201] = u(t.uint32, t.ext), e[202] = t.float32, e[203] = t.float64, e[204] = t.uint8, e[205] = t.uint16, e[206] = t.uint32, e[207] = t.uint64, e[208] = t.int8, e[209] = t.int16, e[210] = t.int32, e[211] = t.int64, e[212] = a(1, t.ext), e[213] = a(2, t.ext), e[214] = a(4, t.ext), e[215] = a(8, t.ext), e[216] = a(16, t.ext), e[217] = u(t.uint8, t.str), e[218] = u(t.uint16, t.str), e[219] = u(t.uint32, t.str), e[220] = u(t.uint16, t.array), e[221] = u(t.uint32, t.array), e[222] = u(t.uint16, t.map), e[223] = u(t.uint32, t.map), r = 224; r <= 255; r++)e[r] = f(r - 256); return e } function o(t) { var r, e = i(t).slice(); for (e[217] = e[196], e[218] = e[197], e[219] = e[198], r = 160; r <= 191; r++)e[r] = a(r - 160, t.bin); return e } function f(t) { return function () { return t } } function u(t, r) { return function (e) { var n = t(e); return r(e, n) } } function a(t, r) { return function (e) { return r(e, t) } } var s = t("./read-format"); e.getReadToken = n }, { "./read-format": 23 }], 25: [function (t, r, e) { function n(t) { function r(t, r) { var n = e[typeof r]; if (!n) throw new Error('Unsupported type "' + typeof r + '": ' + r); n(t, r) } var e = s.getWriteType(t); return r } function i() { var t = this.options; return this.encode = n(t), t && t.preset && a.setExtPackers(this), this } function o(t, r, e) { function n(r) { return e && (r = e(r)), new u(r, t) } e = c.filter(e); var i = r.name; if (i && "Object" !== i) { var o = this.extPackers || (this.extPackers = {}); o[i] = n } else { var f = this.extEncoderList || (this.extEncoderList = []); f.unshift([r, n]) } } function f(t) { var r = this.extPackers || (this.extPackers = {}), e = t.constructor, n = e && e.name && r[e.name]; if (n) return n; for (var i = this.extEncoderList || (this.extEncoderList = []), o = i.length, f = 0; f < o; f++) { var u = i[f]; if (e === u[0]) return u[1] } } var u = t("./ext-buffer").ExtBuffer, a = t("./ext-packer"), s = t("./write-type"), c = t("./codec-base"); c.install({ addExtPacker: o, getExtPacker: f, init: i }), e.preset = i.call(c.preset) }, { "./codec-base": 9, "./ext-buffer": 17, "./ext-packer": 18, "./write-type": 27 }], 26: [function (t, r, e) { function n(t) { return t && t.uint8array ? i() : m || E.hasBuffer && t && t.safe ? f() : o() } function i() { var t = o(); return t[202] = c(202, 4, p), t[203] = c(203, 8, d), t } function o() { var t = w.slice(); return t[196] = u(196), t[197] = a(197), t[198] = s(198), t[199] = u(199), t[200] = a(200), t[201] = s(201), t[202] = c(202, 4, x.writeFloatBE || p, !0), t[203] = c(203, 8, x.writeDoubleBE || d, !0), t[204] = u(204), t[205] = a(205), t[206] = s(206), t[207] = c(207, 8, h), t[208] = u(208), t[209] = a(209), t[210] = s(210), t[211] = c(211, 8, l), t[217] = u(217), t[218] = a(218), t[219] = s(219), t[220] = a(220), t[221] = s(221), t[222] = a(222), t[223] = s(223), t } function f() { var t = w.slice(); return t[196] = c(196, 1, Buffer.prototype.writeUInt8), t[197] = c(197, 2, Buffer.prototype.writeUInt16BE), t[198] = c(198, 4, Buffer.prototype.writeUInt32BE), t[199] = c(199, 1, Buffer.prototype.writeUInt8), t[200] = c(200, 2, Buffer.prototype.writeUInt16BE), t[201] = c(201, 4, Buffer.prototype.writeUInt32BE), t[202] = c(202, 4, Buffer.prototype.writeFloatBE), t[203] = c(203, 8, Buffer.prototype.writeDoubleBE), t[204] = c(204, 1, Buffer.prototype.writeUInt8), t[205] = c(205, 2, Buffer.prototype.writeUInt16BE), t[206] = c(206, 4, Buffer.prototype.writeUInt32BE), t[207] = c(207, 8, h), t[208] = c(208, 1, Buffer.prototype.writeInt8), t[209] = c(209, 2, Buffer.prototype.writeInt16BE), t[210] = c(210, 4, Buffer.prototype.writeInt32BE), t[211] = c(211, 8, l), t[217] = c(217, 1, Buffer.prototype.writeUInt8), t[218] = c(218, 2, Buffer.prototype.writeUInt16BE), t[219] = c(219, 4, Buffer.prototype.writeUInt32BE), t[220] = c(220, 2, Buffer.prototype.writeUInt16BE), t[221] = c(221, 4, Buffer.prototype.writeUInt32BE), t[222] = c(222, 2, Buffer.prototype.writeUInt16BE), t[223] = c(223, 4, Buffer.prototype.writeUInt32BE), t } function u(t) { return function (r, e) { var n = r.reserve(2), i = r.buffer; i[n++] = t, i[n] = e } } function a(t) { return function (r, e) { var n = r.reserve(3), i = r.buffer; i[n++] = t, i[n++] = e >>> 8, i[n] = e } } function s(t) { return function (r, e) { var n = r.reserve(5), i = r.buffer; i[n++] = t, i[n++] = e >>> 24, i[n++] = e >>> 16, i[n++] = e >>> 8, i[n] = e } } function c(t, r, e, n) { return function (i, o) { var f = i.reserve(r + 1); i.buffer[f++] = t, e.call(i.buffer, o, f, n) } } function h(t, r) { new g(this, r, t) } function l(t, r) { new b(this, r, t) } function p(t, r) { y.write(this, t, r, !1, 23, 4) } function d(t, r) { y.write(this, t, r, !1, 52, 8) } var y = t("ieee754"), v = t("int64-buffer"), g = v.Uint64BE, b = v.Int64BE, w = t("./write-uint8").uint8, E = t("./bufferish"), Buffer = E.global, A = E.hasBuffer && "TYPED_ARRAY_SUPPORT" in Buffer, m = A && !Buffer.TYPED_ARRAY_SUPPORT, x = E.hasBuffer && Buffer.prototype || {}; e.getWriteToken = n }, { "./bufferish": 8, "./write-uint8": 28, ieee754: 32, "int64-buffer": 33 }], 27: [function (t, r, e) { function n(t) { function r(t, r) { var e = r ? 195 : 194; _[e](t, r) } function e(t, r) { var e, n = 0 | r; return r !== n ? (e = 203, void _[e](t, r)) : (e = -32 <= n && n <= 127 ? 255 & n : 0 <= n ? n <= 255 ? 204 : n <= 65535 ? 205 : 206 : -128 <= n ? 208 : -32768 <= n ? 209 : 210, void _[e](t, n)) } function n(t, r) { var e = 207; _[e](t, r.toArray()) } function o(t, r) { var e = 211; _[e](t, r.toArray()) } function v(t) { return t < 32 ? 1 : t <= 255 ? 2 : t <= 65535 ? 3 : 5 } function g(t) { return t < 32 ? 1 : t <= 65535 ? 3 : 5 } function b(t) { function r(r, e) { var n = e.length, i = 5 + 3 * n; r.offset = r.reserve(i); var o = r.buffer, f = t(n), u = r.offset + f; n = s.write.call(o, e, u); var a = t(n); if (f !== a) { var c = u + a - f, h = u + n; s.copy.call(o, o, c, u, h) } var l = 1 === a ? 160 + n : a <= 3 ? 215 + a : 219; _[l](r, n), r.offset += n } return r } function w(t, r) { if (null === r) return A(t, r); if (I(r)) return Y(t, r); if (i(r)) return m(t, r); if (f.isUint64BE(r)) return n(t, r); if (u.isInt64BE(r)) return o(t, r); var e = t.codec.getExtPacker(r); return e && (r = e(r)), r instanceof l ? U(t, r) : void D(t, r) } function E(t, r) { return I(r) ? k(t, r) : void w(t, r) } function A(t, r) { var e = 192; _[e](t, r) } function m(t, r) { var e = r.length, n = e < 16 ? 144 + e : e <= 65535 ? 220 : 221; _[n](t, e); for (var i = t.codec.encode, o = 0; o < e; o++)i(t, r[o]) } function x(t, r) { var e = r.length, n = e < 255 ? 196 : e <= 65535 ? 197 : 198; _[n](t, e), t.send(r) } function B(t, r) { x(t, new Uint8Array(r)) } function U(t, r) { var e = r.buffer, n = e.length, i = y[n] || (n < 255 ? 199 : n <= 65535 ? 200 : 201); _[i](t, n), h[r.type](t), t.send(e) } function P(t, r) { var e = Object.keys(r), n = e.length, i = n < 16 ? 128 + n : n <= 65535 ? 222 : 223; _[i](t, n); var o = t.codec.encode; e.forEach(function (e) { o(t, e), o(t, r[e]) }) } function R(t, r) { if (!(r instanceof Map)) return P(t, r); var e = r.size, n = e < 16 ? 128 + e : e <= 65535 ? 222 : 223; _[n](t, e); var i = t.codec.encode; r.forEach(function (r, e, n) { i(t, e), i(t, r) }) } function k(t, r) { var e = r.length, n = e < 32 ? 160 + e : e <= 65535 ? 218 : 219; _[n](t, e), t.send(r) } var _ = c.getWriteToken(t), T = t && t.useraw, S = p && t && t.binarraybuffer, I = S ? a.isArrayBuffer : a.isBuffer, Y = S ? B : x, C = d && t && t.usemap, D = C ? R : P, O = { boolean: r, function: A, number: e, object: T ? E : w, string: b(T ? g : v), symbol: A, undefined: A }; return O } var i = t("isarray"), o = t("int64-buffer"), f = o.Uint64BE, u = o.Int64BE, a = t("./bufferish"), s = t("./bufferish-proto"), c = t("./write-token"), h = t("./write-uint8").uint8, l = t("./ext-buffer").ExtBuffer, p = "undefined" != typeof Uint8Array, d = "undefined" != typeof Map, y = []; y[1] = 212, y[2] = 213, y[4] = 214, y[8] = 215, y[16] = 216, e.getWriteType = n }, { "./bufferish": 8, "./bufferish-proto": 6, "./ext-buffer": 17, "./write-token": 26, "./write-uint8": 28, "int64-buffer": 33, isarray: 34 }], 28: [function (t, r, e) { function n(t) { return function (r) { var e = r.reserve(1); r.buffer[e] = t } } for (var i = e.uint8 = new Array(256), o = 0; o <= 255; o++)i[o] = n(o) }, {}], 29: [function (t, r, e) {
			(function (r) {
				"use strict"; function n() { try { var t = new Uint8Array(1); return t.__proto__ = { __proto__: Uint8Array.prototype, foo: function () { return 42 } }, 42 === t.foo() && "function" == typeof t.subarray && 0 === t.subarray(1, 1).byteLength } catch (t) { return !1 } } function i() { return Buffer.TYPED_ARRAY_SUPPORT ? 2147483647 : 1073741823 } function o(t, r) { if (i() < r) throw new RangeError("Invalid typed array length"); return Buffer.TYPED_ARRAY_SUPPORT ? (t = new Uint8Array(r), t.__proto__ = Buffer.prototype) : (null === t && (t = new Buffer(r)), t.length = r), t } function Buffer(t, r, e) { if (!(Buffer.TYPED_ARRAY_SUPPORT || this instanceof Buffer)) return new Buffer(t, r, e); if ("number" == typeof t) { if ("string" == typeof r) throw new Error("If encoding is specified then the first argument must be a string"); return s(this, t) } return f(this, t, r, e) } function f(t, r, e, n) { if ("number" == typeof r) throw new TypeError('"value" argument must not be a number'); return "undefined" != typeof ArrayBuffer && r instanceof ArrayBuffer ? l(t, r, e, n) : "string" == typeof r ? c(t, r, e) : p(t, r) } function u(t) { if ("number" != typeof t) throw new TypeError('"size" argument must be a number'); if (t < 0) throw new RangeError('"size" argument must not be negative') } function a(t, r, e, n) { return u(r), r <= 0 ? o(t, r) : void 0 !== e ? "string" == typeof n ? o(t, r).fill(e, n) : o(t, r).fill(e) : o(t, r) } function s(t, r) { if (u(r), t = o(t, r < 0 ? 0 : 0 | d(r)), !Buffer.TYPED_ARRAY_SUPPORT) for (var e = 0; e < r; ++e)t[e] = 0; return t } function c(t, r, e) { if ("string" == typeof e && "" !== e || (e = "utf8"), !Buffer.isEncoding(e)) throw new TypeError('"encoding" must be a valid string encoding'); var n = 0 | v(r, e); t = o(t, n); var i = t.write(r, e); return i !== n && (t = t.slice(0, i)), t } function h(t, r) { var e = r.length < 0 ? 0 : 0 | d(r.length); t = o(t, e); for (var n = 0; n < e; n += 1)t[n] = 255 & r[n]; return t } function l(t, r, e, n) { if (r.byteLength, e < 0 || r.byteLength < e) throw new RangeError("'offset' is out of bounds"); if (r.byteLength < e + (n || 0)) throw new RangeError("'length' is out of bounds"); return r = void 0 === e && void 0 === n ? new Uint8Array(r) : void 0 === n ? new Uint8Array(r, e) : new Uint8Array(r, e, n), Buffer.TYPED_ARRAY_SUPPORT ? (t = r, t.__proto__ = Buffer.prototype) : t = h(t, r), t } function p(t, r) { if (Buffer.isBuffer(r)) { var e = 0 | d(r.length); return t = o(t, e), 0 === t.length ? t : (r.copy(t, 0, 0, e), t) } if (r) { if ("undefined" != typeof ArrayBuffer && r.buffer instanceof ArrayBuffer || "length" in r) return "number" != typeof r.length || H(r.length) ? o(t, 0) : h(t, r); if ("Buffer" === r.type && Q(r.data)) return h(t, r.data) } throw new TypeError("First argument must be a string, Buffer, ArrayBuffer, Array, or array-like object.") } function d(t) { if (t >= i()) throw new RangeError("Attempt to allocate Buffer larger than maximum size: 0x" + i().toString(16) + " bytes"); return 0 | t } function y(t) { return +t != t && (t = 0), Buffer.alloc(+t) } function v(t, r) { if (Buffer.isBuffer(t)) return t.length; if ("undefined" != typeof ArrayBuffer && "function" == typeof ArrayBuffer.isView && (ArrayBuffer.isView(t) || t instanceof ArrayBuffer)) return t.byteLength; "string" != typeof t && (t = "" + t); var e = t.length; if (0 === e) return 0; for (var n = !1; ;)switch (r) { case "ascii": case "latin1": case "binary": return e; case "utf8": case "utf-8": case void 0: return q(t).length; case "ucs2": case "ucs-2": case "utf16le": case "utf-16le": return 2 * e; case "hex": return e >>> 1; case "base64": return X(t).length; default: if (n) return q(t).length; r = ("" + r).toLowerCase(), n = !0 } } function g(t, r, e) { var n = !1; if ((void 0 === r || r < 0) && (r = 0), r > this.length) return ""; if ((void 0 === e || e > this.length) && (e = this.length), e <= 0) return ""; if (e >>>= 0, r >>>= 0, e <= r) return ""; for (t || (t = "utf8"); ;)switch (t) { case "hex": return I(this, r, e); case "utf8": case "utf-8": return k(this, r, e); case "ascii": return T(this, r, e); case "latin1": case "binary": return S(this, r, e); case "base64": return R(this, r, e); case "ucs2": case "ucs-2": case "utf16le": case "utf-16le": return Y(this, r, e); default: if (n) throw new TypeError("Unknown encoding: " + t); t = (t + "").toLowerCase(), n = !0 } } function b(t, r, e) { var n = t[r]; t[r] = t[e], t[e] = n } function w(t, r, e, n, i) { if (0 === t.length) return -1; if ("string" == typeof e ? (n = e, e = 0) : e > 2147483647 ? e = 2147483647 : e < -2147483648 && (e = -2147483648), e = +e, isNaN(e) && (e = i ? 0 : t.length - 1), e < 0 && (e = t.length + e), e >= t.length) { if (i) return -1; e = t.length - 1 } else if (e < 0) { if (!i) return -1; e = 0 } if ("string" == typeof r && (r = Buffer.from(r, n)), Buffer.isBuffer(r)) return 0 === r.length ? -1 : E(t, r, e, n, i); if ("number" == typeof r) return r = 255 & r, Buffer.TYPED_ARRAY_SUPPORT && "function" == typeof Uint8Array.prototype.indexOf ? i ? Uint8Array.prototype.indexOf.call(t, r, e) : Uint8Array.prototype.lastIndexOf.call(t, r, e) : E(t, [r], e, n, i); throw new TypeError("val must be string, number or Buffer") } function E(t, r, e, n, i) { function o(t, r) { return 1 === f ? t[r] : t.readUInt16BE(r * f) } var f = 1, u = t.length, a = r.length; if (void 0 !== n && (n = String(n).toLowerCase(), "ucs2" === n || "ucs-2" === n || "utf16le" === n || "utf-16le" === n)) { if (t.length < 2 || r.length < 2) return -1; f = 2, u /= 2, a /= 2, e /= 2 } var s; if (i) { var c = -1; for (s = e; s < u; s++)if (o(t, s) === o(r, c === -1 ? 0 : s - c)) { if (c === -1 && (c = s), s - c + 1 === a) return c * f } else c !== -1 && (s -= s - c), c = -1 } else for (e + a > u && (e = u - a), s = e; s >= 0; s--) { for (var h = !0, l = 0; l < a; l++)if (o(t, s + l) !== o(r, l)) { h = !1; break } if (h) return s } return -1 } function A(t, r, e, n) { e = Number(e) || 0; var i = t.length - e; n ? (n = Number(n), n > i && (n = i)) : n = i; var o = r.length; if (o % 2 !== 0) throw new TypeError("Invalid hex string"); n > o / 2 && (n = o / 2); for (var f = 0; f < n; ++f) { var u = parseInt(r.substr(2 * f, 2), 16); if (isNaN(u)) return f; t[e + f] = u } return f } function m(t, r, e, n) { return G(q(r, t.length - e), t, e, n) } function x(t, r, e, n) { return G(W(r), t, e, n) } function B(t, r, e, n) { return x(t, r, e, n) } function U(t, r, e, n) { return G(X(r), t, e, n) } function P(t, r, e, n) { return G(J(r, t.length - e), t, e, n) } function R(t, r, e) { return 0 === r && e === t.length ? Z.fromByteArray(t) : Z.fromByteArray(t.slice(r, e)) } function k(t, r, e) { e = Math.min(t.length, e); for (var n = [], i = r; i < e;) { var o = t[i], f = null, u = o > 239 ? 4 : o > 223 ? 3 : o > 191 ? 2 : 1; if (i + u <= e) { var a, s, c, h; switch (u) { case 1: o < 128 && (f = o); break; case 2: a = t[i + 1], 128 === (192 & a) && (h = (31 & o) << 6 | 63 & a, h > 127 && (f = h)); break; case 3: a = t[i + 1], s = t[i + 2], 128 === (192 & a) && 128 === (192 & s) && (h = (15 & o) << 12 | (63 & a) << 6 | 63 & s, h > 2047 && (h < 55296 || h > 57343) && (f = h)); break; case 4: a = t[i + 1], s = t[i + 2], c = t[i + 3], 128 === (192 & a) && 128 === (192 & s) && 128 === (192 & c) && (h = (15 & o) << 18 | (63 & a) << 12 | (63 & s) << 6 | 63 & c, h > 65535 && h < 1114112 && (f = h)) } } null === f ? (f = 65533, u = 1) : f > 65535 && (f -= 65536, n.push(f >>> 10 & 1023 | 55296), f = 56320 | 1023 & f), n.push(f), i += u } return _(n) } function _(t) { var r = t.length; if (r <= $) return String.fromCharCode.apply(String, t); for (var e = "", n = 0; n < r;)e += String.fromCharCode.apply(String, t.slice(n, n += $)); return e } function T(t, r, e) { var n = ""; e = Math.min(t.length, e); for (var i = r; i < e; ++i)n += String.fromCharCode(127 & t[i]); return n } function S(t, r, e) { var n = ""; e = Math.min(t.length, e); for (var i = r; i < e; ++i)n += String.fromCharCode(t[i]); return n } function I(t, r, e) { var n = t.length; (!r || r < 0) && (r = 0), (!e || e < 0 || e > n) && (e = n); for (var i = "", o = r; o < e; ++o)i += V(t[o]); return i } function Y(t, r, e) { for (var n = t.slice(r, e), i = "", o = 0; o < n.length; o += 2)i += String.fromCharCode(n[o] + 256 * n[o + 1]); return i } function C(t, r, e) { if (t % 1 !== 0 || t < 0) throw new RangeError("offset is not uint"); if (t + r > e) throw new RangeError("Trying to access beyond buffer length") } function D(t, r, e, n, i, o) { if (!Buffer.isBuffer(t)) throw new TypeError('"buffer" argument must be a Buffer instance'); if (r > i || r < o) throw new RangeError('"value" argument is out of bounds'); if (e + n > t.length) throw new RangeError("Index out of range") } function O(t, r, e, n) { r < 0 && (r = 65535 + r + 1); for (var i = 0, o = Math.min(t.length - e, 2); i < o; ++i)t[e + i] = (r & 255 << 8 * (n ? i : 1 - i)) >>> 8 * (n ? i : 1 - i) } function L(t, r, e, n) { r < 0 && (r = 4294967295 + r + 1); for (var i = 0, o = Math.min(t.length - e, 4); i < o; ++i)t[e + i] = r >>> 8 * (n ? i : 3 - i) & 255 } function M(t, r, e, n, i, o) { if (e + n > t.length) throw new RangeError("Index out of range"); if (e < 0) throw new RangeError("Index out of range") } function N(t, r, e, n, i) { return i || M(t, r, e, 4, 3.4028234663852886e38, -3.4028234663852886e38), K.write(t, r, e, n, 23, 4), e + 4 } function F(t, r, e, n, i) { return i || M(t, r, e, 8, 1.7976931348623157e308, -1.7976931348623157e308), K.write(t, r, e, n, 52, 8), e + 8 } function j(t) {
					if (t = z(t).replace(tt, ""), t.length < 2) return ""; for (; t.length % 4 !== 0;)t += "="; return t
				} function z(t) { return t.trim ? t.trim() : t.replace(/^\s+|\s+$/g, "") } function V(t) { return t < 16 ? "0" + t.toString(16) : t.toString(16) } function q(t, r) { r = r || 1 / 0; for (var e, n = t.length, i = null, o = [], f = 0; f < n; ++f) { if (e = t.charCodeAt(f), e > 55295 && e < 57344) { if (!i) { if (e > 56319) { (r -= 3) > -1 && o.push(239, 191, 189); continue } if (f + 1 === n) { (r -= 3) > -1 && o.push(239, 191, 189); continue } i = e; continue } if (e < 56320) { (r -= 3) > -1 && o.push(239, 191, 189), i = e; continue } e = (i - 55296 << 10 | e - 56320) + 65536 } else i && (r -= 3) > -1 && o.push(239, 191, 189); if (i = null, e < 128) { if ((r -= 1) < 0) break; o.push(e) } else if (e < 2048) { if ((r -= 2) < 0) break; o.push(e >> 6 | 192, 63 & e | 128) } else if (e < 65536) { if ((r -= 3) < 0) break; o.push(e >> 12 | 224, e >> 6 & 63 | 128, 63 & e | 128) } else { if (!(e < 1114112)) throw new Error("Invalid code point"); if ((r -= 4) < 0) break; o.push(e >> 18 | 240, e >> 12 & 63 | 128, e >> 6 & 63 | 128, 63 & e | 128) } } return o } function W(t) { for (var r = [], e = 0; e < t.length; ++e)r.push(255 & t.charCodeAt(e)); return r } function J(t, r) { for (var e, n, i, o = [], f = 0; f < t.length && !((r -= 2) < 0); ++f)e = t.charCodeAt(f), n = e >> 8, i = e % 256, o.push(i), o.push(n); return o } function X(t) { return Z.toByteArray(j(t)) } function G(t, r, e, n) { for (var i = 0; i < n && !(i + e >= r.length || i >= t.length); ++i)r[i + e] = t[i]; return i } function H(t) { return t !== t } var Z = t("base64-js"), K = t("ieee754"), Q = t("isarray"); e.Buffer = Buffer, e.SlowBuffer = y, e.INSPECT_MAX_BYTES = 50, Buffer.TYPED_ARRAY_SUPPORT = void 0 !== r.TYPED_ARRAY_SUPPORT ? r.TYPED_ARRAY_SUPPORT : n(), e.kMaxLength = i(), Buffer.poolSize = 8192, Buffer._augment = function (t) { return t.__proto__ = Buffer.prototype, t }, Buffer.from = function (t, r, e) { return f(null, t, r, e) }, Buffer.TYPED_ARRAY_SUPPORT && (Buffer.prototype.__proto__ = Uint8Array.prototype, Buffer.__proto__ = Uint8Array, "undefined" != typeof Symbol && Symbol.species && Buffer[Symbol.species] === Buffer && Object.defineProperty(Buffer, Symbol.species, { value: null, configurable: !0 })), Buffer.alloc = function (t, r, e) { return a(null, t, r, e) }, Buffer.allocUnsafe = function (t) { return s(null, t) }, Buffer.allocUnsafeSlow = function (t) { return s(null, t) }, Buffer.isBuffer = function (t) { return !(null == t || !t._isBuffer) }, Buffer.compare = function (t, r) { if (!Buffer.isBuffer(t) || !Buffer.isBuffer(r)) throw new TypeError("Arguments must be Buffers"); if (t === r) return 0; for (var e = t.length, n = r.length, i = 0, o = Math.min(e, n); i < o; ++i)if (t[i] !== r[i]) { e = t[i], n = r[i]; break } return e < n ? -1 : n < e ? 1 : 0 }, Buffer.isEncoding = function (t) { switch (String(t).toLowerCase()) { case "hex": case "utf8": case "utf-8": case "ascii": case "latin1": case "binary": case "base64": case "ucs2": case "ucs-2": case "utf16le": case "utf-16le": return !0; default: return !1 } }, Buffer.concat = function (t, r) { if (!Q(t)) throw new TypeError('"list" argument must be an Array of Buffers'); if (0 === t.length) return Buffer.alloc(0); var e; if (void 0 === r) for (r = 0, e = 0; e < t.length; ++e)r += t[e].length; var n = Buffer.allocUnsafe(r), i = 0; for (e = 0; e < t.length; ++e) { var o = t[e]; if (!Buffer.isBuffer(o)) throw new TypeError('"list" argument must be an Array of Buffers'); o.copy(n, i), i += o.length } return n }, Buffer.byteLength = v, Buffer.prototype._isBuffer = !0, Buffer.prototype.swap16 = function () { var t = this.length; if (t % 2 !== 0) throw new RangeError("Buffer size must be a multiple of 16-bits"); for (var r = 0; r < t; r += 2)b(this, r, r + 1); return this }, Buffer.prototype.swap32 = function () { var t = this.length; if (t % 4 !== 0) throw new RangeError("Buffer size must be a multiple of 32-bits"); for (var r = 0; r < t; r += 4)b(this, r, r + 3), b(this, r + 1, r + 2); return this }, Buffer.prototype.swap64 = function () { var t = this.length; if (t % 8 !== 0) throw new RangeError("Buffer size must be a multiple of 64-bits"); for (var r = 0; r < t; r += 8)b(this, r, r + 7), b(this, r + 1, r + 6), b(this, r + 2, r + 5), b(this, r + 3, r + 4); return this }, Buffer.prototype.toString = function () { var t = 0 | this.length; return 0 === t ? "" : 0 === arguments.length ? k(this, 0, t) : g.apply(this, arguments) }, Buffer.prototype.equals = function (t) { if (!Buffer.isBuffer(t)) throw new TypeError("Argument must be a Buffer"); return this === t || 0 === Buffer.compare(this, t) }, Buffer.prototype.inspect = function () { var t = "", r = e.INSPECT_MAX_BYTES; return this.length > 0 && (t = this.toString("hex", 0, r).match(/.{2}/g).join(" "), this.length > r && (t += " ... ")), "<Buffer " + t + ">" }, Buffer.prototype.compare = function (t, r, e, n, i) { if (!Buffer.isBuffer(t)) throw new TypeError("Argument must be a Buffer"); if (void 0 === r && (r = 0), void 0 === e && (e = t ? t.length : 0), void 0 === n && (n = 0), void 0 === i && (i = this.length), r < 0 || e > t.length || n < 0 || i > this.length) throw new RangeError("out of range index"); if (n >= i && r >= e) return 0; if (n >= i) return -1; if (r >= e) return 1; if (r >>>= 0, e >>>= 0, n >>>= 0, i >>>= 0, this === t) return 0; for (var o = i - n, f = e - r, u = Math.min(o, f), a = this.slice(n, i), s = t.slice(r, e), c = 0; c < u; ++c)if (a[c] !== s[c]) { o = a[c], f = s[c]; break } return o < f ? -1 : f < o ? 1 : 0 }, Buffer.prototype.includes = function (t, r, e) { return this.indexOf(t, r, e) !== -1 }, Buffer.prototype.indexOf = function (t, r, e) { return w(this, t, r, e, !0) }, Buffer.prototype.lastIndexOf = function (t, r, e) { return w(this, t, r, e, !1) }, Buffer.prototype.write = function (t, r, e, n) { if (void 0 === r) n = "utf8", e = this.length, r = 0; else if (void 0 === e && "string" == typeof r) n = r, e = this.length, r = 0; else { if (!isFinite(r)) throw new Error("Buffer.write(string, encoding, offset[, length]) is no longer supported"); r = 0 | r, isFinite(e) ? (e = 0 | e, void 0 === n && (n = "utf8")) : (n = e, e = void 0) } var i = this.length - r; if ((void 0 === e || e > i) && (e = i), t.length > 0 && (e < 0 || r < 0) || r > this.length) throw new RangeError("Attempt to write outside buffer bounds"); n || (n = "utf8"); for (var o = !1; ;)switch (n) { case "hex": return A(this, t, r, e); case "utf8": case "utf-8": return m(this, t, r, e); case "ascii": return x(this, t, r, e); case "latin1": case "binary": return B(this, t, r, e); case "base64": return U(this, t, r, e); case "ucs2": case "ucs-2": case "utf16le": case "utf-16le": return P(this, t, r, e); default: if (o) throw new TypeError("Unknown encoding: " + n); n = ("" + n).toLowerCase(), o = !0 } }, Buffer.prototype.toJSON = function () { return { type: "Buffer", data: Array.prototype.slice.call(this.arr || this, 0) } }; var $ = 4096; Buffer.prototype.slice = function (t, r) { var e = this.length; t = ~~t, r = void 0 === r ? e : ~~r, t < 0 ? (t += e, t < 0 && (t = 0)) : t > e && (t = e), r < 0 ? (r += e, r < 0 && (r = 0)) : r > e && (r = e), r < t && (r = t); var n; if (Buffer.TYPED_ARRAY_SUPPORT) n = this.subarray(t, r), n.__proto__ = Buffer.prototype; else { var i = r - t; n = new Buffer(i, void 0); for (var o = 0; o < i; ++o)n[o] = this[o + t] } return n }, Buffer.prototype.readUIntLE = function (t, r, e) { t = 0 | t, r = 0 | r, e || C(t, r, this.length); for (var n = this[t], i = 1, o = 0; ++o < r && (i *= 256);)n += this[t + o] * i; return n }, Buffer.prototype.readUIntBE = function (t, r, e) { t = 0 | t, r = 0 | r, e || C(t, r, this.length); for (var n = this[t + --r], i = 1; r > 0 && (i *= 256);)n += this[t + --r] * i; return n }, Buffer.prototype.readUInt8 = function (t, r) { return r || C(t, 1, this.length), this[t] }, Buffer.prototype.readUInt16LE = function (t, r) { return r || C(t, 2, this.length), this[t] | this[t + 1] << 8 }, Buffer.prototype.readUInt16BE = function (t, r) { return r || C(t, 2, this.length), this[t] << 8 | this[t + 1] }, Buffer.prototype.readUInt32LE = function (t, r) { return r || C(t, 4, this.length), (this[t] | this[t + 1] << 8 | this[t + 2] << 16) + 16777216 * this[t + 3] }, Buffer.prototype.readUInt32BE = function (t, r) { return r || C(t, 4, this.length), 16777216 * this[t] + (this[t + 1] << 16 | this[t + 2] << 8 | this[t + 3]) }, Buffer.prototype.readIntLE = function (t, r, e) { t = 0 | t, r = 0 | r, e || C(t, r, this.length); for (var n = this[t], i = 1, o = 0; ++o < r && (i *= 256);)n += this[t + o] * i; return i *= 128, n >= i && (n -= Math.pow(2, 8 * r)), n }, Buffer.prototype.readIntBE = function (t, r, e) { t = 0 | t, r = 0 | r, e || C(t, r, this.length); for (var n = r, i = 1, o = this[t + --n]; n > 0 && (i *= 256);)o += this[t + --n] * i; return i *= 128, o >= i && (o -= Math.pow(2, 8 * r)), o }, Buffer.prototype.readInt8 = function (t, r) { return r || C(t, 1, this.length), 128 & this[t] ? (255 - this[t] + 1) * -1 : this[t] }, Buffer.prototype.readInt16LE = function (t, r) { r || C(t, 2, this.length); var e = this[t] | this[t + 1] << 8; return 32768 & e ? 4294901760 | e : e }, Buffer.prototype.readInt16BE = function (t, r) { r || C(t, 2, this.length); var e = this[t + 1] | this[t] << 8; return 32768 & e ? 4294901760 | e : e }, Buffer.prototype.readInt32LE = function (t, r) { return r || C(t, 4, this.length), this[t] | this[t + 1] << 8 | this[t + 2] << 16 | this[t + 3] << 24 }, Buffer.prototype.readInt32BE = function (t, r) { return r || C(t, 4, this.length), this[t] << 24 | this[t + 1] << 16 | this[t + 2] << 8 | this[t + 3] }, Buffer.prototype.readFloatLE = function (t, r) { return r || C(t, 4, this.length), K.read(this, t, !0, 23, 4) }, Buffer.prototype.readFloatBE = function (t, r) { return r || C(t, 4, this.length), K.read(this, t, !1, 23, 4) }, Buffer.prototype.readDoubleLE = function (t, r) { return r || C(t, 8, this.length), K.read(this, t, !0, 52, 8) }, Buffer.prototype.readDoubleBE = function (t, r) { return r || C(t, 8, this.length), K.read(this, t, !1, 52, 8) }, Buffer.prototype.writeUIntLE = function (t, r, e, n) { if (t = +t, r = 0 | r, e = 0 | e, !n) { var i = Math.pow(2, 8 * e) - 1; D(this, t, r, e, i, 0) } var o = 1, f = 0; for (this[r] = 255 & t; ++f < e && (o *= 256);)this[r + f] = t / o & 255; return r + e }, Buffer.prototype.writeUIntBE = function (t, r, e, n) { if (t = +t, r = 0 | r, e = 0 | e, !n) { var i = Math.pow(2, 8 * e) - 1; D(this, t, r, e, i, 0) } var o = e - 1, f = 1; for (this[r + o] = 255 & t; --o >= 0 && (f *= 256);)this[r + o] = t / f & 255; return r + e }, Buffer.prototype.writeUInt8 = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 1, 255, 0), Buffer.TYPED_ARRAY_SUPPORT || (t = Math.floor(t)), this[r] = 255 & t, r + 1 }, Buffer.prototype.writeUInt16LE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 2, 65535, 0), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = 255 & t, this[r + 1] = t >>> 8) : O(this, t, r, !0), r + 2 }, Buffer.prototype.writeUInt16BE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 2, 65535, 0), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = t >>> 8, this[r + 1] = 255 & t) : O(this, t, r, !1), r + 2 }, Buffer.prototype.writeUInt32LE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 4, 4294967295, 0), Buffer.TYPED_ARRAY_SUPPORT ? (this[r + 3] = t >>> 24, this[r + 2] = t >>> 16, this[r + 1] = t >>> 8, this[r] = 255 & t) : L(this, t, r, !0), r + 4 }, Buffer.prototype.writeUInt32BE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 4, 4294967295, 0), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = t >>> 24, this[r + 1] = t >>> 16, this[r + 2] = t >>> 8, this[r + 3] = 255 & t) : L(this, t, r, !1), r + 4 }, Buffer.prototype.writeIntLE = function (t, r, e, n) { if (t = +t, r = 0 | r, !n) { var i = Math.pow(2, 8 * e - 1); D(this, t, r, e, i - 1, -i) } var o = 0, f = 1, u = 0; for (this[r] = 255 & t; ++o < e && (f *= 256);)t < 0 && 0 === u && 0 !== this[r + o - 1] && (u = 1), this[r + o] = (t / f >> 0) - u & 255; return r + e }, Buffer.prototype.writeIntBE = function (t, r, e, n) { if (t = +t, r = 0 | r, !n) { var i = Math.pow(2, 8 * e - 1); D(this, t, r, e, i - 1, -i) } var o = e - 1, f = 1, u = 0; for (this[r + o] = 255 & t; --o >= 0 && (f *= 256);)t < 0 && 0 === u && 0 !== this[r + o + 1] && (u = 1), this[r + o] = (t / f >> 0) - u & 255; return r + e }, Buffer.prototype.writeInt8 = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 1, 127, -128), Buffer.TYPED_ARRAY_SUPPORT || (t = Math.floor(t)), t < 0 && (t = 255 + t + 1), this[r] = 255 & t, r + 1 }, Buffer.prototype.writeInt16LE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 2, 32767, -32768), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = 255 & t, this[r + 1] = t >>> 8) : O(this, t, r, !0), r + 2 }, Buffer.prototype.writeInt16BE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 2, 32767, -32768), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = t >>> 8, this[r + 1] = 255 & t) : O(this, t, r, !1), r + 2 }, Buffer.prototype.writeInt32LE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 4, 2147483647, -2147483648), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = 255 & t, this[r + 1] = t >>> 8, this[r + 2] = t >>> 16, this[r + 3] = t >>> 24) : L(this, t, r, !0), r + 4 }, Buffer.prototype.writeInt32BE = function (t, r, e) { return t = +t, r = 0 | r, e || D(this, t, r, 4, 2147483647, -2147483648), t < 0 && (t = 4294967295 + t + 1), Buffer.TYPED_ARRAY_SUPPORT ? (this[r] = t >>> 24, this[r + 1] = t >>> 16, this[r + 2] = t >>> 8, this[r + 3] = 255 & t) : L(this, t, r, !1), r + 4 }, Buffer.prototype.writeFloatLE = function (t, r, e) { return N(this, t, r, !0, e) }, Buffer.prototype.writeFloatBE = function (t, r, e) { return N(this, t, r, !1, e) }, Buffer.prototype.writeDoubleLE = function (t, r, e) { return F(this, t, r, !0, e) }, Buffer.prototype.writeDoubleBE = function (t, r, e) { return F(this, t, r, !1, e) }, Buffer.prototype.copy = function (t, r, e, n) { if (e || (e = 0), n || 0 === n || (n = this.length), r >= t.length && (r = t.length), r || (r = 0), n > 0 && n < e && (n = e), n === e) return 0; if (0 === t.length || 0 === this.length) return 0; if (r < 0) throw new RangeError("targetStart out of bounds"); if (e < 0 || e >= this.length) throw new RangeError("sourceStart out of bounds"); if (n < 0) throw new RangeError("sourceEnd out of bounds"); n > this.length && (n = this.length), t.length - r < n - e && (n = t.length - r + e); var i, o = n - e; if (this === t && e < r && r < n) for (i = o - 1; i >= 0; --i)t[i + r] = this[i + e]; else if (o < 1e3 || !Buffer.TYPED_ARRAY_SUPPORT) for (i = 0; i < o; ++i)t[i + r] = this[i + e]; else Uint8Array.prototype.set.call(t, this.subarray(e, e + o), r); return o }, Buffer.prototype.fill = function (t, r, e, n) { if ("string" == typeof t) { if ("string" == typeof r ? (n = r, r = 0, e = this.length) : "string" == typeof e && (n = e, e = this.length), 1 === t.length) { var i = t.charCodeAt(0); i < 256 && (t = i) } if (void 0 !== n && "string" != typeof n) throw new TypeError("encoding must be a string"); if ("string" == typeof n && !Buffer.isEncoding(n)) throw new TypeError("Unknown encoding: " + n) } else "number" == typeof t && (t = 255 & t); if (r < 0 || this.length < r || this.length < e) throw new RangeError("Out of range index"); if (e <= r) return this; r >>>= 0, e = void 0 === e ? this.length : e >>> 0, t || (t = 0); var o; if ("number" == typeof t) for (o = r; o < e; ++o)this[o] = t; else { var f = Buffer.isBuffer(t) ? t : q(new Buffer(t, n).toString()), u = f.length; for (o = 0; o < e - r; ++o)this[o + r] = f[o % u] } return this }; var tt = /[^+\/0-9A-Za-z-_]/g
			}).call(this, "undefined" != typeof global ? global : "undefined" != typeof self ? self : "undefined" != typeof window ? window : {})
		}, { "base64-js": 30, ieee754: 32, isarray: 34 }], 30: [function (t, r, e) { "use strict"; function n(t) { var r = t.length; if (r % 4 > 0) throw new Error("Invalid string. Length must be a multiple of 4"); return "=" === t[r - 2] ? 2 : "=" === t[r - 1] ? 1 : 0 } function i(t) { return 3 * t.length / 4 - n(t) } function o(t) { var r, e, i, o, f, u, a = t.length; f = n(t), u = new h(3 * a / 4 - f), i = f > 0 ? a - 4 : a; var s = 0; for (r = 0, e = 0; r < i; r += 4, e += 3)o = c[t.charCodeAt(r)] << 18 | c[t.charCodeAt(r + 1)] << 12 | c[t.charCodeAt(r + 2)] << 6 | c[t.charCodeAt(r + 3)], u[s++] = o >> 16 & 255, u[s++] = o >> 8 & 255, u[s++] = 255 & o; return 2 === f ? (o = c[t.charCodeAt(r)] << 2 | c[t.charCodeAt(r + 1)] >> 4, u[s++] = 255 & o) : 1 === f && (o = c[t.charCodeAt(r)] << 10 | c[t.charCodeAt(r + 1)] << 4 | c[t.charCodeAt(r + 2)] >> 2, u[s++] = o >> 8 & 255, u[s++] = 255 & o), u } function f(t) { return s[t >> 18 & 63] + s[t >> 12 & 63] + s[t >> 6 & 63] + s[63 & t] } function u(t, r, e) { for (var n, i = [], o = r; o < e; o += 3)n = (t[o] << 16) + (t[o + 1] << 8) + t[o + 2], i.push(f(n)); return i.join("") } function a(t) { for (var r, e = t.length, n = e % 3, i = "", o = [], f = 16383, a = 0, c = e - n; a < c; a += f)o.push(u(t, a, a + f > c ? c : a + f)); return 1 === n ? (r = t[e - 1], i += s[r >> 2], i += s[r << 4 & 63], i += "==") : 2 === n && (r = (t[e - 2] << 8) + t[e - 1], i += s[r >> 10], i += s[r >> 4 & 63], i += s[r << 2 & 63], i += "="), o.push(i), o.join("") } e.byteLength = i, e.toByteArray = o, e.fromByteArray = a; for (var s = [], c = [], h = "undefined" != typeof Uint8Array ? Uint8Array : Array, l = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", p = 0, d = l.length; p < d; ++p)s[p] = l[p], c[l.charCodeAt(p)] = p; c["-".charCodeAt(0)] = 62, c["_".charCodeAt(0)] = 63 }, {}], 31: [function (t, r, e) { function n() { if (!(this instanceof n)) return new n } !function (t) { function e(t) { for (var r in s) t[r] = s[r]; return t } function n(t, r) { return u(this, t).push(r), this } function i(t, r) { function e() { o.call(n, t, e), r.apply(this, arguments) } var n = this; return e.originalListener = r, u(n, t).push(e), n } function o(t, r) { function e(t) { return t !== r && t.originalListener !== r } var n, i = this; if (arguments.length) { if (r) { if (n = u(i, t, !0)) { if (n = n.filter(e), !n.length) return o.call(i, t); i[a][t] = n } } else if (n = i[a], n && (delete n[t], !Object.keys(n).length)) return o.call(i) } else delete i[a]; return i } function f(t, r) { function e(t) { t.call(o) } function n(t) { t.call(o, r) } function i(t) { t.apply(o, s) } var o = this, f = u(o, t, !0); if (!f) return !1; var a = arguments.length; if (1 === a) f.forEach(e); else if (2 === a) f.forEach(n); else { var s = Array.prototype.slice.call(arguments, 1); f.forEach(i) } return !!f.length } function u(t, r, e) { if (!e || t[a]) { var n = t[a] || (t[a] = {}); return n[r] || (n[r] = []) } } "undefined" != typeof r && (r.exports = t); var a = "listeners", s = { on: n, once: i, off: o, emit: f }; e(t.prototype), t.mixin = e }(n) }, {}], 32: [function (t, r, e) { e.read = function (t, r, e, n, i) { var o, f, u = 8 * i - n - 1, a = (1 << u) - 1, s = a >> 1, c = -7, h = e ? i - 1 : 0, l = e ? -1 : 1, p = t[r + h]; for (h += l, o = p & (1 << -c) - 1, p >>= -c, c += u; c > 0; o = 256 * o + t[r + h], h += l, c -= 8); for (f = o & (1 << -c) - 1, o >>= -c, c += n; c > 0; f = 256 * f + t[r + h], h += l, c -= 8); if (0 === o) o = 1 - s; else { if (o === a) return f ? NaN : (p ? -1 : 1) * (1 / 0); f += Math.pow(2, n), o -= s } return (p ? -1 : 1) * f * Math.pow(2, o - n) }, e.write = function (t, r, e, n, i, o) { var f, u, a, s = 8 * o - i - 1, c = (1 << s) - 1, h = c >> 1, l = 23 === i ? Math.pow(2, -24) - Math.pow(2, -77) : 0, p = n ? 0 : o - 1, d = n ? 1 : -1, y = r < 0 || 0 === r && 1 / r < 0 ? 1 : 0; for (r = Math.abs(r), isNaN(r) || r === 1 / 0 ? (u = isNaN(r) ? 1 : 0, f = c) : (f = Math.floor(Math.log(r) / Math.LN2), r * (a = Math.pow(2, -f)) < 1 && (f--, a *= 2), r += f + h >= 1 ? l / a : l * Math.pow(2, 1 - h), r * a >= 2 && (f++, a /= 2), f + h >= c ? (u = 0, f = c) : f + h >= 1 ? (u = (r * a - 1) * Math.pow(2, i), f += h) : (u = r * Math.pow(2, h - 1) * Math.pow(2, i), f = 0)); i >= 8; t[e + p] = 255 & u, p += d, u /= 256, i -= 8); for (f = f << i | u, s += i; s > 0; t[e + p] = 255 & f, p += d, f /= 256, s -= 8); t[e + p - d] |= 128 * y } }, {}], 33: [function (t, r, e) { (function (Buffer) { var t, r, n, i; !function (e) { function o(t, r, n) { function i(t, r, e, n) { return this instanceof i ? v(this, t, r, e, n) : new i(t, r, e, n) } function o(t) { return !(!t || !t[F]) } function v(t, r, e, n, i) { if (E && A && (r instanceof A && (r = new E(r)), n instanceof A && (n = new E(n))), !(r || e || n || g)) return void (t.buffer = h(m, 0)); if (!s(r, e)) { var o = g || Array; i = e, n = r, e = 0, r = new o(8) } t.buffer = r, t.offset = e |= 0, b !== typeof n && ("string" == typeof n ? x(r, e, n, i || 10) : s(n, i) ? c(r, e, n, i) : "number" == typeof i ? (k(r, e + T, n), k(r, e + S, i)) : n > 0 ? O(r, e, n) : n < 0 ? L(r, e, n) : c(r, e, m, 0)) } function x(t, r, e, n) { var i = 0, o = e.length, f = 0, u = 0; "-" === e[0] && i++; for (var a = i; i < o;) { var s = parseInt(e[i++], n); if (!(s >= 0)) break; u = u * n + s, f = f * n + Math.floor(u / B), u %= B } a && (f = ~f, u ? u = B - u : f++), k(t, r + T, f), k(t, r + S, u) } function P() { var t = this.buffer, r = this.offset, e = _(t, r + T), i = _(t, r + S); return n || (e |= 0), e ? e * B + i : i } function R(t) { var r = this.buffer, e = this.offset, i = _(r, e + T), o = _(r, e + S), f = "", u = !n && 2147483648 & i; for (u && (i = ~i, o = B - o), t = t || 10; ;) { var a = i % t * B + o; if (i = Math.floor(i / t), o = Math.floor(a / t), f = (a % t).toString(t) + f, !i && !o) break } return u && (f = "-" + f), f } function k(t, r, e) { t[r + D] = 255 & e, e >>= 8, t[r + C] = 255 & e, e >>= 8, t[r + Y] = 255 & e, e >>= 8, t[r + I] = 255 & e } function _(t, r) { return t[r + I] * U + (t[r + Y] << 16) + (t[r + C] << 8) + t[r + D] } var T = r ? 0 : 4, S = r ? 4 : 0, I = r ? 0 : 3, Y = r ? 1 : 2, C = r ? 2 : 1, D = r ? 3 : 0, O = r ? l : d, L = r ? p : y, M = i.prototype, N = "is" + t, F = "_" + N; return M.buffer = void 0, M.offset = 0, M[F] = !0, M.toNumber = P, M.toString = R, M.toJSON = P, M.toArray = f, w && (M.toBuffer = u), E && (M.toArrayBuffer = a), i[N] = o, e[t] = i, i } function f(t) { var r = this.buffer, e = this.offset; return g = null, t !== !1 && 0 === e && 8 === r.length && x(r) ? r : h(r, e) } function u(t) { var r = this.buffer, e = this.offset; if (g = w, t !== !1 && 0 === e && 8 === r.length && Buffer.isBuffer(r)) return r; var n = new w(8); return c(n, 0, r, e), n } function a(t) { var r = this.buffer, e = this.offset, n = r.buffer; if (g = E, t !== !1 && 0 === e && n instanceof A && 8 === n.byteLength) return n; var i = new E(8); return c(i, 0, r, e), i.buffer } function s(t, r) { var e = t && t.length; return r |= 0, e && r + 8 <= e && "string" != typeof t[r] } function c(t, r, e, n) { r |= 0, n |= 0; for (var i = 0; i < 8; i++)t[r++] = 255 & e[n++] } function h(t, r) { return Array.prototype.slice.call(t, r, r + 8) } function l(t, r, e) { for (var n = r + 8; n > r;)t[--n] = 255 & e, e /= 256 } function p(t, r, e) { var n = r + 8; for (e++; n > r;)t[--n] = 255 & -e ^ 255, e /= 256 } function d(t, r, e) { for (var n = r + 8; r < n;)t[r++] = 255 & e, e /= 256 } function y(t, r, e) { var n = r + 8; for (e++; r < n;)t[r++] = 255 & -e ^ 255, e /= 256 } function v(t) { return !!t && "[object Array]" == Object.prototype.toString.call(t) } var g, b = "undefined", w = b !== typeof Buffer && Buffer, E = b !== typeof Uint8Array && Uint8Array, A = b !== typeof ArrayBuffer && ArrayBuffer, m = [0, 0, 0, 0, 0, 0, 0, 0], x = Array.isArray || v, B = 4294967296, U = 16777216; t = o("Uint64BE", !0, !0), r = o("Int64BE", !0, !1), n = o("Uint64LE", !1, !0), i = o("Int64LE", !1, !1) }("object" == typeof e && "string" != typeof e.nodeName ? e : this || {}) }).call(this, t("buffer").Buffer) }, { buffer: 29 }], 34: [function (t, r, e) { var n = {}.toString; r.exports = Array.isArray || function (t) { return "[object Array]" == n.call(t) } }, {}]
	}, {}, [1])(1)
});



KaithemWidgetApiSnackbar = function (m,d)
{

	if (kaithemapi.currentSnackbar)
	{
		kaithemapi.currentSnackbar.remove()
	}

	if (m == '')
	{
		return
	}
	// create a new div element
	const newDiv = document.createElement("div");

	// and give it some content
	//const newContent = document.createTextNode(m);

	// add the text node to the newly created div
	//newDiv.appendChild(newContent);

	newDiv.innerHTML=m

	// add the newly created element and its content into the DOM
	const currentDiv = document.getElementById("div1");
	newDiv.onclick = function () {
		if (confirm("Dismiss Message?")) {
			newDiv.remove()
		}
		
	}

	var sb = {
		minWidth: "250px",
		maxWidth: "70%",
		margin: "auto",
		backgroundColor: "#333",
		color: "#fff",
		textAlign: "center",
		borderRadius: "2px",
		padding: "16px",
		position: "fixed",
		zIndex: 10000,
		top: "30px",
		fontSize: "32px",
		WebkitAnimation: "fadein 0.5s, fadeout 0.5s 2.5s",
		animation: "fadein 0.5s, fadeout 0.5s 2.5s",
		borderRadius: '5px',
		borderStyle: 'outset',
		borderColor:"#fff"
	
	}
	for (i in sb) {
		newDiv.style[i] = sb[i]
	}
	document.body.appendChild(newDiv);
	kaithemapi.currentSnackbar = newDiv;

	
	setTimeout(function(){newDiv.remove()}, (d||5)*1000);
}

KaithemApi = function () {
	var x = {

		toSend: [],
		lastDidSnackbarError:0,
		first_error: 1,
		serverMsgCallbacks: {
			"__WIDGETERROR__": [
				function (m) {
					console.error(m);
					if (lastDidSnackbarError < Date.now() + 60000)
					{
						lastDidSnackbarError=Date.now()
						KaithemWidgetApiSnackbar("Ratelimited msg"+m)
					}
				}
			],
			"__SHOWMESSAGE__": [
				function (m) {
					alert(m);
				}
			],
			"__SHOWSNACKBAR__": [
				function (m) {
					KaithemWidgetApiSnackbar(m[0],m[1]);
				}
			],
			"__KEYMAP__": [
				function (m) {
					self.uuidToWidgetId[m[0]] = m[1];
					self.widgetIDtoUUID[m[1]] = m[0];
				}
			]


		},

		//Unused for now
		uuidToWidgetId: {},
		widgetIDtoUUID: {},


		subscriptions: [],
		connection: 0,
		use_mp: 0,

		//Doe nothinh untiul we connect, we just send that buffered data in the connection handler.
		//Todo don't dynamically define this at all?
		poll_ratelimited : function () { },

		subscribe: function (key, callback) {


			if (key in this.serverMsgCallbacks) {
				this.serverMsgCallbacks[key].push(callback);
			}

			else {
				this.serverMsgCallbacks[key] = [callback];
			}

			//If the ws is open, send the subs list, else wait for the connection handler to do it when we first reconnect.
			if (this.connection) {
				if (this.connection.readyState == 1) {
					var j = { "subsc": Object.keys(this.serverMsgCallbacks), "upd": [] }
					this.connection.send(JSON.stringify(j))
				}
			}
		},

		unsubscribe: function (key, callback) {
			var arr = this.serverMsgCallbacks[key];


			if (key in arr) {

				for (var i = 0; i < arr.length; i++) { if (arr[i] === callback) { arr.splice(i, 1); } }
			}

			if (arr.length == 0) {

				//Delete the now unused mapping
				if (key in this.uuidToWidgetId) {
					delete this.widgetIDtoUUID[this.uuidToWidgetId[key]];
					delete this.uuidToWidgetId[key];
				}



				delete this.serverMsgCallbacks[key]


				//If the ws is open, send the subs list. If not, we by definition aren't subscribed, and we already removed it from the local list.
				if (this.connection) {
					if (this.connection.readyState == 1) {
						var j = { "unsub": [key], "upd": [] }
						this.connection.send(JSON.stringify(j))
					}
				}
			}
		},

		sendErrorMessage: function (error) {
			if (this.lastErrMsg) {
				if (this.lastErrMsg > (Date.now() - 1500000)) {
					return
				}
				this.lastErrMsg = Date.now();
			}
			if (this.connection) {
				if (this.connection.readyState == 1) {
					var j = { "telemetry.err": error }
					this.connection.send(JSON.stringify(j))
				}
			}
		},

		register: function (key, callback) {
			this.subscribe(key, callback);
		},

		setValue: function (key, value) {
			this.toSend.push([key, value])
			this.poll_ratelimited();
		},

		sendValue: function (key, value) {
			this.toSend.push([key, value])
			this.poll_ratelimited();
		},

		can_show_error: 1,
		usual_delay: 0,
		reconnect_timeout: 1500,

		connect: function () {
			var apiobj = this


			this.connection = new WebSocket(window.location.protocol.replace("http", "ws") + "//" + window.location.host + '/widgets/ws');

			this.connection.onclose = function (e) {
				console.log(e);
				setTimeout(apiobj.connect, apiobj.reconnect_timeout);
			};

			this.connection.onerror = function (e) {
				console.log(e);

				if (apiobj.connection.readyState != 1) {
					apiobj.reconnect_timeout = Math.min(apiobj.reconnect_timeout * 2, 20000);
					setTimeout(apiobj.connect, apiobj.reconnect_timeout);
				}
			};


			this.connection.onmessage = function (e) {
				try {
					if (typeof (e.data) == 'object') {
						apiobj.use_mp = 1;

						var resp = [0];
						e.data.arrayBuffer().then(function (buffer) {
							var buffer2 = new Uint8Array(buffer);
							try {
								apiobj.connection.handleIncoming(msgpack.decode(buffer2));
							}
							catch (err) {
								apiobj.sendErrorMessage(window.location.href + "\n" + err.stack)
								console.error(err.stack)
							}
						})

					}
					else {
						var resp = JSON.parse(e.data);
						apiobj.connection.handleIncoming(resp)
					}
				}
				catch (err) {
					apiobj.sendErrorMessage(window.location.href + "\n" + err.stack)
					console.error(err.stack)
				}


			}

			this.connection.handleIncoming = function (resp) {
				//Iterate messages
				for (var n = 0; n < resp.length; n++) {
					i = resp[n]
					for (j in apiobj.serverMsgCallbacks[i[0]]) {
						apiobj.serverMsgCallbacks[i[0]][j](resp[n][1]);
					}
				}
			}
			this.connection.onopen = function (e) {
				var j = JSON.stringify({ "subsc": Object.keys(apiobj.serverMsgCallbacks), "req": [], "upd": [["__url__", window.location.href]] })
				apiobj.connection.send(j)
				console.log("WS Connection Initialized");
				apiobj.reconnect_timeout = 1500;
				window.setTimeout(function () { apiobj.wpoll() }, 250);
			}

			this.wpoll = function () {
				//Don't bother sending if we aren'y connected
				if (this.connection.readyState == 1) {
					if (this.toSend.length > 0) {
						var toSend = { 'upd': this.toSend, };
						if (this.use_mp) {
							var j = new Blob([msgpack.encode(toSend)]);
						}
						else {
							var j = JSON.stringify(toSend);
						}

						this.connection.send(j);
						this.toSend = [];
					}

				}

				if (this.toSend.length > 0) {
					window.setTimeout(this.poll_ratelimited, 120);
				}

				this.pollWaiting = false
			}

			this.lastSend = 0
			this.pollWaiting = false

			//Check if wpoll has ran in the last 44ms. If not run it.
			//If it has, set a timeout to check again.
			//This code is only possible because of the JS single threadedness.
			this.poll_ratelimited = function () {
				var d = new Date();
				var n = d.getTime();

				if (n - this.lastSend > 44) {
					this.lastSend = n;
					this.wpoll()
				}
				//If we are already waiting on a poll, don't re-poll.
				else {
					if (this.pollWaiting) {
						return
					}
					this.pollWaiting = true;
					window.setTimeout(this.poll_ratelimited, 50 - (n - this.lastSend))
				}
			}



		}
	}
	x.self = x
	return x
}
kaithemapi = KaithemApi()

if (!window.onerror) {
	var globalPageErrorHandler = function (msg, url, line) {
		kaithemapi.sendErrorMessage(url + '\n' + line + "\n\n" + msg)
	}
	window.onerror = globalPageErrorHandler
}
//Backwards compatibility hack
//Todo deprecate someday? or not.
KWidget_subscribe = function (a, b) { kaithemapi.subscribe(a, b) }
KWidget_setValue = function (a, b) { kaithemapi.setValue(a, b) }
KWidget_sendValue = function (a, b) { kaithemapi.sendValue(a, b) }

setTimeout(function () { kaithemapi.connect() }, 100)
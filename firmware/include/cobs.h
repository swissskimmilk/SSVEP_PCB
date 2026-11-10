// Consistent Overhead Byte Stuffing, used to frame packets on USB CDC (0x00 ends a frame).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace cobs {

constexpr size_t max_encoded(size_t n) { return n + n / 254 + 1; }

// Returns the encoded length (no trailing 0x00).
inline size_t encode(const uint8_t* in, size_t n, uint8_t* out) {
    size_t code_at = 0, o = 1;
    uint8_t code = 1;
    for (size_t i = 0; i < n; i++) {
        if (in[i] == 0) {
            out[code_at] = code;
            code_at = o++;
            code = 1;
        } else {
            out[o++] = in[i];
            if (++code == 0xFF) {
                out[code_at] = code;
                code_at = o++;
                code = 1;
            }
        }
    }
    out[code_at] = code;
    return o;
}

// Returns the decoded length, or 0 on a malformed frame.
inline size_t decode(const uint8_t* in, size_t n, uint8_t* out) {
    size_t i = 0, o = 0;
    while (i < n) {
        const uint8_t code = in[i++];
        if (code == 0 || i + code - 1 > n) return 0;
        for (uint8_t k = 1; k < code; k++) out[o++] = in[i++];
        if (code != 0xFF && i < n) out[o++] = 0;
    }
    return o;
}

}  // namespace cobs

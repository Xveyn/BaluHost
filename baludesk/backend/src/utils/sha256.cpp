/* Minimal SHA256 implementation based on public domain reference code.
   This file provides sha256_file() used by ChangeDetector.
*/
#include "sha256.h"
#include <fstream>
#include <vector>
#include <sstream>
#include <iomanip>

namespace baludesk {

// Platform-independent minimal SHA256 implementation.
// Note: For production, prefer linking a vetted crypto library (OpenSSL/BoringSSL).

// --- Begin tiny SHA256 implementation ---
// Adapted from public-domain compact implementations.

typedef unsigned char uint8;
typedef unsigned int uint32;
typedef unsigned long long uint64;

static uint32 rotr(uint32 x, uint32 n) { return (x >> n) | (x << (32 - n)); }

static void sha256_transform(const uint8* chunk, uint32 h[8]) {
    static const uint32 k[64] = {
        0x428a2f98ul,0x71374491ul,0xb5c0fbcful,0xe9b5dba5ul,0x3956c25bul,0x59f111f1ul,0x923f82a4ul,0xab1c5ed5ul,
        0xd807aa98ul,0x12835b01ul,0x243185beul,0x550c7dc3ul,0x72be5d74ul,0x80deb1feul,0x9bdc06a7ul,0xc19bf174ul,
        0xe49b69c1ul,0xefbe4786ul,0x0fc19dc6ul,0x240ca1ccul,0x2de92c6ful,0x4a7484aaul,0x5cb0a9dcul,0x76f988daul,
        0x983e5152ul,0xa831c66dul,0xb00327c8ul,0xbf597fc7ul,0xc6e00bf3ul,0xd5a79147ul,0x06ca6351ul,0x14292967ul,
        0x27b70a85ul,0x2e1b2138ul,0x4d2c6dfcul,0x53380d13ul,0x650a7354ul,0x766a0abbul,0x81c2c92eul,0x92722c85ul,
        0xa2bfe8a1ul,0xa81a664bul,0xc24b8b70ul,0xc76c51a3ul,0xd192e819ul,0xd6990624ul,0xf40e3585ul,0x106aa070ul,
        0x19a4c116ul,0x1e376c08ul,0x2748774cul,0x34b0bcb5ul,0x391c0cb3ul,0x4ed8aa4aul,0x5b9cca4ful,0x682e6ff3ul,
        0x748f82eeul,0x78a5636ful,0x84c87814ul,0x8cc70208ul,0x90befffaul,0xa4506cebul,0xbef9a3f7ul,0xc67178f2ul
    };

    uint32 w[64];
    for (int i = 0; i < 16; ++i) {
        w[i] = (uint32)chunk[i*4] << 24 | (uint32)chunk[i*4+1] << 16 | (uint32)chunk[i*4+2] << 8 | (uint32)chunk[i*4+3];
    }
    for (int i = 16; i < 64; ++i) {
        uint32 s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
        uint32 s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }

    uint32 a = h[0], b = h[1], c = h[2], d = h[3];
    uint32 e = h[4], f = h[5], g = h[6], hh = h[7];

    for (int i = 0; i < 64; ++i) {
        uint32 S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
        uint32 ch = (e & f) ^ ((~e) & g);
        uint32 temp1 = hh + S1 + ch + k[i] + w[i];
        uint32 S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
        uint32 maj = (a & b) ^ (a & c) ^ (b & c);
        uint32 temp2 = S0 + maj;

        hh = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

std::string sha256_file(const std::string& filePath) {
    std::ifstream ifs(filePath, std::ios::binary);
    if (!ifs.is_open()) return std::string();

    uint64 bitlen = 0;
    uint32 h[8] = {
        0x6a09e667ul,0xbb67ae85ul,0x3c6ef372ul,0xa54ff53aul,
        0x510e527ful,0x9b05688cul,0x1f83d9abul,0x5be0cd19ul
    };

    std::vector<uint8> buffer(64);
    while (ifs.good()) {
        ifs.read(reinterpret_cast<char*>(buffer.data()), 64);
        std::streamsize r = ifs.gcount();
        if (r == 64) {
            sha256_transform(buffer.data(), h);
            bitlen += 512;
        } else {
            // final block handling
            std::vector<uint8> finalBlock(buffer.begin(), buffer.begin() + r);
            // append 0x80
            finalBlock.push_back(0x80);
            // pad with zeros until length mod 64 == 56
            while ((finalBlock.size() % 64) != 56) finalBlock.push_back(0x00);
            // append length in bits big-endian
            bitlen += r * 8;
            uint64 beLen = bitlen;
            for (int i = 7; i >= 0; --i) finalBlock.push_back(static_cast<uint8>((beLen >> (i*8)) & 0xFF));

            // process 64-byte chunks
            for (size_t off = 0; off < finalBlock.size(); off += 64) {
                sha256_transform(finalBlock.data() + off, h);
            }
            // we're done
            std::ostringstream oss;
            for (int i = 0; i < 8; ++i) {
                oss << std::hex << std::setw(8) << std::setfill('0') << h[i];
            }
            return oss.str();
        }
    }

    // If file size was exactly multiple of 64, we still need to append padding
    // append 0x80 then zeros then length
    std::vector<uint8> finalBlock;
    finalBlock.push_back(0x80);
    while ((finalBlock.size() % 64) != 56) finalBlock.push_back(0x00);
    uint64 beLen = bitlen;
    for (int i = 7; i >= 0; --i) finalBlock.push_back(static_cast<uint8>((beLen >> (i*8)) & 0xFF));
    for (size_t off = 0; off < finalBlock.size(); off += 64) {
        sha256_transform(finalBlock.data() + off, h);
    }
    std::ostringstream oss;
    for (int i = 0; i < 8; ++i) {
        oss << std::hex << std::setw(8) << std::setfill('0') << h[i];
    }
    return oss.str();

}

} // namespace baludesk
